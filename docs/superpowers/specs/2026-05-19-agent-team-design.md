# Agent Team Design

## Context

当前平台已有单智能体能力：管理员可维护 `Agent` 的名称、代号、系统提示词、技能和插件；用户创建会话时绑定 `agent_id`；后端通过 `stream_chat` 启动 Claude Agent SDK，并为不同 Agent 注入独立工作目录、技能、插件和安全规则。

团队功能的目标是在不改变用户聊天心智的前提下，让用户可以选择一个“团队”进行对话。团队对用户表现得像一个智能体，但运行时由一个 Team Leader 主智能体调用多个成员智能体协作完成复杂任务。

## Product Shape

第一版采用黑盒团队体验：

- 用户在新建对话时可以选择单个智能体或团队。
- 团队对话进入现有聊天工作台，不新增独立聊天页面。
- 团队内部协作细节默认不完整暴露给用户，最终由 Team Leader 输出统一回复。
- 管理端新增独立“团队管理”入口，不把团队混入“智能体管理”表单。

## Recommended Approach

第一版不引入额外多智能体框架，使用 Claude Agent SDK 原生 `agents` / `AgentDefinition` 能力实现成员智能体调用。

理由：

- 当前项目已经围绕 Claude Agent SDK 建立会话、技能、插件、工作目录和安全边界。
- 本地依赖已支持 `ClaudeAgentOptions.agents`、`AgentDefinition` 和 `SubagentStart` / `SubagentStop` hooks。
- 引入 LangGraph、AutoGen、CrewAI 等框架会带来第二套 Agent、Tool、Memory、State 抽象，与当前 Claude SDK 路线重叠。
- 平台第一版需要验证团队黑盒对话价值，而不是先建设完整流程编排引擎。

允许引入额外框架的判断标准：

- 需要固定流程状态机，例如“调研 -> 分析 -> 方案 -> 审核 -> 修订”。
- 每个节点需要平台级重试、条件分支、人工审批和结构化结果入库。
- Claude SDK 不再是运行时核心，而只是某些节点中的模型或工具执行器。

在这些需求出现前，不建议引入额外框架。

## Team Model

团队本身就是一个 Team Leader 主智能体配置，字段与智能体类似，同时额外拥有成员智能体列表。

### `agent_teams`

- `id`
- `name`
- `code`
- `system_prompt`
- `skills`
- `plugins`
- `is_default`
- `created_at`
- `updated_at`

`skills` 和 `plugins` 第一版沿用现有 Agent 的逗号分隔字符串存储方式，降低迁移和页面复用成本。

### `agent_team_members`

- `id`
- `team_id`
- `agent_id`
- `role_name`
- `description`
- `sort_order`
- `max_turns`

成员智能体继续复用 `agents` 表中的配置。`role_name` 和 `description` 用于生成成员 `AgentDefinition.description`，帮助 Team Leader 判断何时调用该成员。

### `chat_sessions`

新增：

- `team_id`

约束：

- `agent_id` 与 `team_id` 二选一。
- 历史数据保持 `team_id = null`。

## Default Team Leader Prompt

创建团队时，`system_prompt` 默认填入以下模板，管理员可以编辑：

```text
你是一个智能体团队的负责人，负责理解用户目标、拆解任务、选择合适的团队成员协作，并向用户交付统一、清晰、可执行的最终结果。

你的工作方式：
1. 先判断用户任务是否需要团队成员参与。简单问题可直接回答，复杂任务应拆解后委派。
2. 根据每个成员智能体的职责说明，选择最合适的成员执行研究、分析、写作、审查、实现或验证等子任务。
3. 委派任务时要给成员明确的目标、上下文、输入材料、输出格式和质量要求。
4. 收到成员结果后，你必须进行综合、去重、冲突检查和质量判断，不要机械拼接成员回复。
5. 如果成员结果不充分，你可以继续追问成员或自行补充分析。
6. 最终只向用户输出团队统一结论，除非用户要求，否则不要暴露内部协作细节。
7. 遇到不确定信息时，应明确说明假设、风险和需要用户确认的点。
8. 需要修改文件或执行操作时，必须遵守当前工作空间和工具权限限制。

团队成员会作为你的协作者被调用。你负责最终质量，不能把责任转交给成员。
```

运行时仍会追加现有工作空间安全规则，避免管理员编辑模板时覆盖平台安全边界。

## Runtime Design

扩展现有 `stream_chat`，新增可选 `team` 上下文参数；单智能体会话沿用现有路径，团队会话在同一个封装内构建 Team Leader options 和成员 `AgentDefinition`：

