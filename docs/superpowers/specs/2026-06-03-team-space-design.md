# 团队空间功能模块设计

生成日期：2026-06-03
状态：Draft
关联 PRD：`design/goktech-agents/goktech-agents-prd.md`

## 1. 背景

当前平台已经具备个人空间文件管理、文件上传队列、Office/PDF 预览与 Markdown 转换、文件预览编辑、会话工作台布局和 Claude Agent 文件读写能力。PRD 中的团队空间能力需要在现有个人空间基础上补齐多人文件协作，并让绑定团队空间的会话成为团队成员可共享的工作记录。

本设计采用“团队空间作为共享工作域”的边界：

- 团队空间共享文件，也共享绑定该团队空间的会话历史。
- 会话创建时需要绑定一个工作空间，默认个人空间，也可绑定某个团队空间。
- 个人空间会话只对创建者可见；团队空间会话对该空间当前成员可见。
- 会话绑定的工作空间就是 Agent 运行时 `ClaudeAgentOptions.cwd` 的来源。
- Agent 的文件读写权限继承发起对话的人类用户在会话绑定工作空间中的权限。

## 2. 目标

1. 支持团队空间成员管理，团队空间内文件只对成员可见。
2. 支持成员权限，成员分为只读成员和编辑成员；只读成员只能查看、预览、下载和引用文件，编辑成员才具备写入资格。
3. 支持空间级 lock，避免多人和 agent 同时编辑造成冲突。
4. 支持创建者/所有者维护团队空间、管理成员，并将所有权转移给某个成员。
5. 在侧边栏新增团队空间入口，列表页以卡片展示团队空间，详情页复用个人空间的文件管理、预览和编辑体验。
6. 去掉独立对话工作台入口，把会话列表融入个人空间和团队空间；个人空间默认进入个人会话界面，团队空间卡片提供团队会话入口。
7. 保持个人空间旧能力兼容，避免重写文件管理、预览、转换和上传模块。

## 3. 非目标

1. 不做文件级 lock、多人实时协同编辑或版本合并。
2. 不做复杂角色矩阵，首版只区分 owner、reader、editor；owner 是空间所有权，不是独立 member role。
3. 不把团队空间发布为资产快照；该能力归属后续项目资产库设计。
4. 不做跨团队空间搜索、审计报表和管理员强制解锁界面。
5. 不做会话内多人同时编辑同一条消息；团队共享会话只共享历史和后续追加消息。

## 4. 现状梳理

### 4.1 个人空间路径

个人空间入口当前集中在：

- `backend/app/core/config.py`：`user_workspace(username)` 返回个人空间 root。
- `backend/app/api/routes/workspace.py`：文件树、预览、下载、编辑、新建、重命名、移动、删除都直接使用 `user_workspace(user.username)`。
- `backend/app/modules/workspace/*`：文件树、路径安全、预览、Markdown 索引等函数都以 `workspace: Path` 为入参。

这说明文件能力天然可复用，团队空间不需要重写文件模块，关键是新增空间上下文解析和权限闸门。

### 4.2 上传与转换任务

上传和转换当前以 `username` 作为用户归属，并通过 `user_workspace(task.username)` 找回源文件。团队空间如果继续只用 `username`，会导致不同空间的同名文件、任务列表和转换状态混在一起。因此上传任务和转换任务需要增加空间归属字段。

### 4.3 空间会话界面与 Agent cwd

当前 `stream_session_chat()` 固定把 `user_workspace(user.username)` 作为 agent cwd。前端 `ChatWorkspace` 也默认“智能体的 cwd 即用户工作区”。团队空间能力需要把 cwd 从固定个人空间改为“会话绑定工作空间 root”。

会话创建时必须绑定一个工作空间。个人空间会话仍归创建者所有；团队空间会话归属绑定的团队空间，并对该空间当前成员可见。该绑定用于恢复和继续对话时确定 `ClaudeAgentOptions.cwd`、文件引用来源、上传目标、会话可见性和权限。

### 4.4 Agent 写权限

当前 Claude hook 主要限制 Bash 黑名单，SDK settings 和 sandbox 会允许 agent 在个人空间内写文件。团队空间 lock 不能只靠前端隐藏按钮，也不能只靠 HTTP 文件 API 校验。Agent 写权限必须同时落在：

- 会话流式运行前的空间权限解析。
- Claude SDK tool permissions。
- sandbox allowWrite。
- PreToolUse hook 对 Write/Edit/MultiEdit/Bash 的拦截。

## 5. 推荐方案

采用方案 A：统一 `WorkspaceScope`，把个人空间和团队空间都建模成文件空间域。

