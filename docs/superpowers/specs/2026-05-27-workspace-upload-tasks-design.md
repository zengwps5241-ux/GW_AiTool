# 个人空间异步上传任务设计

## 背景

当前个人空间上传使用一次 `multipart/form-data` 请求保存多个文件。上传大文件或多文件时，容易出现请求时间长、失败后缺少任务状态、右侧转换任务列表无法展示上传进度等问题。

本设计将个人空间上传改为后端持久化上传任务，并把右侧“转换任务”列表升级为通用任务列表。第一版不做失败重试和断点续传。

## 目标

- 上传任务后端持久化，状态包括 `queued`、`running`、`succeeded`、`failed`。
- 同一用户全局同时只允许 1 个上传任务处于 `running`。
- 多文件上传时，前端按任务串行上传，其他任务等待。
- 上传中的文件在右侧任务列表显示进度。
- 上传成功和失败任务都保留在历史任务列表中。
- 右侧任务列表统一展示上传任务和转换任务，并能区分任务类型。
- 上传成功后，保持现有行为：Office/PDF 等可转换文件自动创建并调度转换任务。
- 如果页面存在等待中或上传中的上传任务，刷新或关闭浏览器时提示用户可能丢失状态；用户仍然离开后，未完成上传任务标记失败。

## 非目标

- 第一版不支持失败重试按钮。
- 第一版不支持分片上传、断点续传、刷新后恢复本地文件内容。
- 不重构现有 `conversion_tasks` 表。
- 不删除旧 `/api/uploads` 接口，以免影响个人空间以外的上传入口。

## 方案

采用独立上传任务表 + 后端聚合 API 的方案。

保留现有转换任务表和转换队列，新建 `upload_tasks` 表。右侧列表不再直接消费 `ConversionTask[]`，而是消费新的统一任务结构 `WorkspaceTask[]`。后端通过 `/api/workspace-tasks` 合并上传任务和转换任务，按创建时间倒序分页返回。

## 后端设计

### 数据模型

新增 `UploadTask` ORM 模型和 `upload_tasks` 表：

- `id`
- `username`
- `target_dir`
- `relative_path`
- `filename`
- `status`: `queued`、`running`、`succeeded`、`failed`
- `progress`: 0-100
- `size`
- `saved_path`
- `error_message`
- `created_at`
- `started_at`
- `finished_at`
- `updated_at`

索引：

- `(username, created_at)`
- `(username, status)`
- `status`

数据库初始化迁移在 `app/db/migrations.py` 中兼容创建表和索引。

### 上传任务接口

新增路由建议放在 `backend/app/api/routes/upload_tasks.py`。

`POST /api/upload-tasks`

批量创建上传任务。请求包含：

- `target_dir`
- `items`: 每个文件的 `filename`、`relative_path`、`size`

后端负责：

- 校验路径安全。
- 计算安全目标路径。
- 对目标路径做去重。
- 创建 `queued` 上传任务。
- 返回任务列表。

`POST /api/upload-tasks/{id}/file`

上传某个任务对应的文件。

后端负责：

- 校验任务属于当前用户。
- 校验任务状态可上传。
- 用数据库条件更新抢占任务为 `running`。
- 检查同一用户没有其他 `running` 上传任务。
- 使用同目录 `.filename.uploading*` 临时文件写入。
- 写入成功后原子替换到最终路径。
- 成功时标记 `succeeded`、`progress=100`、记录 `saved_path` 和 `size`。
- 失败时删除临时文件并标记 `failed`。
- 上传成功后，如果文件属于现有可转换类型，创建并调度转换任务。若转换任务已存在，不让上传任务失败。

`PATCH /api/upload-tasks/{id}/progress`

前端节流同步上传进度。后端只允许更新当前用户、`running` 状态任务的 `progress`。

`POST /api/upload-tasks/abandon`

页面刷新或关闭前由前端尽力调用。请求包含当前页面创建且未完成的上传任务 ID。后端将这些任务中属于当前用户且状态为 `queued` 或 `running` 的记录标记为 `failed`，错误文案为“页面刷新导致上传中断，请重新上传”。

### 通用任务接口

新增路由建议放在 `backend/app/api/routes/workspace_tasks.py`。

`GET /api/workspace-tasks?limit=10&offset=0`

