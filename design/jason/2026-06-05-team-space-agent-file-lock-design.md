# 团队空间文件锁设计方案

生成日期：2026-06-05
状态：Draft
关联设计：

- `docs/superpowers/specs/2026-06-04-team-space-file-version-optimistic-lock-design.md`
- `docs/superpowers/specs/2026-06-05-team-space-file-concurrency-alternatives.md`

## 1. 核心结论

团队空间文件编辑采用文件级显式锁。前端用户编辑和 Agent 写入共用同一套 `FileLockService`：

1. 用户点击文件默认是预览状态，不加锁；切换到编辑状态时请求文件锁。
2. Agent 在写文件前通过 hook 调用加锁函数，持锁成功后才允许写入。
3. 加锁失败说明文件已被其他用户、其他会话或其他 Agent 持有，本次编辑被拒绝。
4. 会话结束、取消、异常退出或用户退出编辑状态时释放对应文件锁。

这套方案比纯乐观锁更直接。它不是等写入时发现冲突，而是在编辑前就阻止多个执行者同时编辑同一个文件。

## 2. 目标

1. 文件锁粒度是单个团队空间文件，不再锁整个团队空间。
2. 用户进入编辑状态前必须持有该文件锁，预览文件不加锁。
3. Agent 修改文件前必须持有该文件锁。
4. 同一持锁方重复编辑同一文件时允许重入，不重复报错，并刷新过期时间。
5. 其他会话、其他用户、其他 Agent 持锁时，本次编辑不能继续。
6. 会话正常结束、用户取消、Agent 执行异常、用户退出编辑状态时，释放对应文件锁。
7. 异常情况下即使释放失败，也要有超时兜底，避免永久死锁。

## 3. 非目标

1. 不做多人实时协同编辑。
2. 不做自动合并。
3. 不做独立的用户手动加锁/解锁界面，锁行为由进入或退出编辑状态触发。
4. 不把文件锁扩展成空间级锁。
5. 不允许 Agent 通过 Bash 写团队空间文件，必须使用有结构化 file_path 的 Write/Edit/MultiEdit 工具。

## 4. 文件锁模型

建议新增 `team_space_file_locks`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | INTEGER PK | 锁记录 ID |
| `space_id` | INTEGER | 团队空间 ID |
| `path` | VARCHAR | 文件相对路径 |
| `holder_type` | VARCHAR | `user` 或 `agent_session` |
| `holder_user_id` | INTEGER NULL | 持锁用户 |
| `session_id` | INTEGER NULL | 持锁会话 |
| `locked_at` | DATETIME | 加锁时间 |
| `expires_at` | DATETIME | 锁过期时间 |
| `released_at` | DATETIME NULL | 释放时间 |

约束：

```text
UNIQUE(space_id, path) WHERE released_at IS NULL
```

含义：同一个团队空间内，同一个文件同一时间只能存在一把有效锁。

## 5. 加锁函数

核心函数：

```python
def try_lock_file(
    *,
    space_id: int,
    path: str,
    holder_user_id: int,
    session_id: int,
    ttl_seconds: int = 1800,
) -> FileLockResult:
    ...
```

返回：

```python
class FileLockResult(BaseModel):
    ok: bool
    lock: FileLockOut | None = None
    reason: str | None = None
    locked_by: FileLockHolderOut | None = None
```

加锁规则：

1. 先校验用户是团队空间成员。
2. 再校验用户具备写权限。
3. 规范化文件路径，禁止越界路径。
4. **必须使用单条原子 SQL**，禁止 read-then-write 的两步操作。

   使用 `INSERT ... ON CONFLICT` 实现原子加锁：

   ```sql
   INSERT INTO team_space_file_locks
     (space_id, path, holder_type, holder_user_id, session_id, locked_at, expires_at, released_at)
   VALUES
     (:space_id, :path, :holder_type, :holder_user_id, :session_id, NOW(), NOW() + INTERVAL '30 minutes', NULL)
   ON CONFLICT (space_id, path) WHERE released_at IS NULL
   DO UPDATE SET
     expires_at = NOW() + INTERVAL '30 minutes',
     released_at = NULL,
     holder_type = EXCLUDED.holder_type,
     holder_user_id = EXCLUDED.holder_user_id,
     session_id = EXCLUDED.session_id,
     locked_at = EXCLUDED.locked_at
   RETURNING id, holder_type, holder_user_id, session_id, locked_at, expires_at
   ```

   - **无锁时**：INSERT 成功，返回新锁记录。
   - **同一 session_id 已有锁**：ON CONFLICT 触发 UPDATE，刷新 `expires_at`，返回重入成功。
   - **其他 session_id 或用户持锁（未过期）**：ON CONFLICT 触发 UPDATE，但 `RETURNING` 中检测到原锁 `session_id` 与本次不同，**应回滚事务并返回 `FILE_LOCKED`**，而非覆盖他人锁。
   - **锁已过期**：`released_at` 已有值或 `expires_at < NOW()`，该 index entry 不存在，INSERT 成功。

   **实现注意**：此 SQL 依赖 PostgreSQL partial unique index（`UNIQUE(space_id, path) WHERE released_at IS NULL`），`ON CONFLICT ... WHERE` 语法需要用原生 SQL 执行，主流 ORM 的默认 `insert ... on conflict` 不支持带 `WHERE` 子句的 conflict target。