团队空间管理共享文件、共享会话、成员、owner 和 lock。新建会话绑定工作空间后，后端解析出当前用户在该空间中的读写权限，并据此设置 `ClaudeAgentOptions.cwd`、控制 HTTP 文件 API 与 agent 工具权限。

### 5.1 核心原则

1. 权限由后端判定，前端只负责展示状态和禁用交互。
2. 文件管理能力只实现一套，个人空间和团队空间通过 `WorkspaceScope` 选择 root。
3. 成员角色是基础权限，lock 是编辑权限之上的互斥闸门；reader 即使持有会话也不能写，editor 在未 lock 或自己持锁时才能写。
4. Lock 是空间级写权限闸门，不影响成员读文件、预览、下载和 agent 读取。
5. Agent 权限等于发起对话的人类用户在会话绑定工作空间中的权限。
6. 个人空间会话只对创建者可见；团队空间会话对该空间当前成员共享。
7. 团队共享会话中，每轮 agent run 的写权限按发送该轮消息的成员在会话绑定空间中的权限计算。
8. 首版只做空间级 lock 和 reader/editor 两级成员权限，避免权限模型过早复杂化。

## 6. 权限模型

### 6.1 角色

- owner：团队空间当前所有者。可编辑空间信息、添加成员、移除成员、转移所有权、删除空间。
- reader：只读成员。可查看文件树、预览、下载、拖拽引用给 agent；不能上传、新建、编辑、删除、移动、重命名、转换，也不能 lock。
- editor：编辑成员。具备基础写权限；未 lock 时可写，自己持锁时可写，被他人 lock 时只读。

owner 不是单独的成员角色，而是 `team_spaces.owner_user_id`。owner 必须同时是 editor。创建空间时，创建者自动成为 owner 和 editor。所有权转移后，原 owner 保留 editor 身份，除非新 owner 后续调整。

### 6.2 可见性

团队空间文件、空间详情、成员列表、转换任务和上传任务只对成员可见。非成员访问空间资源时建议返回 404，降低空间存在性泄露。

### 6.3 写权限

- reader：始终不可写，不可 lock。
- editor 未 lock：可写。
- editor 已 lock 且自己是持锁人：可写。
- editor 已 lock 但持锁人为他人：不可写。
- 非成员：不可读、不可写。

写权限包括：

- 上传文件。
- 保存文件内容。
- 新建文件或文件夹。
- 重命名、移动、删除。
- 重新转换 Office/PDF 到 Markdown。
- Agent 通过 Write/Edit/MultiEdit/Bash 等工具修改空间文件。

### 6.4 Lock 规则

- editor 可在未 lock 时设置 lock。
- reader 调用 lock 返回 403。
- 持锁人可解除 lock。
- 已由他人持锁时，其他 editor 设置 lock 返回 409，并返回持锁人、加锁时间和 lock 说明。
- owner 不是持锁人时，首版也不能解除普通 lock，以保持“谁持锁谁编辑”的清晰规则。
- 持锁人被移出空间时，后端自动释放 lock。
- 管理员强制解锁可作为后续管理端能力，首版不在用户界面暴露。

## 7. 后端设计

### 7.1 数据模型

新增 `team_spaces`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | 空间 ID |
| name | VARCHAR | 空间名称 |
| description | TEXT NULL | 空间描述 |
| owner_user_id | INTEGER FK users.id | 当前所有者 |
| created_by_user_id | INTEGER FK users.id | 创建者，审计用 |
| lock_holder_user_id | INTEGER NULL FK users.id | 当前持锁人 |
| lock_acquired_at | TIMESTAMP NULL | 加锁时间 |
| lock_note | TEXT NULL | 加锁说明 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

新增 `team_space_members`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | 成员记录 ID |
| space_id | INTEGER FK team_spaces.id | 团队空间 |
| user_id | INTEGER FK users.id | 成员用户 |
| role | VARCHAR | `reader` 或 `editor` |
| added_by_user_id | INTEGER FK users.id | 添加人 |
| created_at | TIMESTAMP | 加入时间 |
| updated_at | TIMESTAMP | 更新时间 |

约束：

- `UNIQUE(space_id, user_id)`。
- `team_space_members.role IN ('reader', 'editor')`。
- owner 必须是该空间成员，且 owner 的成员角色必须是 `editor`。
- 转移所有权只能转给已有成员。
- 转移所有权时，如果目标成员当前是 `reader`，事务内自动升级为 `editor`，否则新 owner 会无法编辑和管理空间。
- 删除 owner 前必须先转移所有权。
- 将 owner 降级为 `reader` 返回 409。
- 持锁人被移出空间时，自动释放 lock。

扩展 `upload_tasks` 和 `conversion_tasks`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| workspace_kind | VARCHAR | `personal` 或 `team` |
| team_space_id | INTEGER NULL | 团队空间任务归属 |

