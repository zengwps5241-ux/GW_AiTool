# 团队空间功能模块技术设计

生成日期：2026-06-03  
关联 PRD：`design/goktech-agents/goktech-agents-prd.md`  
状态：Draft  
适用范围：团队空间成员管理、空间文件隔离、空间 lock、对话工作台空间切换、个人空间改造

## 1. 背景与目标

当前平台已经具备个人空间文件管理、文件上传队列、Office/PDF 转 Markdown、文件预览编辑、对话工作台和 Claude Agent 文件读写能力。团队空间要在这个基础上补齐多人协作能力：

1. 团队空间成员管理：团队空间内文件只对成员可见。
2. 团队空间成员权限：成员分为只读成员和编辑成员；只读成员只能查看、预览、下载和引用文件，编辑成员才具备写入资格。
3. 团队空间 lock：未加锁时编辑成员均可编辑；加锁后只有持锁人可以编辑和解锁。
4. Agent 权限继承人类用户权限：用户无编辑权限时，其对话中的 agent 也不能编辑团队空间文件。
5. 侧边栏新增团队空间入口：列表页展示空间卡片，详情页复用个人空间的文件管理、预览和编辑体验。
6. 团队空间维护：用户可创建空间；只有创建者/所有者可添加、编辑成员；所有者可转移给空间成员。
7. 新建会话时支持选择工作空间，默认个人空间，也可选择某个团队空间；该工作空间与 `ClaudeAgentOptions.cwd` 一致。

## 2. 现状梳理

### 2.1 个人空间路径

后端个人空间入口集中在：

- `backend/app/core/config.py`：`user_workspace(username)` 返回 `workspaces_dir/<username>`，并初始化 `.claude/skills/skill-creator`。
- `backend/app/api/routes/workspace.py`：所有文件树、预览、下载、编辑、新建、重命名、移动、删除都直接使用 `user_workspace(user.username)`。
- `backend/app/modules/workspace/*`：文件树、路径安全、预览、Markdown 索引等业务函数都以 `workspace: Path` 为入参，天然可以复用到团队空间。

这说明团队空间最小改造点不是重写文件模块，而是新增“空间上下文解析”，把 API 中固定的 `user_workspace(user.username)` 替换为可授权的 workspace root。

### 2.2 上传与转换任务

上传和转换当前按 `username` 归属：

- `upload_tasks` 表和 `/api/upload-tasks` 以 `username` 查询和创建任务。
- `conversion_tasks` 表和 `/api/conversion-tasks` 以 `username` 查询、去重、恢复 running 状态。
- `run_conversion_task()` 通过 `user_workspace(task.username)` 找回源文件。

团队空间若要支持上传和转换，必须把任务归属扩展为 `workspace_scope`，否则不同空间的同名文件和任务状态会混在一起。

### 2.3 对话工作台与 Agent 文件访问

当前会话固定使用个人空间：

- `ChatSession` 只有 `user_id / agent_id / claude_session_id / title`，没有空间字段。
- `stream_session_chat()` 固定 `ws = user_workspace(user.username)`。
- `stream_chat()` 把 `cwd`、权限 allow、sandbox allowWrite 都设置到该 workspace。
- 前端 `ChatWorkspace` 注释明确“智能体的 cwd 即用户工作区”。

团队空间需要落入会话创建模型。新建会话时选择工作空间，默认个人空间；选择团队空间后，该团队空间就是本会话的 `cwd`。会话创建后不建议切换工作空间，因为 Claude 历史、工具结果和相对路径都依赖同一个 cwd。

### 2.4 工具权限

当前 Claude hook 只做 Bash 黑名单：

- `backend/app/integrations/claude/guard.py` 只判断 Bash 命令是否在黑名单中。
- `_settings()` 和 sandbox 允许 `Write/Edit/MultiEdit` 写入当前 workspace。

因此团队 lock 不能只靠前端隐藏按钮，也不能只靠 HTTP 文件 API 校验。Agent 的 Write/Edit/MultiEdit/Bash 都必须进入后端 tool hook 或 SDK 权限配置。

### 2.5 前端复用点

前端个人空间已拆出可复用组件：

- `WorkspaceTree`
- `WorkspacePreview`
- `WorkspaceTaskDrawer`
- `useWorkspacePreview`
- `frontend/src/lib/workspace.ts`

`WorkspacePage` 目前直接调用 `api.workspaceTree()`、`api.workspaceSaveContent()` 等个人空间接口。团队空间详情页应复用这套组件，把数据源改为可配置的 workspace API client。

## 3. 核心设计原则

1. 权限在后端判定，前端只做状态展示和交互降级。
2. 文件能力只实现一套，HTTP 文件接口通过 `WorkspaceScope` 选择 root。
3. 成员角色是基础权限，lock 是编辑权限之上的互斥闸门；reader 即使持有会话也不能写，editor 在未 lock 或自己持锁时才能写。
4. Agent 权限等于发起对话的人类用户对会话绑定空间的权限。
5. 会话绑定一个工作空间；Agent 的 cwd、文件引用、上传目标和写权限都以会话绑定空间为准。
6. 首版只做空间级 lock 和 reader/editor 两级成员权限，不做文件级锁、多角色矩阵或细粒度 ACL。