5. 如果当前 session 已持有该锁，直接刷新 `expires_at`，返回重入成功。
6. 如果该文件已被其他 `session_id` 或其他用户持锁，返回 `FILE_LOCKED`。
7. 如果已有锁过期（`expires_at < NOW()`），视为无有效锁，可被新的 ON CONFLICT UPDATE 覆盖。

加锁失败响应：

```json
{
  "ok": false,
  "reason": "FILE_LOCKED",
  "locked_by": {
    "holder_type": "agent_session",
    "holder_name": "团队会话 #123",
    "locked_at": "2026-06-05T10:00:00+08:00"
  }
}
```

`holder_name` 显示规则：

| holder_type | holder_name 值 |
|---|---|
| `agent_session` | `"团队会话 #" + session_id`，如 `"团队会话 #123"` |
| `user` | 从用户表查询 `display_name` 或 `name`，如 `"张三"`；无姓名时使用 `"用户 #user_id"` |

> 注意：如果是 `user` 持锁但响应中 `holder_name` 为空，用户看到的错误信息会是"文件正在被其他用户或会话编辑"，缺少具体人名，导致无法判断该等还是该找谁。**必须**在查询锁记录时通过 `holder_user_id` JOIN 用户表获取 `display_name`。

## 6. Agent 编辑流程

Agent 文件写入通过 hook 控制。Agent 读文件不需要加锁，只有写入前才加锁。

```text
Agent 准备写 docs/a.md
        |
        v
PreToolUse 解析目标文件路径
        |
        v
try_lock_file(space_id, path, session_id)
        |
        +-- 成功：允许工具继续执行
        |
        +-- 失败：拒绝工具执行，提示文件已被占用
```

适用工具：

- `Write` → hook 从 `tool_input.file_path` 读取目标文件路径
- `Edit` → hook 从 `tool_input.file_path` 读取目标文件路径
- `MultiEdit` → hook 从 `tool_input.file_path` 读取目标文件路径
- `NotebookEdit` → hook 从 `tool_input.notebook_path` 读取目标文件路径

**`Bash` 不接入文件锁服务**，原因：Bash 工具的 `tool_input` 只有原始命令字符串（`{command: "echo hi > docs/a.md"}`），没有结构化的 `file_path` 字段，hook 无法直接获取目标文件路径。Agent 需要写文件时应使用 `Write/Edit/MultiEdit`工具。

## 7. 同一会话多文件编辑

同一会话可以持有多把文件锁：

```text
session 123
  - docs/a.md
  - docs/b.md
  - prompts/c.md
```

Agent 每次准备编辑文件时都调用 `try_lock_file()`。如果某个文件加锁失败，只拒绝该文件的编辑，不影响已持锁文件。

同一会话再次编辑已持锁文件时视为可重入加锁：直接放行，并刷新该锁的 `expires_at`。这样 Agent 在长任务中反复编辑同一个文件时，不会因为锁 TTL 到期而意外失去编辑权。

## 8. 释放锁

释放函数：

```python
def release_session_file_locks(
    *,
    session_id: int,
) -> int:
    ...


def release_file_lock(
    *,
    space_id: int,
    path: str,
    holder_user_id: int,
    session_id: int | None = None,
) -> bool:
    ...
```

释放时机：

1. Agent 执行正常结束。
2. 用户停止生成。
3. Agent 执行异常。
4. 服务端捕获到会话流关闭。
5. 用户退出编辑状态、切换文件或关闭页面。
6. 后台任务发现锁过期。