保留 `username` 作为任务发起人和旧数据兼容字段，不再把它作为唯一 workspace key。

扩展 `chat_sessions`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| workspace_kind | VARCHAR | 会话绑定的工作空间类型，默认 `personal` |
| team_space_id | INTEGER NULL | 绑定团队空间时的空间 ID |
| user_id | INTEGER FK users.id | 会话创建者；个人空间会话用作 owner，团队空间会话用作 creator |

`workspace_kind/team_space_id` 同时决定会话可见性和运行工作目录：

- `workspace_kind='personal'`：会话只对 `user_id` 对应创建者可见。
- `workspace_kind='team'`：会话归属于 `team_space_id`，对该团队空间当前成员可见。
- 已创建会话不支持直接切换绑定空间，避免 Claude 历史里的相对路径、工具结果和文件引用失真；用户需要切换工作空间时应新建会话。
- 团队空间会话由不同成员继续发送消息时，每轮 run 按当前发送者在该空间的 reader/editor、lock 状态计算写权限。

团队共享会话需要保留消息发送者：

| 对象 | 新字段 | 说明 |
| --- | --- | --- |
| chat_messages | created_by_user_id INTEGER NULL | 用户消息的发送者；旧数据可为空 |
| run_state / usage event | actor_user_id INTEGER NULL | 触发本轮 agent run 的成员，用于权限、审计和展示 |

前端展示团队空间会话时，用户消息旁显示发送者名称。个人空间会话可以不展示发送者。

### 7.2 WorkspaceScope

新增 `backend/app/modules/workspace/scope.py`：

```python
@dataclass(frozen=True)
class WorkspaceScope:
    kind: Literal["personal", "team"]
    key: str
    root: Path
    display_name: str
    can_read: bool
    can_write: bool
    member_role: Literal["reader", "editor"] | None = None
    is_owner: bool = False
    locked_by_user_id: int | None = None
    readonly_reason: str | None = None
```

核心函数：

- `resolve_workspace_scope(db, user, kind, team_space_id=None) -> WorkspaceScope`
- `require_workspace_read(scope)`
- `require_workspace_write(scope)`
- `require_team_owner(db, user, space_id)`

个人空间规则：

- `kind=personal` 时 root 为 `user_workspace(user.username)`。
- 只有本人可读写。

团队空间规则：

- `kind=team` 时 root 为 `team_workspaces/<space_id>`。
- 成员可读。
- `reader` 不可写。
- `editor` 在未 lock 时可写。
- `editor` 在已 lock 且自己是持锁人时可写。
- `readonly_reason` 需要区分“只读成员”和“空间已由某人锁定”，供 HTTP 错误和 agent hook 复用。

### 7.3 团队空间目录

配置新增：

```python
team_workspaces_dir: Path = Path("team_workspaces")
```

目录结构：

```text
team_workspaces/<space_id>/
team_workspaces/<space_id>/.markdown/
```

空间目录使用 ID 而不是名称，避免空间重命名导致文件迁移。首版不复制个人空间中的 `.claude/skills/skill-creator`，避免团队空间被当成共享技能开发目录。

### 7.4 API

新增团队空间管理 API：

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

新增团队空间文件 API，内部复用现有 workspace service：

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

个人空间旧 API 保持兼容：

- `GET /api/workspace/tree`
- `PUT /api/workspace/content`
- 其他现有个人空间接口保持原语义。

会话 API 调整：

- 创建会话请求接收 `workspace_kind` 和 `team_space_id`，默认 `workspace_kind='personal'`。
- `workspace_kind='team'` 时必须提供 `team_space_id`，且当前用户必须是该空间成员。
- 会话创建后不支持修改 `workspace_kind/team_space_id`。
- 会话列表按入口空间过滤：个人空间入口只返回当前用户个人会话；团队空间会话入口返回该空间全部团队会话。
- 团队空间会话详情、消息历史、运行中恢复对当前空间成员可见。
- 团队空间会话发送消息前校验当前用户仍是空间成员。
- 同一团队空间会话同一时刻只允许一个 agent run；已有 run 进行中时，其他成员只能查看实时状态，不能再次发送。
- 团队空间会话重命名和删除首版限定为会话创建者或空间 owner。
- `load_history()`、`remove_session()`、`stream_running_session()` 使用会话绑定的 `WorkspaceScope` root；团队空间会话的历史目录位于团队空间 root 下。

### 7.5 文件 API 权限闸门

只读接口调用 `require_workspace_read(scope)`：

- 文件树。
- 预览。
- 下载。
- 下载 Markdown。
- 上传任务列表。
- 转换任务列表。

写接口调用 `require_workspace_write(scope)`：

- 上传任务创建。
- 文件上传。
- 保存内容。
- 新建文件或文件夹。
- 重命名。
- 移动。
- 删除。
- 重新转换。