## 4. 推荐方案：统一 WorkspaceScope 绑定会话 cwd

### 4.1 WorkspaceScope

新增统一空间上下文：

```python
@dataclass(frozen=True)
class WorkspaceScope:
    kind: Literal["personal", "team"]
    key: str
    root: Path
    display_name: str
    can_read: bool
    can_write: bool
    is_owner: bool = False
    locked_by_user_id: int | None = None
```

解析规则：

- `personal:<username>`：只有本人可读写，root 为 `workspaces_dir/<username>`。
- `team:<space_id>`：只有成员可读；`role='editor'` 的成员才有基础写权限；未 lock 时 editor 可写；已 lock 时仅持锁 editor 可写；所有者可管理成员和转移所有权。

HTTP 文件接口提供：

- `resolve_workspace_scope(db, user, kind, key) -> WorkspaceScope`
- `require_workspace_read(scope)`
- `require_workspace_write(scope)`
- `require_team_owner(space, user)`

文件 API、上传 API、转换 API 接收 scope，而不是直接从 username 推导路径。

Agent 对话接收固定 `WorkspaceScope`。`stream_chat()` 的 `ClaudeAgentOptions.cwd` 设置为 `scope.root`，前端给 agent 的附件路径保持相对路径。hook 不需要从路径反推出团队空间，只需要根据当前 scope 的 `can_write` 决定是否允许写工具。

### 4.2 路由形态

保留个人空间旧接口，新增团队空间接口。为了降低前端和后端改造风险，首版不强行把旧接口改成 query scope。

个人空间继续可用：

- `GET /api/workspace/tree`
- `PUT /api/workspace/content`
- `POST /api/workspace/file`
- `PATCH /api/workspace/file/rename`
- `PATCH /api/workspace/file/move`
- `DELETE /api/workspace/file`

新增团队空间文件接口：

- `GET /api/team-spaces`
- `POST /api/team-spaces`
- `GET /api/team-spaces/{space_id}`
- `PATCH /api/team-spaces/{space_id}`
- `DELETE /api/team-spaces/{space_id}`
- `GET /api/team-spaces/{space_id}/members`
- `POST /api/team-spaces/{space_id}/members`
- `PATCH /api/team-spaces/{space_id}/members/{user_id}`
- `DELETE /api/team-spaces/{space_id}/members/{user_id}`
- `POST /api/team-spaces/{space_id}/transfer-owner`
- `POST /api/team-spaces/{space_id}/lock`
- `DELETE /api/team-spaces/{space_id}/lock`
- `GET /api/team-spaces/{space_id}/workspace/tree`
- `GET /api/team-spaces/{space_id}/workspace/preview`
- `GET /api/team-spaces/{space_id}/workspace/markdown-preview`
- `GET /api/team-spaces/{space_id}/workspace/office-preview`
- `GET /api/team-spaces/{space_id}/workspace/download`
- `GET /api/team-spaces/{space_id}/workspace/download-markdown`
- `PUT /api/team-spaces/{space_id}/workspace/content`
- `POST /api/team-spaces/{space_id}/workspace/file`
- `PATCH /api/team-spaces/{space_id}/workspace/file/rename`
- `PATCH /api/team-spaces/{space_id}/workspace/file/move`
- `DELETE /api/team-spaces/{space_id}/workspace/file`

推荐用内部 helper 复用个人空间路由逻辑，避免复制业务实现：

```python
def workspace_tree_for_scope(scope: WorkspaceScope, conversion_meta: dict) -> list[WorkspaceNode]:
    require_workspace_read(scope)
    return get_workspace_tree(scope.root, conversion_meta)
```

### 4.3 数据模型

新增表 `team_spaces`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | SERIAL PK | 空间 ID |
| name | VARCHAR | 空间名称 |
| description | TEXT NULL | 空间描述 |
| owner_user_id | INTEGER FK users.id | 当前所有者 |
| created_by_user_id | INTEGER FK users.id | 创建者，审计用 |
| lock_holder_user_id | INTEGER NULL FK users.id | 当前持锁人 |
| lock_acquired_at | TIMESTAMP NULL | 加锁时间 |
| lock_note | TEXT NULL | 加锁说明 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

新增表 `team_space_members`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | SERIAL PK | 成员记录 ID |
| space_id | INTEGER FK team_spaces.id | 空间 |
| user_id | INTEGER FK users.id | 成员用户 |
| role | VARCHAR | 成员权限：`reader` 或 `editor` |
| added_by_user_id | INTEGER FK users.id | 添加人 |
| created_at | TIMESTAMP | 加入时间 |
| updated_at | TIMESTAMP | 更新时间 |

约束：

- `UNIQUE(space_id, user_id)`
- `team_space_members.role IN ('reader', 'editor')`
- `team_spaces.owner_user_id` 必须是该空间成员，且 owner 的成员角色必须是 `editor`。创建空间时自动插入 owner 成员，role 为 `editor`。
- 转移所有权只能转给已有成员。
- 转移所有权时，如果目标成员当前是 `reader`，事务内自动升级为 `editor`，否则新 owner 会无法编辑和管理空间。
- 删除成员时，如果删除的是 owner，必须先转移所有权。
- 持锁人被移出空间时，自动释放 lock。