释放范围：

- `session_id` 是文件锁的会话级 owner。
- 会话结束、取消或异常时，释放该会话当前持有的全部锁。
- 单次 Agent 执行如果需要排查，可以在日志里记录执行标识，不放进锁模型的核心字段。

用户前端编辑锁按单文件释放，避免用户退出某个文件编辑状态时误释放其他文件锁。

## 9. 超时兜底

必须有 `expires_at`，否则服务崩溃或网络断开时会留下永久锁。

建议：

- 默认 TTL：30 分钟。
- 不使用定时续租任务。
- Agent 每次写操作 hook 都会调用 `try_lock_file()`。
- 后台任务定期清理过期锁（`expires_at < NOW() AND released_at IS NULL`）。

**重入逻辑（核心规则）：**

`try_lock_file()` 的重入判断基于 `session_id`，**不基于** `expires_at`：

- 如果锁由**同一 session_id** 持有（无论是否已过期）→ 重入成功，刷新 `expires_at`
- 如果锁由**其他 session_id** 持有且未过期 → 返回 `FILE_LOCKED`
- 如果锁由**其他 session_id** 持有但已过期 → 该 session_id 的锁视为无效，可被覆盖

```
同一 session 持锁，过期了
        |
        v
  try_lock_file() 被调用
        |
        v
  检测到锁的 session_id 与本次相同
        |
        v
  重入成功，刷新 expires_at ← 这是预期行为，不是 bug
```

```
其他 session 持锁，过期了
        |
        v
  try_lock_file() 被调用
        |
        v
  检测到锁的 session_id 与本次不同，且 expires_at < NOW()
        |
        v
  视为无效锁，可被本次覆盖 ← 其他 session 可以"偷"走
```

过期锁处理：

```text
now > expires_at
        |
        v
视为无效锁
        |
        v
新加锁请求可先释放旧锁，再创建新锁
```

## 10. 用户编辑流程

用户点击文件时默认进入预览状态，不加锁。只有用户切换到编辑状态时，前端才请求文件锁：

```text
用户打开文件
        |
        v
默认预览，不加锁
        |
        v
用户点击编辑
        |
        v
前端请求文件锁
        |
        +-- 成功：允许保存
        |
        +-- 失败：保持预览状态，提示文件正在被其他会话编辑
```

用户退出编辑状态、切换文件、关闭页面或会话结束时，释放用户持有的文件锁。异常关闭时依赖 `expires_at` 兜底。

**保存接口的锁校验：**

用户保存前，后端必须校验：`当前 session_id + space_id + path` 是否仍持有有效锁（`released_at IS NULL AND expires_at > NOW()`）。如果锁已过期或已被其他 session 持有，**拒绝保存**，返回409：

```json
{
  "detail": {
    "code": "FILE_LOCK_EXPIRED",
    "message": "编辑超时，请重新打开文件编辑",
    "path": "docs/a.md"
  }
}
```

如果不做这层校验，用户进入编辑状态后锁过期，又继续保存，会重新引入并发写风险。

## 11. Bash 写入处理

Bash 是风险最大的入口，因为它可能写多个文件，也可能通过重定向、脚本或命令间接写文件。

Bash 工具的 `tool_input` 只有原始命令字符串（`{command: "echo hi > docs/a.md"}`），没有结构化的 `file_path` 字段。hook 无法直接获取目标文件路径，无法通过 `try_lock_file()` 进行加锁。

**首版采用保守策略：Agent 需要写文件时必须使用 `Write/Edit/MultiEdit` 工具，不允许通过 Bash 写团队空间文件。**

原因：`Bash` 和 `Write`/`Edit` 是两个独立的工具，Claude LLM 可以选择调用其中任意一个。当 LLM 选择 `Write` 时，hook 从 `tool_input.file_path` 可以直接拿到目标文件；但当 LLM 选择 `Bash` 时，hook 只能看到命令字符串，需要额外解析才能推断目标——这增加了复杂度且容易出错，因此首版直接要求使用有结构化输入的写工具。

未来如需支持 Bash 写文件，需先实现 Bash 命令的路径解析逻辑，再接入文件锁服务。

## 12. 错误提示

Agent 加锁失败时，hook 返回：