转换任务创建是写操作，因为它会写入 `.markdown`。如果任务创建时用户有写权限，但任务执行期间空间被他人 lock，首版允许任务继续执行，避免队列状态不可预测。

### 7.6 Agent 权限控制

`stream_session_chat()` 在发起运行时根据会话绑定的工作空间解析 `WorkspaceScope`，并把 `scope.root` 设置为 `ClaudeAgentOptions.cwd`，同时把 `scope.can_write` 传给 Claude runner。

可写时：

- 允许 `Read/Write/Edit/MultiEdit` 访问空间 root。
- sandbox allowWrite 包含空间 root。
- Bash 仍受现有安全黑名单约束。

只读时：

- 只允许读取空间 root。
- 不允许 `Write/Edit/MultiEdit/NotebookEdit`。
- sandbox allowWrite 不包含空间 root。
- PreToolUse hook 拒绝写工具。
- Bash 采用只读策略，拒绝明显写入类命令和重定向；首版可在只读空间中直接拒绝 Bash，以降低绕过风险。

系统提示词同时说明当前空间只读，但提示词只作为体验辅助，真正权限以 hook、settings 和 sandbox 为准。

`build_pre_tool_use_hooks()` 签名建议调整为：

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

判定流程：

1. 读工具直接放行。
2. `can_write=True` 时，写工具放行；Bash 仍走现有黑名单。
3. `can_write=False` 时，`Write/Edit/MultiEdit/NotebookEdit` 直接拒绝。
4. `can_write=False` 时，Bash 疑似写入、删除、移动、复制、创建文件或使用重定向时拒绝；纯读取 Bash 仍走现有黑名单。
5. 拒绝文案使用 `readonly_reason`，例如“你是只读成员”或“空间已由张三锁定”。

Runner 权限配置：

- `Read(scope.root/**)` 始终允许。
- `Write/Edit/MultiEdit(scope.root/**)` 是否需要在 SDK settings 中放开，取决于 SDK permissions 与 hook 的执行顺序；如果 permissions 先于 hook，仍需允许写工具进入 hook，再由 hook 做业务拒绝。
- sandbox `allowRead` 包含 `scope.root`。
- sandbox `allowWrite` 在 `can_write=True` 时包含 `scope.root`；如果 SDK 要求 hook 前必须有 sandbox 写权限，可包含 `scope.root` 并依赖 hook 最终裁决。

lock 变化对新的 agent run 生效。一轮 run 启动后，`can_write` 按启动时的 scope 状态固定；如需 lock 立即阻断运行中下一次工具调用，可后续在 hook 中重新查询团队空间状态。

## 8. 前端设计

### 8.1 侧边栏

侧边栏去掉独立“对话工作台”入口。空间成为会话和文件的统一入口：

```text
个人空间
团队空间
```

`ViewName` 保留或新增：

- `personalSpace`：默认展示个人会话界面。
- `personalSpaceDetail`：个人空间文件详情页。
- `teamSpaces`：团队空间卡片列表页。
- `teamSpaceChat`：某个团队空间的团队会话界面。
- `teamSpaceDetail`：某个团队空间文件详情页。

### 8.2 团队空间列表页

新增 `TeamSpacesPage`，以卡片展示当前用户加入的团队空间：

- 空间名称。
- 描述。
- owner。
- 成员数量。
- 更新时间。
- lock 状态。
- 当前用户权限：所有者、可编辑、只读。

- 对话图标按钮：进入该团队空间的团队会话界面。
- 详情/进入按钮：进入该团队空间文件详情页。

用户可以创建团队空间。owner 可以编辑空间名称/描述和删除空间。点击卡片主体默认进入团队空间详情页；点击对话图标进入团队会话界面，避免卡片点击行为歧义。

### 8.3 个人空间会话界面与详情页

点击侧边栏“个人空间”菜单，默认进入个人会话界面。该界面复用当前对话工作台布局：

```text
左侧：个人会话列表，按智能体分组
中间：消息流和输入区
右侧：个人空间文件面板
```

个人空间会话界面规则：

- 左侧只展示当前用户个人会话。
- 会话列表按智能体分组，不按时间分组；组内按 `updated_at` 倒序。
- 点击 `+ 新建` 后选择智能体，在个人空间下创建会话。
- 右侧文件面板 title 显示“个人空间”。
- “个人空间”标题右侧放一个“进入”图标按钮，点击跳转到个人空间详情页。
- 右侧文件面板仍支持浏览、拖拽引用、上传和预览；具体写权限沿用个人空间权限。

个人空间详情页复用 `WorkspaceFileManager` 的完整文件管理体验。详情页顶部或右上角提供“会话列表”入口，点击回到个人空间会话界面。

