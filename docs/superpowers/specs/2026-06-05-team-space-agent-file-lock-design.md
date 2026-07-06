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

文件锁使用 Redis 存储，不再新增数据库锁表。Redis 是锁状态的唯一写入仲裁点，数据库只用于查询用户、团队空间、权限和会话等业务信息。

建议使用 Redis Hash：

```text
team_space:file_lock:{space_id}:{path_hash}
```

其中：

- `path_hash` 使用规范化后的文件相对路径计算，建议 `sha256(normalized_path)`，避免路径中的特殊字符影响 Redis key。
- Hash 中必须保留原始规范化路径，便于排查和错误响应。

Hash 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `space_id` | string | 团队空间 ID |
| `path` | string | 规范化后的文件相对路径 |
| `holder_type` | string | `user` 或 `agent_session` |
| `holder_user_id` | string | 持锁用户 ID |
| `session_id` | string | 持锁会话 ID；用户编辑态也必须带 session_id |
| `lock_token` | string | 持锁方令牌；Agent 使用 `agent:{chat_session_id}`，用户编辑态使用后端生成的 UUID |
| `locked_at_ms` | string | 加锁时间，毫秒时间戳 |
| `expires_at_ms` | string | 逻辑过期时间，毫秒时间戳 |

Redis key TTL：

- Redis key 必须设置 `PEXPIRE`，用于服务崩溃后的物理清理兜底。
- 逻辑过期以 `expires_at_ms` 为准，Lua 脚本必须显式判断。
- 建议 `PEXPIRE = ttl_seconds + cleanup_grace_seconds`，例如锁 TTL 30 分钟，清理宽限 5 分钟。这样可以在 key 尚未物理删除时保留持锁方信息，便于返回 `locked_by` 或处理同一 session 重入。

含义：同一个团队空间内，同一个文件同一时间只能存在一把有效 Redis 锁。

**Redis Cluster 注意事项：**

首版按单实例 Redis 设计。如果未来 Redis 使用 Cluster，Lua 脚本里的所有 key 必须落在同一个 hash slot；当前 `lock_key + owner_index_key` 的组合不能直接跨 slot 执行，需要重新设计 owner 索引或改用同 hash tag key：

```text
team_space:file_lock:{space_id:path_hash}
team_space:file_lock_owner:{lock_token}
```

部署文档必须写清楚首版不支持 Redis Cluster；不能在 Cluster 环境中直接使用跨 slot Lua。

## 5. 加锁函数

核心函数：