扩展 `chat_sessions`：

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| workspace_kind | VARCHAR | `personal` | `personal` 或 `team` |
| team_space_id | INTEGER NULL | NULL | 团队空间会话绑定 |

约束：

- `workspace_kind='personal'` 时 `team_space_id IS NULL`。
- `workspace_kind='team'` 时 `team_space_id IS NOT NULL`。
- 创建团队空间会话时，当前用户必须是该空间成员。
- 会话创建后不支持修改 `workspace_kind/team_space_id`。如果用户要切换空间，应新建会话。

扩展任务表，推荐字段：

| 表 | 新字段 | 说明 |
| --- | --- | --- |
| upload_tasks | workspace_kind VARCHAR DEFAULT `personal` | 任务所属空间类型 |
| upload_tasks | team_space_id INTEGER NULL | 团队空间任务归属 |
| conversion_tasks | workspace_kind VARCHAR DEFAULT `personal` | 转换任务所属空间类型 |
| conversion_tasks | team_space_id INTEGER NULL | 团队空间任务归属 |

保留 `username` 作为发起人和兼容旧数据字段，不再把它当成唯一 workspace key。

### 4.4 团队空间目录

配置新增：

```python
team_workspaces_dir: Path = Path("team_workspaces")
```

团队空间 root：

```text
team_workspaces/<space_id>/
```

不建议使用空间名称作为目录名，避免重命名造成路径迁移。空间名称只存在数据库中。

初始化团队空间时创建：

```text
team_workspaces/<space_id>/
team_workspaces/<space_id>/.claude/skills/
team_workspaces/<space_id>/.markdown/
```

`.claude/skills/skill-creator` 是否复制到团队空间首版建议不复制。理由：团队空间是共享资产目录，允许 editor 在未 lock 时修改技能会带来团队级能力污染。需要团队技能时，应走后续“团队技能/插件授权”设计。

### 4.5 Lock 权限模型

#### 4.5.1 读写规则

读权限：

- 个人空间：本人可读。
- 团队空间：成员可读。

写权限：

- 个人空间：本人可写。
- 团队空间 reader：不可写，不可 lock，不可触发上传/转换/编辑。
- 团队空间 editor：未 lock 时可写。
- 团队空间 editor：已 lock 且自己是持锁人时可写。
- 团队空间 editor：已 lock 但持锁人为他人时不可写。

管理权限：

- 只有 owner 可编辑空间基础信息、添加成员、移除成员、调整成员角色、转移所有权。
- lock 的设置只允许 editor 执行；解除 lock 仅允许持锁人。为防止长期死锁，建议 admin 增加后门 API 或管理端能力，但首版 UI 不暴露。

#### 4.5.2 Lock API

`POST /api/team-spaces/{space_id}/lock`

请求：

```json
{
  "note": "正在整理交付文档"
}
```

行为：

- 非成员返回 404 或 403。建议 404，避免泄露空间存在。
- reader 调用返回 403，文案为“只读成员不能锁定团队空间”。
- 已被他人 lock 返回 409，返回持锁人名称和加锁时间。
- 未 lock 或当前用户已持锁则成功，返回空间详情。

`DELETE /api/team-spaces/{space_id}/lock`

行为：

- 只有持锁人可解除。
- 空间未 lock 时幂等成功。
- owner 不是持锁人时也不能解锁，除非后续增加 admin break-lock 能力。

### 4.6 Agent 写权限阻断

团队空间 lock 必须影响对话中的 agent。由于会话已绑定工作空间，正确做法是在会话启动时解析 `WorkspaceScope`，并把 `scope.root` 作为 `ClaudeAgentOptions.cwd`。`build_pre_tool_use_hooks()` 只根据当前 scope 的 `can_write` 拦截写工具，不拦截读工具。

读工具不需要业务 hook 拦截。进入团队空间会话的前提是当前用户是空间成员；所有成员都有读权限。业务 hook 只负责防止 reader 写入，以及防止非持锁 editor 在 lock 状态下写入。

#### 4.6.1 Hook 输入

`build_pre_tool_use_hooks()` 签名调整：

```python
def build_pre_tool_use_hooks(
    workspace: Path,
    *,
    can_write: bool,
    readonly_reason: str | None = None,
    agent_workdir: Path | None = None,
) -> list[HookMatcher]:
    ...
```

`can_write` 在启动会话 run 前由后端基于 `WorkspaceScope` 计算：

```python
def can_write_scope(scope: WorkspaceScope) -> bool:
    if scope.kind == "personal":
        return True
    if scope.member_role != "editor":
        return False
    return scope.locked_by_user_id is None or scope.locked_by_user_id == scope.current_user_id
```

#### 4.6.2 工具覆盖

写操作：

- `Write`
- `Edit`
- `MultiEdit`
- `NotebookEdit` 如果 SDK 暴露
- `Bash` 中可能写文件的命令或重定向。首版建议：当 `can_write=False` 时拒绝所有疑似写入 Bash；纯读取 Bash 仍受现有 Bash 黑名单约束。

#### 4.6.3 判定流程

每次 PreToolUse：

1. 只处理写工具或疑似写入的 Bash；读工具直接放行。
2. 如果 `can_write=True`，沿用现有 Bash 黑名单后放行。
3. 如果 `can_write=False`：
   - `Write/Edit/MultiEdit/NotebookEdit` 直接拒绝。
   - Bash 疑似写入时拒绝。
   - 拒绝文案使用 `readonly_reason`，例如“你是只读成员”或“空间已由张三锁定”。