### 8.4 团队空间详情页

新增 `TeamSpaceDetailPage`：

```text
顶部：空间名称、lock 状态、当前权限、加锁/解锁按钮、成员管理入口、会话列表入口
主体：文件树、预览/编辑区、上传与转换任务抽屉
```

文件管理部分抽出通用组件：

```tsx
<WorkspaceFileManager
  scope={workspaceScope}
  api={workspaceApi}
  readonly={!space.can_write}
/>
```

个人空间页和团队空间详情页都使用该组件。团队空间只读时：

- 禁用上传、新建、保存、重命名、移动、删除和重新转换。
- 拖拽上传和拖拽移动不可用。
- 右键菜单只保留预览、下载、下载 Markdown。
- 编辑视图可打开但内容不可保存，或直接进入只读文本模式。
- “会话列表”入口返回该团队空间的团队会话界面。

### 8.5 成员管理

owner 可打开成员管理抽屉：

- 搜索用户。
- 添加成员，并选择权限：只读或可编辑，默认只读。
- 修改成员权限：`reader` 和 `editor` 互相切换。
- 移除成员。
- 转移所有权。

成员权限说明：

- `reader`：可查看文件树、预览、下载、拖拽引用给 agent；不能上传、新建、编辑、删除、移动、重命名、转换，也不能 lock。
- `editor`：具备基础写权限；未 lock 时可写，自己持锁时可写，被他人 lock 时只读。
- `owner`：不是单独的 member role，而是 `team_spaces.owner_user_id`；owner 必须同时是 `editor` 成员。

转移所有权需要二次确认。后端在事务内更新 owner；如果目标成员是 `reader`，后端先升级为 `editor`。原 owner 保留 `editor` 成员身份，除非新 owner 后续调整。

### 8.6 团队空间会话界面

用户从团队空间卡片的对话图标进入团队会话界面。界面与当前会话工作台布局一致，但绑定到单个团队空间，不再通过顶部工作空间下拉切换。

```text
左侧：团队共享会话列表，按智能体分组
中间：消息流和输入区
右侧：团队空间文件面板
```

团队空间会话界面结构：

```text
左侧顶部：
  团队空间名称                  [+ 新建]
搜索：[搜索当前团队空间会话]

Echo 智能体
  会话 A
  会话 B

Delta 智能体
  会话 C
```

交互规则：

- 左侧会话列表展示该团队空间的共享会话，包含其他成员创建的会话。
- 左侧会话列表始终按智能体分组；分组标题使用 `agent_name`，无智能体时归入“未分配”。
- 点击 `+ 新建` 后打开轻量弹出菜单或空状态选择区，让用户选择智能体；创建会话时把当前团队空间和所选智能体写入 `chat_sessions.workspace_kind/team_space_id/agent_id`。
- 新建会话的智能体默认选中平台默认智能体或用户最近使用的智能体，但不把智能体选择做成常驻筛选器。
- 已有会话继续运行时使用会话绑定的工作空间，不允许在原会话中直接切换。
- 当前成员都可查看历史并继续追加消息。
- 团队空间会话的重命名和删除按钮仅对会话创建者和空间 owner 展示。
- 当绑定团队空间被他人 lock，输入仍可发送，但显示“当前空间只读，Agent 只能读取和分析文件，不能修改文件”。
- 右侧文件面板 title 显示“团队空间”。
- “团队空间”标题右侧放一个“进入”图标按钮，点击跳转到团队空间详情页。

运行规则：

- 后端把会话绑定的工作空间 root 设置为 `ClaudeAgentOptions.cwd`。
- 个人空间会话的 `cwd` 为 `user_workspace(user.username)`。
- 团队空间会话的 `cwd` 为 `team_workspaces/<space_id>`。
- 如果用户已不再是绑定团队空间成员，继续会话时返回 403，并提示用户新建个人空间会话或联系空间 owner。

附件规则：

- 个人空间会话：沿用当前上传目标。
- 团队空间会话：上传目标为该团队空间；如果当前用户无写权限，禁用上传。
- 文件引用路径仍使用相对当前工作目录的路径，因为 agent cwd 与会话绑定的工作空间 root 一致。

### 8.7 团队空间会话列表呈现

团队空间会话列表放在团队会话界面的左侧会话栏中，不放在团队空间文件详情页里。用户从团队空间卡片进入后，直接看到该团队空间下按智能体分组的共享会话。

左侧会话栏结构：

```text
顶部工具区：
  团队空间名称                    [+ 新建]
  [搜索当前团队空间会话]

会话列表：
  Echo 智能体
    会话标题
    张三 · 14:20
    [运行中] [只读] [已锁定]
  Delta 智能体
    ...
```

列表数据规则：