返回统一任务列表：

```json
{
  "type": "upload",
  "id": 1,
  "name": "report.pdf",
  "path": "docs/report.pdf",
  "status": "running",
  "progress": 62,
  "error_message": null,
  "created_at": "...",
  "started_at": "...",
  "finished_at": null
}
```

转换任务映射为：

- `type`: `conversion`
- `name`: `source_name`
- `path`: `source_path`
- `status`: 原转换状态
- `progress`: `null`

上传任务映射为：

- `type`: `upload`
- `name`: `filename`
- `path`: `saved_path` 或预期目标路径
- `status`: 上传状态
- `progress`: 上传进度

列表按 `created_at` 倒序混排。分页第一版可在内存合并后排序分页，也可用 SQL `UNION ALL` 优化；实现时优先选择清晰、测试可靠的方式。

### 并发控制

同一用户全局只允许一个上传任务运行。`POST /api/upload-tasks/{id}/file` 开始时执行原子条件更新：

- 目标任务状态必须是 `queued`。
- 当前用户不能已有其他 `running` 上传任务。

如果多窗口并发触发，后端返回冲突响应，前端可稍后刷新任务列表。正常单页面队列不会触发冲突。

### 页面刷新后的中断处理

浏览器刷新后无法恢复本地 `File` 对象。因此：

- 前端在刷新前尽力调用 abandon 接口。
- 后端将未完成任务标记失败。
- 为防止 abandon 没发出去，`GET /api/workspace-tasks` 或后台清理逻辑可以把长时间未更新的 `running` 上传任务标记失败。

## 前端设计

### 上传队列

个人空间页面上传流程：

1. 用户选择文件/文件夹或拖拽文件。
2. 前端调用 `POST /api/upload-tasks` 创建任务。
3. 前端把返回的任务放入本页上传队列。
4. 队列同一时间只启动一个任务。
5. 当前任务使用 `XMLHttpRequest` 上传到 `/api/upload-tasks/{id}/file`。
6. `xhr.upload.onprogress` 更新本地任务进度，并节流调用进度同步接口。
7. 当前任务成功或失败后，自动启动下一个等待任务。
8. 每次任务状态变化后刷新文件树和通用任务列表。

### 离开页面提示

当本页存在状态为 `queued` 或 `running` 的上传任务时：

- 注册 `beforeunload`，触发浏览器原生离开提示。
- 用户仍然离开时，用 `navigator.sendBeacon` 或 `fetch(..., { keepalive: true })` 调用 abandon 接口。

### 通用任务列表

将 `ConversionTaskDrawer` 改为 `WorkspaceTaskDrawer`：

- 标题为“任务”。
- 任务按创建时间倒序混排。
- 每条任务显示类型标签：`上传` 或 `转换`。
- 主标题显示文件名，副标题显示路径。
- 状态文案：
  - `queued`: 等待中
  - `running`: 上传中 / 转换中
  - `succeeded`: 已完成
  - `failed`: 失败
- 上传任务显示进度条和百分比。
- 转换任务不显示进度条。
- 失败任务显示错误原因。
- 保留刷新、加载更多、收起/展开。
- 第一版不提供上传失败重试按钮。
- 转换失败重试入口保留在文件预览区，右侧列表第一版不放操作按钮。

## 兼容性

- 旧 `/api/uploads` 接口保留，避免影响聊天上传或其他上传入口。
- 个人空间页面切换到新的上传任务接口。
- 现有转换任务接口保留，文件预览里的转换重试继续使用。
- 右侧列表改用 `/api/workspace-tasks`。

## 测试计划

后端测试：

- 批量创建上传任务。
- 单文件上传成功并落盘。
- 上传失败时任务状态为 `failed`，临时文件被清理。
- 同一用户同时只能有一个 `running` 上传任务。
- abandon 接口将等待中/上传中任务标记失败。
- 上传成功后自动创建转换任务。
- 通用任务接口能合并上传任务和转换任务，并按时间排序。

前端测试/验证：

- 上传任务状态映射和类型标签渲染。
- 上传队列串行执行。
- 上传进度更新。
- 存在等待中/上传中任务时注册离开提示。
- 通用任务列表展示上传/转换混排。
- `npm run build` 通过。

## 开放问题

无。失败重试和断点续传明确不在第一版范围内。