拒绝文案：

```text
团队空间“客户试点资料”当前由 张三 锁定。你可以读取文件，但不能修改、删除、移动或创建文件。
```

#### 4.6.4 Runner 权限配置

`stream_chat()` 使用会话绑定的 `scope.root` 作为 `cwd`：

```python
options = ClaudeAgentOptions(
    cwd=str(scope.root),
    hooks={"PreToolUse": build_pre_tool_use_hooks(
        scope.root,
        can_write=scope.can_write,
        readonly_reason=scope.readonly_reason,
        agent_workdir=agent_workdir,
    )},
)
```

SDK settings/sandbox 建议：

- `Read(scope.root/**)` 始终允许。
- `Write/Edit/MultiEdit(scope.root/**)` 是否需要在 settings 中放开，取决于 SDK permissions 与 hook 的执行顺序：
  - 如果 permissions 先于 hook，仍需允许 `Write/Edit/MultiEdit(scope.root/**)`，再由 hook 做业务拒绝。
  - 如果 hook 先于 permissions，可以按更窄策略处理。
- sandbox `allowRead` 包含 `scope.root`。
- sandbox `allowWrite` 在 `can_write=True` 时包含 `scope.root`；如果 SDK 要求 hook 前必须有 sandbox 写权限，则可包含 `scope.root` 并依赖 hook 最终裁决。

lock 变化对新的 agent run 生效。一轮 run 启动后，`can_write` 按启动时的 scope 状态固定；如需实时生效，可以后续在 hook 中重新查询空间状态。

### 4.7 会话工作空间绑定

规则：

- `ChatSession` 增加 `workspace_kind/team_space_id`。
- 创建会话接口接收 `workspace_kind/team_space_id`，默认 `personal`。
- 创建团队空间会话时校验当前用户是空间成员。
- 会话创建后不支持切换工作空间。
- 会话列表、消息历史、运行中恢复、删除会话都使用会话绑定的 scope。
- 对话工作台中的文件树、上传、拖拽引用都跟随当前会话绑定 workspace。

历史读取和删除：

- `load_history()` 使用会话绑定 scope root。
- `remove_session()` 使用会话绑定 scope root。
- `stream_running_session()` 继续只允许会话 owner 访问。

### 4.8 文件 API 写权限闸门

以下接口必须调用 `require_workspace_write(scope)`：

- 上传任务创建和文件上传
- 保存文件内容
- 新建文件/文件夹
- 重命名
- 移动
- 删除
- 重新转换

以下接口只需要读权限：

- 文件树
- 预览
- 下载
- 下载 Markdown
- 转换任务列表
- 上传任务列表

转换任务的特殊规则：

- 创建转换任务是写操作，因为会写 `.markdown`。
- 已在队列中的转换任务如果空间后来被他人 lock，任务是否继续？
  - 推荐：继续执行。任务是由当时有写权限的用户显式触发，且队列运行中断会造成体验不确定。
  - 任务记录保留 `created_by_username` 或继续使用 `username` 作为发起人。

## 5. 前端设计

### 5.1 侧边栏

`ViewName` 新增：

```typescript
export type ViewName = ... | "teamSpaces";
```

Sidebar 主导航新增：

```text
主要
- 对话工作台
- 个人空间
- 团队空间
```

面包屑：

- 团队空间列表：`["团队空间", "空间列表"]`
- 团队空间详情：`["团队空间", space.name]`

### 5.2 团队空间列表页

新增 `TeamSpacesPage`：

主要区域展示空间卡片：

- 空间名称
- 描述
- owner
- 成员数量
- 文件更新时间或空间更新时间
- lock 状态：未加锁 / 已由某人加锁
- 当前用户权限：只读 / 可编辑 / 所有者

操作：

- 创建团队空间
- 点击卡片进入详情
- owner 可在卡片菜单中编辑名称、删除空间

空态：

- 未加入任何团队空间时，显示“暂无团队空间”，提供“创建团队空间”按钮。

### 5.3 团队空间详情页

新增 `TeamSpaceDetailPage`，布局建议：

```text
顶部栏：空间名称 / lock 状态 / 当前权限 / 加锁或解锁按钮 / 成员管理按钮
主体：复用 WorkspacePage 文件树 + 预览编辑 + 任务抽屉
```

文件管理部分不要复制 `WorkspacePage`，而是抽出通用组件：

```tsx
<WorkspaceFileManager
  scope={workspaceScope}
  api={workspaceApi}
  readonly={!space.can_write}
/>
```

`WorkspaceTree` 增加 `readonly?: boolean`：

- readonly 时隐藏或禁用上传、新建、重命名、移动、删除、重新转换。
- 拖拽上传和拖拽移动禁用。
- 右键菜单只保留预览、下载、下载 Markdown。

`WorkspacePreview` 增加 `readonly?: boolean`：

- readonly 时隐藏保存按钮或显示禁用态。
- 文本区域使用 readonly。
- mode 仍允许在预览/编辑视图切换，但编辑视图不可保存。

### 5.4 成员管理