- 列表分组保持现有 `groupSessions()` 逻辑，按智能体名称分组，不按时间分组。
- 每个智能体分组内按 `updated_at` 倒序排序。
- 分组可折叠，折叠状态按 `workspace_kind/team_space_id/agent_name` 维度记忆，避免切换空间后串状态。
- 团队空间会话列表支持搜索标题、创建者名称和 agent 名称；首版不做全文搜索消息内容。

团队空间会话列表项字段：

- 标题：会话标题。
- 副信息：`created_by_name · updated_at`。智能体名已经在分组标题中展示，不在每个列表项重复显示。
- 状态标签：
  - `运行中`：该会话当前有 active run。
  - `只读`：当前成员是 reader，或当前空间被他人 lock。
  - `已锁定`：空间当前被他人 lock。
- 操作：
  - 点击列表项打开会话历史。
  - 创建者或空间 owner 可重命名、删除。
  - 非创建者且非 owner 只显示打开，不显示删除入口。

空态：

- 团队空间暂无会话时，显示“暂无团队会话”，提供“新建团队会话”按钮。
- 当前用户不是任何团队空间成员时，团队空间列表页展示空态，提示先创建或加入团队空间。

运行中态：

- 某个团队共享会话运行中时，所有成员在列表项看到 `运行中` 标签。
- 打开运行中会话时，成员可以查看实时输出和历史，但输入区禁用，提示“该会话正在运行，完成后可继续发送”。
- 触发该轮 run 的成员断开连接后，其他成员仍可通过运行中恢复接口查看状态。

消息区展示：

- 团队空间会话的用户消息展示发送者名称，例如 `张三`、`李四`。
- assistant、tool 消息不绑定成员，但可在折叠信息里展示触发该轮 run 的成员。
- 输入区旁展示当前团队空间权限：`可编辑`、`只读成员`、`空间已由 {name} 锁定`。

## 9. API 与 Schema 草案

### 9.1 TeamSpace DTO

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
  readonly_reason: string | null;
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

### 9.2 ChatSession DTO

```typescript
export interface Session {
  id: string;
  title: string;
  created_by_user_id: number;
  created_by_name: string;
  agent_id: number | null;
  agent_name: string | null;
  workspace_kind: "personal" | "team";
  team_space_id: number | null;
  team_space_name: string | null;
  workspace_member_role: "reader" | "editor" | null;
  workspace_can_write: boolean;
  workspace_readonly_reason: string | null;
  created_at: string;
  updated_at: string;
}
```

团队共享会话中的消息 DTO 建议补充发送者字段：

