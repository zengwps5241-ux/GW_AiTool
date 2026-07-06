# 团队空间文件乐观并发控制方案

## 背景

团队空间原方案包含显式空间锁：成员设置 lock 后，由持锁人获得空间内文件编辑权限并负责解锁。该方案会让协作状态对用户可见，也会把并发控制扩大到整个团队空间。

新的目标是将文件冲突控制做成对用户无感的乐观并发机制：团队空间只负责成员可见性和角色权限，文件写入前由服务端判断目标文件是否已经发生变化；如果发生变化，向 agent 返回明确错误信息，由 agent 自行决定重读、合并、覆盖或放弃。

## 目标

1. 团队空间不再提供显式 lock/unlock。
2. 不存在空间持锁人、锁定时间、锁备注等状态。
3. 文件并发控制从空间级锁改为文件级乐观版本校验。
4. 用户和 agent 的写权限仍由团队成员角色决定。
5. agent 在编辑文件前必须校验文件是否已从它读取或会话快照后发生变化。
6. 冲突返回给 agent，不在 UI 上引入用户可见的锁操作。

## 非目标

1. 不实现多人实时协同编辑。
2. 不在团队空间详情页展示锁状态。
3. 不由服务端自动合并冲突内容。
4. 不为整个团队空间加排他锁。

## 权限模型

团队空间权限分为两层：

1. 成员可见性：只有团队空间成员可以查看空间、文件和团队会话。
2. 成员写权限：`owner` 和 `editor` 可写，`reader` 只读。

`can_write` 只表达成员角色写权限，不再表达空间锁状态。

建议语义：

```python
def member_can_write(member) -> tuple[bool, str | None]:
    if member.role != "editor":
        return False, "只读成员不能编辑团队空间"
    return True, None
```

并发冲突不影响 `can_write`。并发冲突只在具体写入入口返回 `409 Conflict`。

## 文件版本模型

服务端为每个文件生成版本信息：

```json
{
  "path": "docs/a.md",
  "exists": true,
  "size": 1024,
  "mtime_ns": 1780000000000000000,
  "sha256": "..."
}
```

字段说明：

- `path`：相对工作空间根目录的文件路径。
- `exists`：文件是否存在。
- `size`：文件大小。
- `mtime_ns`：纳秒级修改时间。
- `sha256`：文件内容哈希。

建议比较策略：

1. 文件不存在时，版本只需要表达 `exists=false`。
2. 文件存在时，优先比较 `exists`、`size`、`mtime_ns`。
3. 当快速字段不一致时，可计算并比较 `sha256`，用于形成更准确的冲突信息。
4. 最终以服务端写入前获取到的实际版本为准。

## Schema 建议

```python
class FileVersion(BaseModel):
    path: str
    exists: bool
    size: int | None = None
    mtime_ns: int | None = None
    sha256: str | None = None


class FileConflictOut(BaseModel):
    code: str = "FILE_VERSION_CONFLICT"
    message: str = "文件已被其他操作变更，请重新读取后再编辑"
    path: str
    expected: FileVersion | None = None
    actual: FileVersion
```

写入类请求增加：

```python
expected_version: FileVersion | None = None
```

`expected_version=None` 的处理建议：

- 人类用户通过前端写入时，应尽量传入版本信息。
- agent 写入时必须传入快照版本或由 hook 按快照校验。
- 为兼容旧接口，可允许个人空间或非覆盖写入暂时不传；团队空间写入建议强制要求。

## API 交互

读取、预览、文件树接口返回文件版本信息。写入类接口携带 `expected_version`。

保存文件请求示例：

```json
{
  "path": "docs/a.md",
  "content": "...",
  "expected_version": {
    "path": "docs/a.md",
    "exists": true,
    "size": 1024,
    "mtime_ns": 1780000000000000000,
    "sha256": "..."
  }
}
```

写入前处理流程：

1. 校验用户是团队空间成员。
2. 校验成员角色允许写。
3. 获取目标文件当前版本。
4. 比较 `expected_version` 和当前版本。
5. 一致则执行写入。
6. 不一致返回 `409 Conflict`。

冲突响应示例：

```json
{
  "detail": {
    "code": "FILE_VERSION_CONFLICT",
    "message": "文件已被其他操作变更，请重新读取后再编辑",
    "path": "docs/a.md",
    "expected": {
      "path": "docs/a.md",
      "exists": true,
      "size": 1024,
      "mtime_ns": 1780000000000000000,
      "sha256": "..."
    },
    "actual": {
      "path": "docs/a.md",
      "exists": true,
      "size": 1100,
      "mtime_ns": 1780000001000000000,
      "sha256": "..."
    }
  }
}
```

