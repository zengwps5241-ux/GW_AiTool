# 团队空间文件乐观锁技术方案

生成日期：2026-06-05
状态：Draft
关联设计：`docs/superpowers/specs/2026-06-03-team-space-design.md`

## 1. 核心结论

团队空间不再做用户可见的空间级 lock/unlock。文件并发控制改为文件级乐观锁：

1. 用户在前端编辑文件时，打开文件即保存版本信息，保存时把版本信息一起传给后端校验。
2. Agent 在会话中编辑文件时，读取文件即缓存版本信息，写文件前通过 hook 校验版本一致性。

版本一致才允许写入；版本不一致说明文件已被其他用户或 Agent 修改，返回冲突错误。

## 2. 文件版本定义

文件版本由服务端根据磁盘文件实时生成，不单独存数据库。

```python
class FileVersion(BaseModel):
    path: str
    exists: bool
    size: int | None = None
    mtime_ns: int | None = None
    sha256: str | None = None
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `path` | 工作空间内相对路径，防止拿 A 文件版本写 B 文件 |
| `exists` | 文件是否存在；新建文件时使用 `exists=false` |
| `size` | 文件大小 |
| `mtime_ns` | 文件纳秒级修改时间 |
| `sha256` | 文件内容哈希 |

文件存在时，`path/exists/size/mtime_ns/sha256` 全部一致才认为版本一致。文件不存在时，`exists=false` 表达“我期望这个路径当前不存在”，用于新建文件。

## 3. 用户编辑文件流程

### 3.1 打开文件

用户在前端打开团队空间文件时，后端返回文件内容和当前版本：

```json
{
  "path": "docs/a.md",
  "content": "...",
  "version": {
    "path": "docs/a.md",
    "exists": true,
    "size": 1024,
    "mtime_ns": 1780000000000000000,
    "sha256": "..."
  }
}
```

前端把 `version` 保存在当前编辑器状态中：

```ts
type OpenFileState = {
  path: string;
  content: string;
  version: FileVersion;
  dirty: boolean;
};
```

### 3.2 保存文件

用户编辑完成后，前端保存文件时把打开文件时拿到的版本一并传给后端：

```json
{
  "path": "docs/a.md",
  "content": "# new content",
  "expected_version": {
    "path": "docs/a.md",
    "exists": true,
    "size": 1024,
    "mtime_ns": 1780000000000000000,
    "sha256": "..."
  }
}
```

后端处理：

1. 校验用户是团队空间成员。
2. 校验用户具备写权限。
3. 重新提取目标文件当前版本 `actual_version`。
4. 比较 `expected_version` 和 `actual_version`。
5. 一致则写入文件，并返回写入后的新版本。
6. 不一致则返回 `409 FILE_VERSION_CONFLICT`。

保存成功后，前端用响应里的新版本替换本地旧版本。保存冲突后，前端只提示用户“文件已被其他人修改，存在编辑冲突”，不静默覆盖，不要求提供合并入口。

### 3.3 新建文件

新建文件不需要先读取版本，前端只需要声明目标路径应该不存在：

```json
{
  "path": "docs/new.md",
  "content": "...",
  "expected_version": {
    "path": "docs/new.md",
    "exists": false
  }
}
```

后端写入前发现目标已存在，则返回 409，避免覆盖别人刚创建的同名文件。

## 4. Agent 文件编辑流程

Agent 的文件并发控制通过 Claude hook 实现。核心规则是：

- Agent 读文件时缓存该文件版本。
- Agent 写文件时校验该文件当前版本是否仍等于缓存版本。
- Agent 没读过已有文件就尝试修改时，拒绝写入，提示先读取文件。

### 4.1 版本台账

每轮 Agent run 创建一个内存版本台账：

```python
@dataclass
class AgentVersionLedger:
    versions: dict[str, FileVersion]

    def record_read(self, path: str, version: FileVersion) -> None:
        self.versions[path] = version

    def expected_for_write(self, path: str) -> FileVersion | None:
        return self.versions.get(path)
```

版本台账只在本轮 run 内有效，不跨轮复用。

### 4.2 读文件 hook

Agent 通过 `Read` 或明确的 Bash 读操作读取文件时，hook 提取文件版本并写入台账：

```text
Agent Read docs/a.md
        |
        v
Hook 提取 FileVersion
        |
        v