```python
def try_lock_file(
    *,
    space_id: int,
    path: str,
    holder_user_id: int,
    session_id: int,
    lock_token: str,
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
4. **必须使用 Redis Lua 脚本完成原子加锁**，禁止 `GET/HGETALL` 后再 `SET/HSET` 的 read-then-write 两步操作。

   Lua 脚本输入：

   ```text
   KEYS[1] = lock_key
   KEYS[2] = owner_index_key
   ARGV[1] = now_ms
   ARGV[2] = expires_at_ms
   ARGV[3] = redis_ttl_ms
   ARGV[4] = space_id
   ARGV[5] = path
   ARGV[6] = holder_type
   ARGV[7] = holder_user_id
   ARGV[8] = session_id
   ARGV[9] = lock_token
   ```

   Lua 脚本规则：

   ```lua
   local key = KEYS[1]
   local now_ms = tonumber(ARGV[1])
   local expires_at_ms = tonumber(ARGV[2])
   local redis_ttl_ms = tonumber(ARGV[3])
   local owner_index_key = KEYS[2]
   local current_session_id = redis.call("HGET", key, "session_id")
   local current_lock_token = redis.call("HGET", key, "lock_token")
   local current_expires_at_ms = tonumber(redis.call("HGET", key, "expires_at_ms") or "0")

   local function write_lock(reason)
     redis.call("HSET", key,
       "space_id", ARGV[4],
       "path", ARGV[5],
       "holder_type", ARGV[6],
       "holder_user_id", ARGV[7],
       "session_id", ARGV[8],
       "lock_token", ARGV[9],
       "locked_at_ms", ARGV[1],
       "expires_at_ms", ARGV[2]
     )
     redis.call("PEXPIRE", key, redis_ttl_ms)
     redis.call("SADD", owner_index_key, key)
     redis.call("PEXPIRE", owner_index_key, redis_ttl_ms)
     return {"OK", reason}
   end

   if current_session_id == false then
     return write_lock("ACQUIRED")
   end

   if current_lock_token == ARGV[9] then
     redis.call("HSET", key, "expires_at_ms", ARGV[2])
     redis.call("PEXPIRE", key, redis_ttl_ms)
     redis.call("SADD", owner_index_key, key)
     redis.call("PEXPIRE", owner_index_key, redis_ttl_ms)
     return {"OK", "REENTRANT"}
   end

   if current_expires_at_ms <= now_ms then
     return write_lock("TAKEN_OVER_EXPIRED")
   end

   return {
     "LOCKED",
     redis.call("HGET", key, "holder_type") or "",
     redis.call("HGET", key, "holder_user_id") or "",
     current_session_id,
     current_lock_token or "",
     redis.call("HGET", key, "locked_at_ms") or "",
     redis.call("HGET", key, "expires_at_ms") or ""
   }
   ```

   - **无锁时**：脚本创建 Hash，设置 `PEXPIRE`，返回 `ACQUIRED`。
   - **同一 lock_token 已有锁**：脚本刷新 `expires_at_ms` 和 Redis key TTL，返回 `REENTRANT`。
   - **其他 session_id 或用户持锁（未过期）**：脚本不修改锁，返回 `LOCKED` 和当前持锁方信息。
   - **其他 session_id 或用户持锁（已过期）**：脚本原子覆盖旧锁，返回 `TAKEN_OVER_EXPIRED`。

5. 如果当前 `lock_token` 已持有该锁，直接刷新 `expires_at_ms`，返回重入成功。
6. 如果该文件已被其他 `session_id` 或其他用户持锁且未过期，返回 `FILE_LOCKED`。
7. 如果已有锁过期（`expires_at_ms <= now_ms`），视为无有效锁，可被新的 Lua 脚本调用原子覆盖。

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

> 注意：如果是 `user` 持锁但响应中 `holder_name` 为空，用户看到的错误信息会是"文件正在被其他用户或会话编辑"，缺少具体人名，导致无法判断该等还是该找谁。**必须**先从 Redis 锁 Hash 读取 `holder_user_id`，再查询用户表获取 `display_name`。

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

同一会话再次编辑已持锁文件时视为可重入加锁：直接放行，并刷新该锁的 `expires_at_ms` 和 Redis key TTL。这样 Agent 在长任务中反复编辑同一个文件时，不会因为锁 TTL 到期而意外失去编辑权。

## 8. 释放锁

释放函数：

```python
def release_session_file_locks(
    *,
    lock_token: str,
) -> int:
    ...


def release_file_lock(
    *,
    space_id: int,
    path: str,
    lock_token: str,
) -> bool:
    ...
```

释放时机：

1. Agent 执行正常结束。
2. 用户停止生成。
3. Agent 执行异常。
4. 服务端捕获到会话流关闭。
5. 用户退出编辑状态、切换文件或关闭页面。

释放范围：

- `lock_token` 是文件锁的 owner。
- 会话结束、取消或异常时，释放该 Agent 会话对应 `lock_token` 当前持有的全部锁。
- 单次 Agent 执行如果需要排查，可以在日志里记录执行标识，不放进锁模型的核心字段。

用户前端编辑锁按单文件释放，避免用户退出某个文件编辑状态时误释放其他文件锁。

释放也必须是原子操作，不能先读取再删除。`release_file_lock()` 使用 Lua 脚本比较 owner 后删除：

```lua
local key = KEYS[1]
local owner_index_key = KEYS[2]
local expected_lock_token = ARGV[1]
local current_lock_token = redis.call("HGET", key, "lock_token")

if current_lock_token == false then
  return 0
end

if current_lock_token == expected_lock_token then
  redis.call("DEL", key)
  redis.call("SREM", owner_index_key, key)
  return 1
end