owner 可打开成员管理弹窗或侧抽屉：

- 搜索用户：复用企业微信用户字段或本地 `users` 表。
- 添加成员，并选择权限：只读或可编辑，默认只读。
- 修改成员权限：`reader` 和 `editor` 互相切换。
- 移除成员。
- 转移所有权。

成员权限说明：

- `reader`：可查看文件树、预览、下载、拖拽引用给 agent；不能上传、新建、编辑、删除、移动、重命名、转换，也不能 lock。
- `editor`：具备基础写权限；未 lock 时可写，自己持锁时可写，被他人 lock 时只读。
- `owner`：不是单独的 member role，而是 `team_spaces.owner_user_id`；owner 必须同时是 `editor` 成员。

转移所有权流程：

1. owner 选择某个成员。
2. 二次确认：转移后只有新 owner 可管理成员。
3. 如果目标成员是 `reader`，后端事务内先升级为 `editor`。
4. 后端事务内更新 `team_spaces.owner_user_id`。
5. 原 owner 仍保留 `editor` 成员身份，除非新 owner 后续调整。

### 5.5 新建会话入口：智能体与工作空间下拉

调整对话入口页，把智能体选择和工作空间选择都改成下拉式控件：

```text
智能体：[默认智能体 v]
工作空间：[个人空间 v]
```

推荐交互：

- 智能体下拉：展示可用智能体，默认选择平台默认智能体或用户最近使用项。
- 工作空间下拉：默认“个人空间”；下拉中列出当前用户加入的团队空间，并显示权限标签：只读 / 可编辑 / 已锁定。
- 用户点击开始对话时，创建会话 payload 携带 `agent_id`、`workspace_kind`、`team_space_id`。
- 会话创建后，工作空间固定，不在同一会话内切换。用户要切换空间时新建会话。
- 进入会话后，文件树、上传、拖拽引用、预览和 agent cwd 都来自会话绑定 workspace。
- 如果绑定团队空间是 reader，文件面板固定只读；输入仍可发送，提示“你是只读成员，Agent 也只能读取该空间文件”。
- 如果绑定团队空间被他人 lock，文件面板只读；输入仍可发送，提示“该空间已锁定，Agent 可以读取文件，但不能写入”。

附件引用：

- 个人空间会话和团队空间会话都使用相对路径，因为 `cwd` 已经绑定到对应 workspace root。
- `composePromptWithAttachments()` 文案可继续使用“相对于当前工作目录”。

示例：

```text
[已引用文件]
- README.md: README.md
- 交付材料/方案.md: 交付材料/方案.md
```

## 6. API 与 Schema 草案

### 6.1 TeamSpace DTO

```typescript
export interface TeamSpace {
  id: number;
  name: string;
  description: string | null;
  owner_user_id: number;
  owner_name: string;
  member_count: number;
  locked_by_user_id: number | null;
  locked_by_name: string | null;
  lock_acquired_at: string | null;
  lock_note: string | null;
  member_role: "reader" | "editor";
  can_write: boolean;
  is_owner: boolean;
  created_at: string;
  updated_at: string;
}
```

成员 DTO：

```typescript
export interface TeamSpaceMember {
  id: number;
  user_id: number;
  username: string;
  display_name: string | null;
  role: "reader" | "editor";
  is_owner: boolean;
  added_by_user_id: number;
  created_at: string;
  updated_at: string;
}
```

### 6.2 ChatSession DTO

```typescript
export interface Session {
  id: string;
  title: string;
  agent_id: number | null;
  agent_name: string | null;
  workspace_kind: "personal" | "team";
  team_space_id: number | null;
  team_space_name: string | null;
  workspace_member_role: "reader" | "editor" | null;
  workspace_can_write: boolean;
  created_at: string;
  updated_at: string;
}
```

创建会话请求：

```typescript
export interface CreateSessionRequest {
  title?: string;
  agent_id?: number | null;
  workspace_kind?: "personal" | "team";
  team_space_id?: number | null;
}
```

默认值：

- `workspace_kind` 缺省为 `personal`。
- `workspace_kind='team'` 时必须提供 `team_space_id`，且当前用户必须是该空间成员。

### 6.3 通用 Workspace API client

前端建议封装：

```typescript
interface WorkspaceApi {
  tree(): Promise<WorkspaceNode[]>;
  tasks(limit?: number, offset?: number): Promise<WorkspaceTask[]>;
  saveContent(path: string, content: string): Promise<WorkspaceTextOut>;
  createItem(path: string, kind: "file" | "dir", content?: string): Promise<{ path: string }>;
  renameItem(path: string, newName: string): Promise<{ path: string }>;
  moveItem(path: string, targetDir: string): Promise<{ path: string }>;
  deleteItem(path: string): Promise<void>;
  previewUrl(path: string): string;
  markdownPreviewUrl(path: string): string;
  officePreviewUrl(path: string): string;
  downloadUrl(path: string): string;
  markdownDownloadUrl(path: string): string;
  retryConversion(path: string): Promise<ConversionTask>;
  createUploadTasks(targetDir: string, items: UploadTaskCreateItem[]): Promise<UploadTask[]>;
  uploadTaskFile(taskId: number, file: File, options: UploadOptions): Promise<UploadTask>;
}
```