## 写操作规则

保存文件：

- 校验目标文件当前版本等于 `expected_version`。
- 版本一致时写入。
- 版本不一致时返回 409。

新建文件：

- `expected_version.exists` 应为 `false`。
- 如果目标文件已存在，返回 409。

删除文件：

- 校验待删除文件版本一致。
- 版本一致时删除。

重命名和移动：

- 校验源文件版本一致。
- 校验目标路径不存在。
- 源文件变化或目标路径已存在时返回 409。

上传覆盖：

- 覆盖已有文件时校验目标文件版本一致。
- 新文件上传时校验目标路径不存在。

转换任务输出：

- 写 `.markdown` 文件前校验输出文件版本。
- retry 时使用任务创建或上次读取时记录的输出文件版本。
- 输出文件变化时返回 409，避免覆盖人工修改。

## 服务端 helper

建议在 workspace 模块新增统一 helper：

```python
def get_file_version(root: Path, relative_path: str) -> FileVersion:
    ...


def assert_file_version(root: Path, relative_path: str, expected: FileVersion | None) -> None:
    actual = get_file_version(root, relative_path)
    if not version_matches(expected, actual):
        raise HTTPException(
            status_code=409,
            detail=FileConflictOut(path=relative_path, expected=expected, actual=actual).model_dump(),
        )
```

所有团队空间文件写入口必须复用该 helper，避免不同接口的冲突判断不一致。

## Agent 写入控制

agent 写文件前需要做版本校验。建议在每轮 agent 执行前建立工作区文件版本快照：

```python
workspace_snapshot: dict[str, FileVersion]
```

Claude `PreToolUse` hook 对以下工具执行写前校验：

- `Write`
- `Edit`
- `MultiEdit`
- `NotebookEdit`
- 可能写文件的 `Bash`

校验规则：

1. 从 tool input 解析目标路径。
2. 从快照中找到该路径的 expected version。
3. 写入前获取当前 actual version。
4. expected 与 actual 不一致时 deny。
5. deny reason 包含路径、expected、actual 和处理建议。

对于 `Bash`：

- 能明确解析目标路径的写命令，做版本校验。
- 无法可靠解析写入路径的命令，建议拒绝，并提示 agent 使用受控文件写入方式或明确目标文件。

hook 返回给 agent 的错误信息建议：

```text
文件已被其他操作变更，请重新读取后再编辑。path=docs/a.md
```

## 对现有团队空间设计的调整

需要移除：

- `TeamSpace.lock_holder_user_id`
- `TeamSpace.lock_acquired_at`
- `TeamSpace.lock_note`
- `TeamSpaceLockIn`
- `/api/team-spaces/{id}/lock`
- `DELETE /api/team-spaces/{id}/lock`
- 持锁人才能编辑的权限逻辑
- 空间已锁定相关 readonly reason

需要新增：

- `FileVersion` schema。
- `FileConflictOut` schema。
- 文件版本获取和比较 helper。
- 写文件请求的 `expected_version`。
- agent 文件版本快照。
- Claude 写工具 hook 的乐观并发校验。
- 文件冲突返回 409 的测试。

## 测试重点

服务端测试：

1. editor 保存文件时版本一致，写入成功。
2. editor 保存文件时文件已变化，返回 409。
3. 新建文件时目标已存在，返回 409。
4. 删除文件时版本已变化，返回 409。
5. rename/move 时源文件变化，返回 409。
6. rename/move 时目标路径已存在，返回 409。
7. reader 即使版本一致也不能写，返回 403。
8. 上传覆盖文件时版本冲突返回 409。
9. 转换任务 retry 写 `.markdown` 时版本冲突返回 409。

agent hook 测试：

1. agent 快照后文件被其他成员修改，`Write` 被拒绝。
2. agent 快照后文件被其他成员修改，`Edit` 被拒绝。
3. agent 快照后文件被其他成员修改，`MultiEdit` 被拒绝。
4. 无法解析写入路径的 Bash 写命令被拒绝。
5. readonly 成员的 agent 仍然被角色权限拒绝，返回 403 语义的错误信息。

## 结论

团队空间只负责成员可见性、角色权限和共享会话归属；文件并发控制下沉到每一个写文件入口。该方案避免了用户感知锁，也避免了空间级锁带来的粗粒度阻塞。agent 在遇到文件版本冲突时收到明确错误信息，再自行决定后续处理。