return 0
```

`release_session_file_locks()` 需要能找到该 Agent 会话当前持有的所有锁。建议加锁成功后维护一个 owner 索引集合：

```text
team_space:file_lock_owner:{lock_token} = Set(lock_key)
```

加锁 Lua 必须和 `HSET` 在同一脚本内完成 `SADD`，释放 Lua 成功后 `SREM`。该集合只是批量释放的辅助索引，**不能作为锁是否有效的判断依据**；锁是否有效只看单个 lock key 的 Lua 结果。会话结束时遍历该集合，对每个 lock key 调用 owner compare-and-delete Lua，最后删除 owner 集合。集合自身也设置不短于锁 key 的 TTL，避免异常时残留。

如果 owner 索引集合中残留了已被其他 owner 接管的旧 lock key，释放脚本会因为 `lock_token` 不匹配返回 0，不会误删他人锁。

## 9. 超时兜底

必须有 `expires_at_ms` 和 Redis key TTL，否则服务崩溃或网络断开时会留下永久锁。

建议：

- 默认 TTL：30 分钟。
- 不使用定时续租任务。
- Agent 每次写操作 hook 都会调用 `try_lock_file()`。
- Redis `PEXPIRE` 自动清理过期锁；不需要依赖数据库后台任务清理。
- 如果需要更早清理 owner 索引集合中的陈旧 key，可以做轻量后台巡检，但不能把巡检作为互斥正确性的前提。

**重入逻辑（核心规则）：**

`try_lock_file()` 的重入判断基于 Redis Lua 脚本内读取到的 `lock_token`，**不基于** `expires_at_ms`：

- 如果 Redis key 仍存在且锁由**同一 lock_token** 持有（无论逻辑上是否已过期）→ 重入成功，刷新 `expires_at_ms` 和 Redis key TTL
- 如果锁由**其他 session_id** 持有且未过期 → 返回 `FILE_LOCKED`
- 如果锁由**其他 session_id** 持有但已过期 → 该 session_id 的锁视为无效，可被 Lua 脚本原子覆盖
- 如果 Redis key 已被物理清理 → 视为无锁，本次请求可重新加锁；若期间其他 session 已抢先加锁，则按 `FILE_LOCKED` 处理

```
同一 session 持锁，过期了
        |
        v
  try_lock_file() 被调用
        |
        v
  检测到锁的 lock_token 与本次相同
        |
        v
  重入成功，刷新 expires_at_ms 和 Redis key TTL ← 这是预期行为，不是 bug
```

```
其他 session 持锁，过期了
        |
        v
  try_lock_file() 被调用
        |
        v
  检测到锁的 session_id 与本次不同，且 expires_at_ms <= now_ms
        |
        v
  视为无效锁，可被本次 Lua 脚本原子覆盖 ← 其他 session 可以"偷"走
```

过期锁处理：

```text
now_ms >= expires_at_ms
        |
        v
视为无效锁
        |
        v
新加锁请求在同一个 Lua 脚本内覆盖旧锁
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

用户退出编辑状态、切换文件、关闭页面或会话结束时，释放用户持有的文件锁。异常关闭时依赖 `expires_at_ms` 和 Redis key TTL 兜底。

**保存接口的锁校验：**

用户保存前，后端必须用 Redis Lua 脚本校验：`当前 lock_token + space_id + path` 是否仍持有有效锁（Redis key 存在，owner 匹配，且 `expires_at_ms > now_ms`）。如果锁已过期、Redis key 已不存在或已被其他 session 持有，**拒绝保存**，返回409：

校验脚本：

```lua
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local expected_lock_token = ARGV[2]
local current_session_id = redis.call("HGET", key, "session_id")
local current_holder_user_id = redis.call("HGET", key, "holder_user_id")
local current_lock_token = redis.call("HGET", key, "lock_token")
local current_expires_at_ms = tonumber(redis.call("HGET", key, "expires_at_ms") or "0")

if current_session_id == false then
  return {"EXPIRED"}
end

if current_lock_token ~= expected_lock_token then
  return {
    "LOCKED",
    redis.call("HGET", key, "holder_type") or "",
    current_holder_user_id or "",
    current_session_id or "",
    current_lock_token or ""
  }
end

if current_expires_at_ms <= now_ms then
  return {"EXPIRED"}
end

return {"OK"}
```