- Team Leader 使用团队自身的 `system_prompt`、`skills`、`plugins` 启动。
- 团队成员转换为 `ClaudeAgentOptions.agents`。
- 每个成员的 `AgentDefinition.prompt` 来源于成员 Agent 的 `system_prompt`。
- 每个成员的 `description` 由 `role_name`、`description`、成员名称组合生成。
- 每个成员可继承自身 Agent 的 `skills`。
- 每个成员默认禁用 `Agent` 工具，防止递归委派。
- Team Leader 的 `allowed_tools` 需要包含 SDK 调用子智能体所需的 Agent 工具。
- Team Leader 与成员第一版共享当前用户 workspace 和同一个 Claude session。

成员插件策略：

- 第一版优先支持 Team Leader 的插件注入。
- 成员 Agent 的 `plugins` 先保留在配置和管理页面中，不强行注入给 subagent，除非 SDK 的 `AgentDefinition` 能稳定支持成员级插件。
- 如果成员必须使用特定插件，应把插件配置到团队主智能体，或在后续版本扩展成员级插件注入。

## API Design

新增团队管理 API：

- `GET /api/teams`
- `GET /api/teams/{team_id}`
- `POST /api/teams`
- `PATCH /api/teams/{team_id}`
- `DELETE /api/teams/{team_id}`

权限：

- 登录用户可读取团队列表和详情。
- 管理员可创建、更新、删除团队。

会话 API 调整：

- `CreateSessionRequest` 增加 `team_id`。
- 创建会话时校验 `agent_id` 和 `team_id` 不能同时存在。
- `SessionOut` 增加 `team_id`、`team_name`，用于会话列表展示。

对话 API 不新增路径，继续使用：

- `POST /api/sessions/{session_id}/chat`
- `POST /api/sessions/{session_id}/stop`
- `GET /api/sessions/{session_id}/messages`

后端根据会话绑定的是 `agent_id` 还是 `team_id` 选择单智能体运行或团队运行。

## Frontend Design

侧边栏新增独立入口：

- 对话工作台
- 个人空间
- 智能体管理
- 团队管理
- 技能管理
- 反馈管理

新增 `TeamsPage`，整体交互复用 `AgentsPage` 的列表和居中弹窗模式。团队表单包含四个页签：

- 基础信息：团队名称、团队代号、Team Leader 提示词。
- 技能：勾选团队主智能体可用技能。
- 插件：勾选团队主智能体可用插件。
- 智能体：勾选成员智能体，配置角色名、职责描述和排序。

新建对话页需要展示两个分组：

- 智能体：现有单 Agent。
- 团队：Agent Team。

用户选择团队后进入同一个聊天工作台。聊天页标题和会话列表优先展示团队名称。

## Error Handling

- 创建或更新团队时，`code` 必须唯一，格式沿用 Agent 代号规则。
- 团队至少需要一个成员智能体，否则保存失败。
- 删除团队时，如果有会话引用该团队，必须阻止删除并返回引用提示。
- 团队成员引用的 Agent 被删除时，数据库使用限制删除或在删除 Agent 前检查 Team 引用，避免团队配置悬空。
- 团队运行时若某个成员调用失败，Team Leader 应拿到失败信息并决定是否继续；平台 SSE 至少返回最终错误事件，避免前端卡死。
- 停止团队会话时，沿用当前 `stop_event` 机制中断 SDK client。

## Testing

后端测试：

- 团队 CRUD 权限：普通用户只读，管理员可写。
- 团队创建校验：名称、代号、成员列表、重复代号。
- 会话创建校验：`agent_id` 与 `team_id` 二选一。
- 会话列表返回团队名称。
- 团队会话调用时正确构建 `ClaudeAgentOptions.agents`。
- 删除被会话或成员引用的团队/智能体时返回明确错误。

前端测试：

- 侧边栏显示“团队管理”入口。
- 团队管理页可加载技能、插件、智能体列表。
- 团队表单能创建、编辑成员配置。
- 新建对话页能选择团队并创建团队会话。

手动验证：

- 创建一个含两个成员的团队。
- 用户选择团队发起对话。
- Team Leader 能根据任务调用成员并给出统一回复。
- 停止按钮可中断运行中的团队对话。
- 历史消息可重新加载。

## Out of Scope

第一版不做：

- 用户自定义团队。
- 团队流程图或完整过程可视化。
- 成员之间直接互相通信。
- 子智能体再调用子智能体。
- 每个成员独立 workspace。
- 平台自研多 Agent 调度引擎。
- 引入 LangGraph、AutoGen、CrewAI 等额外多智能体框架。

## Implementation Notes

建议保持增量实现：

1. 先补后端模型、schema、service、routes 和迁移。
2. 再调整会话创建和团队运行时。
3. 最后新增前端团队管理页与新建对话选择器分组。

团队运行时应尽量复用现有 `stream_chat` 的安全规则、插件解析、SSE 队列和停止机制，避免复制出第二套难以维护的 Claude SDK 封装。