ledger["docs/a.md"] = FileVersion(...)
```

这里不根据用户引用文件建快照，也不扫描整个工作空间。只有 Agent 实际读取过的文件才进入版本台账。

### 4.3 写文件 hook

Agent 通过 `Write`、`Edit`、`MultiEdit` 或明确的 Bash 写操作修改文件时，hook 在写入前做版本校验：

```text
Agent 写 docs/a.md
        |
        v
Hook 从 ledger 读取 expected_version
        |
        v
Hook 重新提取 actual_version
        |
        +-- 一致：允许写入
        |
        +-- 不一致：拒绝写入，提示文件已变化
```

规则：

1. 修改已有文件时，必须能从台账找到 `expected_version`。
2. 新建文件时，可以使用 `exists=false` 作为 `expected_version`。
3. 版本不一致时，hook 拒绝本次写入，并提示 Agent 重新读取文件后再编辑。
4. 写入成功后，重新提取文件新版本并更新台账，避免同一轮连续编辑误报冲突。

## 5. 后端校验逻辑

建议在 workspace 模块提供统一 helper，前端文件 API 和 Agent hook 复用同一套逻辑：

```python
def get_file_version(root: Path, relative_path: str) -> FileVersion:
    ...


def version_matches(expected: FileVersion, actual: FileVersion) -> bool:
    if expected.path != actual.path:
        return False
    if expected.exists != actual.exists:
        return False
    if not expected.exists:
        return True
    return (
        expected.size == actual.size
        and expected.mtime_ns == actual.mtime_ns
        and expected.sha256 == actual.sha256
    )


def assert_file_version(root: Path, path: str, expected: FileVersion) -> None:
    actual = get_file_version(root, path)
    if not version_matches(expected, actual):
        raise FileVersionConflict(path=path, expected=expected, actual=actual)
```

所有写入入口都要在实际写入前调用 `assert_file_version()`。

为避免两个请求同时通过校验后先后覆盖，同一目标路径的“版本校验 + 写入”需要放在同一个短临界区内执行。这个锁是服务端内部写入锁，不是用户可见的空间锁。

## 6. 错误返回

版本冲突统一返回 409：

```json
{
  "detail": {
    "code": "FILE_VERSION_CONFLICT",
    "message": "文件已被其他操作变更，请重新读取后再编辑",
    "path": "docs/a.md",
    "expected": { "...": "..." },
    "actual": { "...": "..." }
  }
}
```

语义区分：

| 场景 | 状态码 | 说明 |
| --- | --- | --- |
| 非成员访问团队空间 | 404 | 不暴露空间存在性 |
| reader 写文件 | 403 | 没有写权限 |
| editor 缺少 `expected_version` | 400 | 写请求不完整 |
| editor 版本冲突 | 409 | 有权限，但基于旧版本写入 |
| editor 版本一致 | 200/204 | 写入成功 |

## 7. 覆盖范围

首版重点覆盖两个入口：

1. 前端编辑器保存文件。
2. Agent 通过工具读写文件。

其他写入口按相同模型扩展：

| 操作 | 版本策略 |
| --- | --- |
| 新建文件 | 使用 `exists=false` |
| 上传新文件 | 使用 `exists=false` |
| 上传覆盖 | 使用目标文件当前版本 |
| 删除文件 | 使用待删除文件版本 |
| 移动/重命名文件 | 使用源文件版本，并校验目标路径不存在 |
| 转换任务输出 | 任务创建时记录输出文件版本，任务写入前校验 |

## 8. 测试重点

前端文件 API：

1. 打开文件返回 `version`。
2. 保存文件时版本一致，写入成功并返回新版本。
3. 保存文件时版本不一致，返回 409。
4. 保存冲突时前端展示编辑冲突提示。
5. reader 即使版本一致也不能写，返回 403。

Agent hook：

1. Agent 读取文件后，版本进入本轮台账。
2. Agent 修改已读取且未变化的文件，允许写入。
3. Agent 修改已读取但已变化的文件，拒绝写入。
4. Agent 未读取已有文件就修改，拒绝写入并提示先读取。
5. Agent 新建文件时目标不存在，允许写入。
6. Agent 新建文件时目标已存在，拒绝写入。
7. Agent 写入成功后更新台账，连续编辑同一文件不误报冲突。

并发：

1. 两个用户基于同一旧版本同时保存同一文件，只允许一个成功。
2. Agent 和用户基于同一旧版本同时写同一文件，只允许一个成功。