```typescript
export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  created_by_user_id: number | null;
  created_by_name: string | null;
  created_at: string;
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

### 9.3 通用 Workspace API Client

前端抽出 `WorkspaceFileManager` 后，个人空间和团队空间分别提供符合下列接口的 client：

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

## 10. 数据流

### 10.1 团队空间文件编辑

1. 用户进入团队空间详情页。
2. 前端请求空间详情和文件树。
3. 后端校验用户是成员，返回空间信息、lock 状态和 `can_write`。
4. 用户保存或上传文件。
5. 后端再次解析 `WorkspaceScope` 并校验写权限。
6. 写入空间 root 下的目标文件。
7. 前端刷新文件树和任务状态。

### 10.2 团队空间 lock

1. 成员点击加锁。
2. 后端事务内检查空间未被他人持锁。
3. 写入 `lock_holder_user_id`、`lock_acquired_at`、`lock_note`。
4. 其他成员看到空间变为只读。
5. 持锁人点击解锁后清空 lock 字段。

### 10.3 Agent 使用团队空间

1. 用户在左侧会话栏顶部切换到某个团队空间，点击新建，并在新建菜单中选择智能体。
2. 后端把所选团队空间记录为会话绑定工作空间，该会话进入团队空间会话列表。
3. 任一当前空间成员打开该会话并发送消息。
4. 后端根据会话绑定工作空间解析 `WorkspaceScope`。
5. 后端把空间 root 设置为 `ClaudeAgentOptions.cwd`。
6. 如果发送该轮消息的成员可写，agent 获得空间内写权限。
7. 如果发送该轮消息的成员不可写，agent 只能读取文件，写工具和 Bash 写入被拒绝。
8. 对话历史对该团队空间当前成员可见。

## 11. 错误处理

| 场景 | HTTP 状态 | 文案 |
| --- | --- | --- |
| 非成员访问空间 | 404 | 空间不存在 |
| reader 写入空间 | 403 | 只读成员不能编辑团队空间 |
| reader 加锁空间 | 403 | 只读成员不能锁定团队空间 |
| 非持锁人写入已 lock 空间 | 423 或 409 | 当前空间已由 {name} 锁定，暂不可编辑 |
| 非 owner 管理成员 | 403 | 只有空间所有者可以管理成员 |
| 转移所有权给非成员 | 400 | 只能转移给当前空间成员 |
| 删除 owner 成员 | 409 | 请先转移空间所有权 |
| 将 owner 降级为 reader | 409 | 空间所有者必须保持可编辑权限 |
| 已被他人 lock 时再次 lock | 409 | 当前空间已被锁定 |
| 非成员访问团队空间会话 | 404 | 会话不存在 |
| 非创建者且非 owner 删除团队空间会话 | 403 | 只有会话创建者或空间所有者可以删除会话 |
| 团队空间目录创建失败 | 500 | 团队空间初始化失败 |

建议使用 `423 Locked` 表达 lock 场景；如果前端通用错误处理不支持，使用 `409 Conflict` 也可接受，但要用明确 detail 区分。Agent 写工具被拒绝时，tool result 返回同一套中文原因，说明当前空间只读或被他人持锁。

## 12. 测试计划

### 12.1 后端测试

- owner 创建空间后自动成为 editor 成员。
- 非成员无法获取空间详情和文件树。
- 成员可读取空间文件。
- owner 可添加 reader，reader 可以读取文件树但不能写。
- owner 可添加 editor，editor 未 lock 时可保存、上传、删除、移动、重命名文件。
- owner 可将 reader 升级为 editor。
- owner 不能把当前 owner 降级为 reader。
- owner 转移给 reader 时，目标成员自动升级为 editor。
- reader 调用 lock 返回 403。
- 他人持锁后 editor 写操作返回 423 或 409。
- 持锁人可写并可解除 lock。
- 非持锁 owner 不能解除普通 lock。
- 移除持锁人时自动释放 lock。
- 上传任务和转换任务按空间隔离。
- 创建团队空间会话时，非成员返回 404 或 403。
- 团队空间会话列表对空间当前成员可见。
- 团队空间成员可以读取同一空间内其他成员创建的团队会话历史。
- 团队空间成员可以在共享会话中追加消息。
- 团队空间会话每轮 agent run 的写权限按当前发送者权限计算。
- 团队共享会话的用户消息记录发送者，前端可展示发送者名称。
- 团队共享会话运行中时，其他成员不能并发发送第二轮消息。
- 团队空间会话的 `stream_chat()` cwd 等于 `team_workspaces/<space_id>`。
- 删除团队空间会话时，只有会话创建者或空间 owner 可删除，`remove_session()` 使用会话绑定 scope root。
- 个人空间旧接口行为不变。

### 12.2 Agent 权限测试

- 团队空间可写时，agent 能在空间内创建或修改文件。
- 团队空间只读时，agent 的 Write/Edit/MultiEdit 被 hook 拒绝。
- 团队空间只读时，agent 不能通过 Bash 重定向、mkdir、rm、mv、cp、touch 修改空间文件。
- agent 仍可读取和分析团队空间文件。

### 12.3 前端测试

- 侧边栏不再展示独立对话工作台入口。
- 点击侧边栏个人空间后，默认进入个人会话界面。
- 个人会话界面右侧文件面板 title 为“个人空间”，标题旁有“进入”图标，点击进入个人空间详情页。
- 个人空间详情页有返回会话列表的入口。
- 团队空间列表卡片展示 owner、成员数量、lock 状态和对话图标按钮。
- 点击团队空间卡片对话图标后进入团队会话界面。
- 团队会话界面右侧文件面板 title 为“团队空间”，标题旁有“进入”图标，点击进入团队空间详情页。
- 团队空间详情页有返回团队会话列表的入口。
- 只读状态下文件管理写操作禁用。
- 持锁人可看到解锁按钮，非持锁成员不可解锁。
- owner 可打开成员管理并完成添加、移除、转移所有权。
- 点击新建会话后再选择智能体，智能体不作为常驻筛选下拉。
- 创建会话 payload 包含 `workspace_kind/team_space_id`。
- 创建团队空间会话后，继续对话时使用绑定空间，不在原会话中直接切换空间。
- 团队空间模式下展示该空间共享会话列表，包含其他成员创建的团队会话。
- 团队空间会话列表按智能体分组，不按时间分组。
- 团队空间会话列表项展示标题、创建者、更新时间和运行/只读/锁定状态。
- 团队空间共享会话中的用户消息展示发送者名称。
- 团队空间共享会话运行中时，输入区对其他成员展示运行中禁用态。
- 非创建者且非 owner 不能看到团队空间会话删除入口。
- owner 成员管理可添加 reader/editor，并可调整成员权限。
- reader 文件面板固定只读，隐藏上传、新建、编辑、删除、转换入口。
- 团队空间只读时，对话输入旁展示 agent 只读提示。

## 13. 实施顺序

1. 增加模型与迁移：`TeamSpace`、`TeamSpaceMember`、`chat_sessions.workspace_kind/team_space_id`、上传/转换任务空间归属字段和必要索引。
2. 增加 `backend/app/modules/team_spaces/service.py`：空间 CRUD、成员 reader/editor 管理、所有权转移、lock/unlock。
3. 增加 `backend/app/modules/workspace/scope.py`：个人/团队 scope 解析、会话 scope 解析、读写权限校验。
4. 增加团队空间管理 API 和团队空间文件 API，复用现有 workspace service。
5. 改造上传、转换、任务列表，使任务按 workspace scope 隔离。
6. 改造会话 API，创建会话时接收并持久化绑定工作空间；团队空间会话按成员权限共享列表、历史和运行中状态。
7. 改造 Claude runner、hook、settings 和 sandbox 写权限，使 `ClaudeAgentOptions.cwd` 来自会话绑定 scope。
8. 抽出前端通用 `WorkspaceFileManager` 和 `WorkspaceApi`。
9. 增加团队空间列表页、详情页和成员管理。
10. 改造空间会话界面：个人空间默认进入个人会话界面，团队卡片对话按钮进入团队会话界面，左侧会话按智能体分组，点击新建后选择智能体，会话绑定字段与上传目标保持现有业务逻辑。
11. 补齐后端、agent 权限和前端测试。

## 14. 验收标准

1. 用户能创建团队空间，并作为 owner 添加成员。
2. 成员能查看团队空间文件，非成员无法查看。
3. reader 和其 agent 只能读取空间文件，不能写入。
4. 未 lock 时，editor 和其 agent 都能编辑空间文件。
5. 已 lock 时，只有持锁 editor 和其 agent 能编辑空间文件。
6. 非持锁 editor 和其 agent 只能读取空间文件，不能写入。
7. owner 能将所有权转移给某个成员；目标为 reader 时自动升级为 editor。
8. 侧边栏有团队空间入口，列表页和详情页可完成主要管理与文件操作。
9. 侧边栏无独立对话工作台入口；个人空间默认进入个人会话界面，团队空间通过卡片对话按钮进入团队会话界面。
10. 绑定团队空间的会话对该空间当前成员共享，成员可查看历史并继续追加消息。
11. 个人会话界面展示个人会话，团队会话界面展示该团队空间共享会话，二者会话列表都按智能体分组。
12. 团队共享会话列表项能识别创建者、智能体、更新时间、运行中和锁定/只读状态。
13. 团队共享会话中的用户消息可识别发送者，同一会话同一时刻只有一个运行中的 agent run。
14. 个人空间会话仍只对创建者可见。
15. 个人空间原有功能不回退。

## 15. 风险与处理

### 15.1 运行中 agent 遇到 lock 变化

风险：agent run 启动时团队空间可写，运行过程中被其他 editor lock。

首版处理：一次 agent run 的 `can_write` 在启动时按会话绑定 scope 计算并固定。lock 对新的 agent run 生效；已经开始的一轮 run 不做中途权限刷新。若业务要求 lock 立即阻断运行中的下一次工具调用，可后续把 hook 改为每次重新查询团队空间状态。

### 15.2 长期持锁导致团队无法编辑

风险：成员离线后长期持锁。

首版处理：

- 展示持锁人、加锁时间和 lock 说明。
- owner 可以联系持锁人。
- 后端预留 admin break-lock service，但不在普通 UI 暴露。

后续增强：

- lock 过期时间。
- owner 申请解锁。
- 管理员审计解锁。

### 15.3 任务表兼容迁移复杂

风险：旧上传/转换任务只有 `username`，新任务增加 workspace scope。

处理：

- 旧数据迁移为 `workspace_kind='personal'`。
- 查询个人任务时短期兼容 `workspace_kind IS NULL OR workspace_kind='personal'`，待一次版本后清理兼容。
- 团队空间任务查询必须带 `workspace_kind='team'` 和 `team_space_id`。

### 15.4 文件权限只在前端禁用

风险：用户直接调用 API 或 agent 工具绕过 UI。

处理：

- 所有写 API 后端统一 `require_workspace_write(scope)`。
- Claude Write/Edit/MultiEdit/NotebookEdit 和 Bash 写行为统一 hook 拦截。
- sandbox allowWrite 根据 `scope.can_write` 动态配置，或在 SDK 限制下由 hook 做最终业务裁决。

## 16. 后续演进

- 团队空间发布只读资产快照 Release。
- 从项目资产库 Fork 到团队空间。
- 团队空间绑定知识库/RAG 任务。
- Agent 团队共享同一个团队空间上下文。
- 空间级审计日志：谁上传、谁编辑、谁 lock、哪个 agent 修改了哪个文件。
- 按部门或角色批量授权团队空间。