个人空间和团队空间分别提供实现，`WorkspaceFileManager` 只依赖该 interface。

## 7. 后端实现拆分

### 7.1 模型与迁移

新增：

- `backend/app/models/team_space.py`
- `TeamSpace`
- `TeamSpaceMember`

更新：

- `backend/app/models/__init__.py`
- `backend/app/db/migrations.py`
- `backend/app/models/session.py`
- `backend/app/models/upload_task.py`
- `backend/app/models/conversion_task.py`

迁移重点：

- 旧 `chat_sessions` 默认 `workspace_kind='personal'`。
- 旧 `upload_tasks` / `conversion_tasks` 默认 `workspace_kind='personal'`。
- 为团队空间成员查询加索引：
  - `idx_team_space_members_user`
  - `idx_team_space_members_space`
  - `uq_team_space_members_space_user`
- 为任务按空间查询加索引：
  - `(workspace_kind, team_space_id, created_at)`
  - 保留旧 `(username, created_at)` 兼容个人任务。

### 7.2 模块

新增 `backend/app/modules/team_spaces/service.py`：

- `list_accessible_spaces(db, user)`
- `create_space(db, user, data)`
- `get_member_space(db, user, space_id)`
- `update_space(db, user, space_id, data)`
- `delete_space(db, user, space_id)`
- `list_members(db, user, space_id)`
- `add_member(db, owner, space_id, user_id, role)`
- `update_member_role(db, owner, space_id, user_id, role)`
- `remove_member(db, owner, space_id, user_id)`
- `transfer_owner(db, owner, space_id, user_id)`
- `lock_space(db, user, space_id, note)`
- `unlock_space(db, user, space_id)`

新增 `backend/app/modules/workspace/scope.py`：

- `personal_workspace_scope(user)`
- `team_workspace_scope(db, user, space_id)`
- `workspace_scope_for_session(db, user, cs)`
- `require_workspace_write(scope)`

### 7.3 路由

新增：

- `backend/app/api/routes/team_spaces.py`

更新：

- `backend/app/api/router.py` 注册 team spaces 路由。
- `sessions.py` 创建会话时接收 `workspace_kind/team_space_id`，chat/messages/delete/running 都按会话解析 scope。
- `upload_tasks.py` 支持团队空间路径或新增 team-space upload tasks 路由。
- `conversion_tasks.py` 支持团队空间 retry。
- `workspace_tasks.py` 支持团队空间任务列表。

### 7.4 Claude runner

更新签名：

```python
async def stream_chat(
    *,
    prompt: str,
    claude_session_id: str | None,
    workspace: WorkspaceScope,
    ...
)
```

`cwd` 使用 `workspace.root`。`build_pre_tool_use_hooks()` 使用 `workspace.can_write` 判断是否允许写工具。

## 8. 权限与错误语义

| 场景 | HTTP 状态 | 文案 |
| --- | --- | --- |
| 非成员访问空间 | 404 | 空间不存在 |
| 成员读取空间文件 | 200 | 正常 |
| reader 写入空间 | 403 | 只读成员不能编辑团队空间 |
| reader 加锁空间 | 403 | 只读成员不能锁定团队空间 |
| 非持锁人写入已 lock 空间 | 423 或 409 | 当前空间已由 {name} 锁定，暂不可编辑 |
| 非 owner 管理成员 | 403 | 只有空间所有者可以管理成员 |
| 转移给非成员 | 400 | 只能转移给当前空间成员 |
| 删除 owner 成员 | 409 | 请先转移空间所有权 |
| 将 owner 降级为 reader | 409 | 空间所有者必须保持可编辑权限 |
| 已被他人 lock 时再次 lock | 409 | 当前空间已被锁定 |

建议使用 `423 Locked` 表达 lock 场景；如果前端通用错误处理不支持，使用 `409 Conflict` 也可接受，但要用明确 detail 区分。

## 9. 备选方案

### 方案 A：最小可行，复制团队空间文件路由

摘要：保留个人空间原样，新增 `/api/team-spaces/{id}/workspace/*` 路由，内部直接调用现有 workspace service；会话创建时记录 `workspace_kind/team_space_id`，runner 按会话 scope 设置 cwd。

优点：

- 改动直观，首版上线最快。
- 不影响现有个人空间接口和前端页面。
- 容易按功能点拆 PR。

缺点：

- 上传、转换、对话会出现个人/团队两套分支。
- 后续项目资产库、知识库、团队技能复用时会继续膨胀。
- 权限逻辑容易遗漏某条接口。

复用：`workspace.service`、`WorkspaceTree`、`WorkspacePreview`。

### 方案 B：推荐，统一 WorkspaceScope 绑定会话 cwd

摘要：个人空间和团队空间都抽象为 `WorkspaceScope`。HTTP 文件能力、上传/转换任务、会话创建、Claude runner cwd、写权限 hook 都使用同一个 scope。

优点：

- 权限、路径、任务和对话 cwd 统一收口。
- 相对路径语义清晰，附件引用、历史读取和删除都跟随会话 cwd。
- 后续项目资产库、空间快照、Fork、知识库绑定都能复用 scope。
- 前端可以沉淀 `WorkspaceFileManager`，个人空间和团队空间体验一致。

缺点：