用户编辑态 API 必须包含锁令牌：

- `POST /api/team-spaces/{space_id}/workspace/locks`：输入 `path`，成功时返回 `lock_token`、`expires_at`。
- `DELETE /api/team-spaces/{space_id}/workspace/locks`：输入 `path`、`lock_token`，只释放当前 owner 的锁。
- `PUT /api/team-spaces/{space_id}/workspace/content`：请求体必须新增 `lock_token`，保存前先调用锁校验脚本。

前端不能自己生成 `lock_token`；必须使用后端返回的随机 UUID，避免伪造其他持锁方。

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

**首版采用保守策略：团队空间会话中直接拒绝 Bash 工具。Agent 需要写文件时必须使用 `Write/Edit/MultiEdit` 工具。**

原因：`Bash` 和 `Write`/`Edit` 是两个独立的工具，Claude LLM 可以选择调用其中任意一个。当 LLM 选择 `Write` 时，hook 从 `tool_input.file_path` 可以直接拿到目标文件；但当 LLM 选择 `Bash` 时，hook 只能看到命令字符串，需要额外解析才能推断目标——这增加了复杂度且容易出错，因此首版在团队空间中直接拒绝 Bash，避免绕过文件锁。

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

保存时锁已过期（持锁方仍为当前用户但 `expires_at_ms <= now_ms`，或 Redis key 已过期不存在），返回：

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
3. 前端保存接口：保存前通过 Redis Lua 校验当前 `lock_token` 是否仍持有该文件的**有效**锁（Redis key 存在，owner 匹配，且 `expires_at_ms > now_ms`），如果锁已过期、Redis key 不存在或已被其他 owner 持有，拒绝保存，返回 `FILE_LOCK_EXPIRED` 或 `FILE_LOCKED`。
4. 会话结束、异常、用户退出编辑状态：释放对应锁。
5. Redis TTL 兜底：释放异常时由 Redis key 自动过期兜底。

文件创建、重命名、移动、删除、上传和转换任务也属于写入口：

- `create file`：对目标文件路径加锁；目录创建首版可沿用写权限校验，不纳入文件锁。
- `rename/move/delete file`：对源文件路径加锁；目标路径已存在时按现有文件操作错误处理。
- `upload file`：对最终目标文件路径加锁；上传完成或失败后释放。
- `conversion/retry`：如果会写入源文件旁的 Markdown 或 `.markdown` 映射文件，必须对实际写入路径加锁。

保存 Office/PDF 预览内容时，后端当前可能把原始文件路径映射到转换后的 Markdown 文件。锁校验必须使用**实际写入路径**，否则用户锁住 `a.pdf` 但后端写的是 `.markdown/a.md` 时仍可能冲突。

后续上传、转换任务或其他后台写文件任务也必须复用同一套锁服务，不能绕过文件锁直接写团队空间文件。

## 14. 测试重点

Agent：

1. 文件无锁时，Agent 编辑前加锁成功并允许写入。
2. 文件被其他会话持锁时，Agent 加锁失败并拒绝写入。
3. 同一会话重复编辑同一文件时，加锁重入成功，并刷新 `expires_at_ms` 和 Redis key TTL。
4. Agent 一轮会话编辑多个文件时，记录多把锁。
5. Agent 会话正常结束后释放该会话所有锁。
6. Agent 会话异常退出后释放该会话所有锁。
7. 锁过期后，新会话可以重新加锁。
8. **【T2】** 同一 session 持锁期间逻辑 TTL 过期但 Redis key 尚未物理清理，下一次 `try_lock_file()` 调用应重入成功并刷新 `expires_at_ms` 和 Redis key TTL，而非报错。
9. **【T2 variant】** session A 持锁并逻辑过期，session B 尝试加锁同一文件，应通过 Lua 脚本成功"偷"走锁（过期锁可被其他 session 覆盖）。
10. **【T2 Redis atomic】** session A 和 session B 并发加锁同一无锁文件时，只能有一个 Lua 脚本返回成功，另一个返回 `FILE_LOCKED`。

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
5. Redis key TTL 兜底清理过期锁。

这样能把设计从“Agent 自律”提升为“系统级文件编辑互斥”，评审时更站得住。