```text
文件正在被其他用户或会话编辑，已阻止本次写入。
path=docs/a.md
请稍后重试，或改为编辑其他文件。
```

前端用户保存失败时，返回：

```json
{
  "detail": {
    "code": "FILE_LOCKED",
    "message": "文件正在被其他用户或会话编辑，请稍后再试",
    "path": "docs/a.md",
    "locked_by": {
      "holder_type": "agent_session",
      "holder_name": "团队会话 #123"
    }
  }
}
```

保存时锁已过期（持锁方仍为当前用户但 `expires_at < NOW()`），返回：

```json
{
  "detail": {
    "code": "FILE_LOCK_EXPIRED",
    "message": "编辑超时，请重新打开文件编辑",
    "path": "docs/a.md"
  }
}
```

建议状态码使用 `409 Conflict`。如果前端错误处理支持，也可以使用 `423 Locked`，但需要统一处理。

## 13. 统一锁服务接入范围

首版把所有团队空间文件编辑入口都接入 `FileLockService`：

1. Agent 写工具 hook：写入前加锁，失败则阻止工具执行。
2. 前端编辑态：从预览切换到编辑时加锁，失败则保持预览。
3. 前端保存接口：保存前校验当前 session 是否仍持有该文件的**有效**锁（`released_at IS NULL AND expires_at > NOW()`），如果锁已过期或已被其他 session 持有，拒绝保存，返回 `FILE_LOCK_EXPIRED` 或 `FILE_LOCKED`。
4. 会话结束、异常、用户退出编辑状态：释放对应锁。
5. 过期锁清理：释放异常时由 TTL 兜底。

后续上传、转换任务或其他后台写文件任务也必须复用同一套锁服务，不能绕过文件锁直接写团队空间文件。

## 14. 测试重点

Agent：

1. 文件无锁时，Agent 编辑前加锁成功并允许写入。
2. 文件被其他会话持锁时，Agent 加锁失败并拒绝写入。
3. 同一会话重复编辑同一文件时，加锁重入成功，并刷新 `expires_at`。
4. Agent 一轮会话编辑多个文件时，记录多把锁。
5. Agent 会话正常结束后释放该会话所有锁。
6. Agent 会话异常退出后释放该会话所有锁。
7. 锁过期后，新会话可以重新加锁。
8. **【T2】** 同一 session 持锁期间 TTL 过期（用户离开30 分钟以上），下一次 `try_lock_file()` 调用应重入成功并刷新 `expires_at`，而非报错或被其他 session "偷"走。
9. **【T2 variant】** session A 持锁并过期，session B 尝试加锁同一文件，应成功"偷"走锁（过期锁可被其他 session 覆盖）。

用户：

1. 用户打开文件进入预览状态时不加锁。
2. 用户切换到编辑状态时请求文件锁。
3. 用户编辑被 Agent 持锁的文件时返回 `FILE_LOCKED`，并保持预览状态。
4. Agent 编辑被用户持锁的文件时返回 `FILE_LOCKED`。
5. 用户退出编辑状态后释放文件锁。
6. reader 即使文件未锁，也不能加锁或写入。
7. **【T3】** 用户持锁期间 TTL 过期，用户点击保存，后端校验发现锁已过期，拒绝保存，返回 `FILE_LOCK_EXPIRED`（409），前端提示"编辑超时，请重新打开文件编辑"。
8. **【T3 variant】** 用户持锁 TTL 过期后，其他 session 抢先拿到了锁，用户点保存时检测到锁已被他人持有，返回 `FILE_LOCKED`。

Bash：

1. Agent 调用 Bash 工具写文件（无论任何形式的写入命令），hook 返回错误，提示"请改用 Write/Edit/MultiEdit 工具"。
2. 无法从 Bash 命令提取目标路径时，hook 拒绝执行。

## 15. 最终建议

最终方案是统一文件锁服务：

```text
统一 FileLockService
        |
        +-- Agent 写前加锁
        +-- 用户切换编辑状态时加锁
        +-- 会话结束/异常统一释放
        +-- TTL 兜底清理
```

首版推荐：

1. 实现 `try_lock_file()`。
2. Agent 写工具 hook 接入加锁。
3. 前端从预览切换到编辑状态时请求文件锁。
4. 会话结束和异常时释放该会话所有文件锁。
5. 后台清理过期锁。

这样能把设计从“Agent 自律”提升为“系统级文件编辑互斥”，评审时更站得住。