- 首版涉及数据模型、任务表、会话表、runner 和 tool hook，改造面更大。
- 会话创建后不能随意切换 workspace；用户要切换空间需要新建会话。

复用：现有 workspace modules、上传队列、转换任务、Claude runner 和前端 workspace 组件。

### 方案 C：轻量协作，团队空间只读共享 + 个人编辑 Fork

摘要：团队空间首版只做共享文件和成员可见，编辑必须先复制到个人空间，完成后再由 owner 合并。

优点：

- 几乎不需要 lock。
- 冲突风险低，适合审阅型资产库。
- Agent 权限更简单。

缺点：

- 不满足“团队空间内直接编辑”和“lock 持有人编辑”的明确需求。
- FDE 协作体验割裂，团队空间会变成只读资料柜。
- 合并流程会引入新的复杂度。

复用：下载、预览、复制文件能力。

推荐选择：方案 B。团队空间不是单个页面，而是未来团队共享、项目资产库、知识库、Agent 协作的底座。统一 `WorkspaceScope` 能让文件管理、上传转换、会话 cwd 和 Agent 权限使用同一套判定。

## 10. 分阶段实施计划

### Phase 1：数据模型与团队空间基础 API

- 新增 `TeamSpace` / `TeamSpaceMember`。
- 新增兼容迁移。
- 新增团队空间 CRUD、成员管理、所有权转移、lock/unlock API。
- 新增 `team_workspaces_dir` 配置。
- 后端测试覆盖 owner、reader、editor、非成员、转移所有权、lock 冲突。

验收：

- 用户能创建团队空间并自动成为 owner。
- owner 能添加/移除成员，并设置 reader/editor 权限。
- owner 能调整成员权限，但不能把当前 owner 降级为 reader。
- owner 能把所有权转给成员；如果目标是 reader，自动升级为 editor。
- editor 能 lock；reader 不能 lock；非持锁人不能 unlock。

### Phase 2：WorkspaceScope 与团队文件管理

- 新增 `workspace/scope.py`。
- 团队空间文件接口复用现有 workspace service。
- `WorkspaceTree` / `WorkspacePreview` 增加 readonly 支持。
- 新增 `TeamSpacesPage` 和 `TeamSpaceDetailPage`。
- 抽取 `WorkspaceFileManager` 复用个人空间页面。

验收：

- 非成员看不到团队空间。
- reader 和 editor 都可查看、预览、下载空间文件。
- reader 始终不能上传、编辑、删除文件。
- 未 lock 时 editor 可上传、编辑、删除文件。
- 被他人 lock 时前端进入只读态，后端写接口返回 lock 错误。

### Phase 3：上传、转换与任务归属

- `upload_tasks` / `conversion_tasks` 增加 workspace scope 字段。
- upload queue 支持不同 workspace API client。
- 团队空间上传后可在任务抽屉看到进度。
- 团队空间 Office/PDF 可转换并预览 Markdown。
- running 转换任务重启恢复时按 scope 找 workspace。

验收：

- 同一用户在个人空间和团队空间上传任务互不污染。
- 同名文件在不同团队空间的转换任务互不冲突。
- reader 不能创建上传/转换任务。
- lock 后非持锁 editor 不能创建新的上传/转换任务。

### Phase 4：新建会话入口与 Agent cwd 权限

- 新建会话入口将智能体选择改为下拉。
- 新建会话入口增加工作空间下拉，默认个人空间，可选择某个团队空间。
- `chat_sessions` 增加 `workspace_kind/team_space_id`。
- `stream_session_chat()` 按会话解析 `WorkspaceScope`。
- `stream_chat()` 使用 `scope.root` 作为 `ClaudeAgentOptions.cwd`。
- `build_pre_tool_use_hooks()` 基于 `scope.can_write` 拦截写工具。

验收：

- 新建会话默认绑定个人空间。
- 用户可在新建会话入口选择某个团队空间。
- 创建团队空间会话后，agent cwd 为该团队空间 root。
- reader 团队空间会话中，agent 可读但不能写。
- 未 lock 的 editor 团队空间会话中，agent 可以写。
- 被他人 lock 的团队空间会话中，agent 写工具被拒绝。
- 会话历史、运行中恢复、删除会话均使用绑定 scope root。

## 11. 测试计划

### 11.1 后端单元/API 测试

新增测试文件建议：

- `backend/tests/test_team_spaces_api.py`
- `backend/tests/test_team_workspace_api.py`
- `backend/tests/test_team_workspace_lock.py`
- `backend/tests/test_team_workspace_agent_hooks.py`

关键用例：

1. 创建空间自动创建 owner 成员，role 为 `editor`。
2. 非成员访问空间列表详情不可见。
3. owner 添加 reader 成员，reader 可以读取文件树但不能写。
4. 非 owner 添加成员返回 403。
5. owner 添加 editor 成员，editor 未 lock 时可以写。
6. owner 将 reader 升级为 editor 后，该成员获得写权限。
7. owner 不能把当前 owner 降级为 reader。
8. owner 转移给 reader 时，目标成员自动升级为 editor；旧 owner 不能再管理成员，新 owner 可以。
9. editor A lock 后，editor B 保存/删除/上传/转换返回 lock 错误。
10. reader 调用 lock 返回 403。
11. editor A lock 后，editor A 可以编辑并 unlock。
12. 持锁人被 owner 移出空间时 lock 自动释放。
13. 创建会话默认 `workspace_kind='personal'`。
14. 创建团队空间会话时，非成员返回 404/403。
15. 团队空间会话的 `stream_chat()` cwd 等于 `team_workspaces/<space_id>`。
16. reader 团队空间会话中，Claude hook 不拦截 `Read/Glob/Grep`，但拒绝 Write/Edit/MultiEdit/NotebookEdit 和疑似写 Bash。
17. lock 状态下，非持锁 editor 会话写工具被拒绝。
18. 删除团队空间会话时，`remove_session()` 使用会话绑定 scope root。

### 11.2 前端测试

现有前端测试较轻，建议补充纯函数和组件行为测试：

- 新建会话入口的智能体选择是下拉控件。
- 新建会话入口的工作空间选择是下拉控件，默认个人空间。
- 创建会话 payload 包含 `workspace_kind/team_space_id`。
- 团队空间会话中，文件拖拽引用生成相对路径。
- reader 文件面板固定只读，隐藏上传、新建、编辑、删除、转换入口。
- owner 成员管理可添加 reader/editor，并可调整成员权限。
- 团队空间 lock 状态映射为正确提示和按钮状态。
- upload queue 能对不同 workspace API client 创建任务。

### 11.3 手工验收脚本

1. 用户 A 创建团队空间“客户试点资料”。
2. 用户 A 添加用户 B。
3. 用户 B 登录，可在团队空间列表看到卡片。
4. 用户 A 上传 `访谈纪要.docx`，转换成功后可预览 Markdown。
5. 用户 B 在未 lock 时编辑 `README.md` 并保存。
6. 用户 A lock 空间。
7. 用户 B 刷新详情页，文件管理进入只读态。
8. 用户 B 新建会话，智能体下拉选择默认智能体，工作空间下拉选择“客户试点资料”。
9. 该会话内 agent cwd 为团队空间 root，读取 `README.md` 使用相对路径。
10. 用户 B 要求 agent 修改 `README.md`，由于空间被用户 A lock，hook 拒绝写工具。
11. 用户 A unlock。
12. 用户 B 新建或继续发起新一轮对话，要求 agent 修改 `README.md`，允许写入。

## 12. 风险与处理

### 12.1 运行中 agent 遇到 lock 变化

风险：agent 开始运行时某团队空间未 lock，运行中被其他成员 lock。

推荐首版处理：一次 agent run 的 `can_write` 在启动时按会话绑定 scope 计算并固定。lock 对新的 agent run 生效；已经开始的一轮 run 不做中途权限刷新。若业务要求 lock 立即阻断运行中的下一次工具调用，可后续把 hook 改为每次重新查询团队空间状态。

### 12.2 长期持锁导致团队无法编辑

风险：成员离线后长期持锁。

首版处理：

- 展示持锁人和加锁时间。
- owner 可以联系持锁人。
- 后端预留 admin break-lock service，但不在普通 UI 暴露。

后续增强：

- lock 过期时间。
- owner 申请解锁。
- 管理员审计解锁。

### 12.3 任务表兼容迁移复杂

风险：旧任务只有 username，新任务有 workspace scope。

处理：

- 旧数据迁移为 `workspace_kind='personal'`。
- 查询个人任务时同时兼容 `workspace_kind IS NULL OR workspace_kind='personal'`，待一次版本后清理兼容。

### 12.4 文件权限只在前端禁用

风险：用户直接调用 API 或 agent 工具绕过 UI。

处理：

- 所有写 API 后端统一 `require_workspace_write(scope)`。
- Claude Write/Edit/MultiEdit/Bash 写行为统一 hook 拦截。
- sandbox allowWrite 根据 lock 状态动态配置。

## 13. 不做事项

首版不做：

- 文件级 lock。
- 超出 reader/editor 的多角色权限矩阵。
- 团队空间对话历史共享。
- 团队空间内技能/插件管理。
- 空间快照 Release/Fork。
- lock 自动过期。
- 多人实时协同编辑。

这些能力都可以基于 `WorkspaceScope + TeamSpace` 后续扩展。

## 14. 成功标准

1. 成员隔离：非成员无法通过列表、详情、文件 API 或创建团队空间会话访问团队空间。
2. 文件能力：团队空间支持个人空间已有的上传、下载、删除、建文件夹、预览、编辑、转换。
3. Lock 生效：被他人 lock 时，用户和绑定该空间会话中的 agent 都不能写该团队空间文件。
4. 会话绑定：新建会话可选择个人空间或某个团队空间，`ClaudeAgentOptions.cwd` 与会话绑定 workspace root 一致。
5. 所有权：创建者/owner 能维护成员并转移所有权。
6. 兼容性：旧个人空间、旧会话、旧上传/转换任务不受影响。

## 15. 后续演进

团队空间落地后，可继续承接 PRD 中的团队共享主线：

- 团队空间发布只读资产快照 Release。
- 从项目资产库 Fork 到团队空间。
- 团队空间绑定知识库/RAG 任务。
- Agent 团队共享同一个团队空间上下文。
- 空间级审计日志：谁上传、谁编辑、谁 lock、哪个 agent 修改了哪个文件。
- 按部门或角色批量授权团队空间。
