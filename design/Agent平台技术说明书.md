- **智能体平台技术说明书**
- 基于 Claude Agent SDK 与 Subagent 的第一版平台方案
- 版本：V1.0
日期：2026-05-08
文档类型：技术说明书

# 1. 文档概述

本文档说明智能体平台第一版的目标架构、核心对象、运行机制、文件与 Skill 管理规范、事件审计、安全边界和实施阶段。文档保留最终方案，不展开方案选择过程。

## 1.1 建设目标

- 建设一个 Web 化智能体平台，支持管理员控制台和普通用户客户端。

- 基于 Claude Agent SDK 运行 main agent，并使用 Claude subagent 实现多智能体协作。

- 支持用户创建 Agent、Agent Team，并在授权范围内选择 Claude Code Skill。

- 支持用户上传文件、会话内持续使用文件和产物、查看运行结果。

- 通过事件流、权限控制和工作区隔离，使平台具备可观测、可审计、可治理能力。

## 1.2 第一版范围

| - **范围** | - **说明** |
| - 包含 | - Claude Agent SDK、Claude subagent、Claude`Code`Skill、会话级 workspace、Run 事件流、控制台、客户端。 |
| - 不包含 | - Plugin、marketplace、复杂商业化租户体系、完整事件回放、DAG 工作流引擎。 |
| - 存储 | - 第一版使用服务器本地文件系统；后续可迁移至对象存储。 |

# 2. 总体架构

平台采用“控制面 + Claude 原生运行时”的架构。平台负责用户、权限、团队配置、Skill 授权、workspace、Run 记录、事件流和审计；Claude Agent SDK 负责 main agent loop、subagent 调用、上下文隔离、工具和 Skill 执行。

| - **层级** | - **组件** | - **职责** |
| - Web 层 | - Admin Console | - 管理用户、角色、权限、Skill、用户数据、运行审计。 |
| - Web 层 | - User Client | - 上传文件、创建 Agent/Team、发送消息、查看会话、产物和事件。 |
| - 服务层 | - API Server | - 处理认证、鉴权、管理端 API 和客户端 API。 |
| - 服务层 | - Run Service | - 创建 Run、维护运行状态机、队列投递、取消和重试。 |
| - 运行层 | - Agent Runtime Worker | - 加载 Team 配置，生成 Claude SDK options，注入 Skill 和文件清单，监听事件流。 |
| - 运行层 | - Claude Agent SDK | - 运行 main agent，管理会话，调用 subagents。 |
| - 存储层 | - Database / Filesystem | - 保存配置、会话、消息、Run、事件、文件和产物。 |

Admin Console / User Client
|
API Server
|
Run Service
|
Agent Runtime Worker
|
Claude Agent SDK
|
Main Agent -> Subagent A / Subagent B / Subagent C

# 3. 核心对象定义

| - **对象** | - **定义** | - **边界** |
| - Conversation | - 一段聊天上下文和一个持续 workspace。 | - 同一会话中的多轮消息、输入文件、中间文件和产物共享同一个 workspace。 |
| - Message | - 用户或 assistant 的单条消息。 | - 记录聊天内容，不直接拥有文件目录。 |
| - Run | - 为响应一条用户消息而触发的一次 main agent 执行记录。 | - 记录状态、事件、耗时、成本、错误和审计信息；不创建独立 workspace。 |
| - Agent Team | - 一组 Agent 配置，包含 main agent 和多个 subagent。 | - 只拥有配置，不拥有长期目录。 |
| - Skill | - 遵循 Claude`Code`规范的声明式能力包。 | - 由平台统一管理、授权、版本化和运行时注入。 |

## 3.1 Run 模式

每条需要 assistant 回复的用户消息通常都会触发一个 Run。Run 的模式决定本次执行是否访问文件、使用工具或调用 subagent。

| - **Run mode** | - **Main Agent** | - **Subagent** | - **文件访问** | - **产物** | - **说明** |
| - chat | - 是 | - 否 | - 否 | - 否 | - 普通问答或解释。 |
| - tool_execution | - 是 | - 可选 | - 可选 | - 可选 | - 使用工具、Skill 或 workspace 文件。 |
| - multi_agent | - 是 | - 是 | - 可选 | - 可选 | - 主 Agent 调用一个或多个 subagent 协作。 |

| - **设计原则** - Run 不创建独立目录。同一个长期会话可以产生大量 Run 记录，但文件系统只保留一个 conversation workspace。 |

# 4. 多智能体协作机制

多智能体团队使用 Claude Agent SDK 的 subagent 功能实现。平台不自研子 Agent 通信协议，不允许子 Agent 直接互相通信，也不允许 subagent 再创建 subagent。

| - **角色** | - **职责** | - **约束** |
| - Main Agent | - 理解用户请求，规划执行，调用 subagent，审核结果，生成最终回复。 | - 可使用 Agent tool 调用 subagent。 |
| - Subagent | - 承担专门能力，例如研究、分析、审核、写作。 | - 不能使用 Agent tool，不能直接调用其他 subagent。 |
| - Run Service | - 创建 Run，维护状态，处理取消、超时、重试和队列投递。 | - 不直接执行模型推理。 |
| - Agent Runtime Worker | - 根据会话、Team、Skill、权限和文件清单启动 Claude SDK。 | - 必须记录事件并执行权限校验。 |

## 4.1 执行流程

- 用户在 Conversation 中发送消息。
- Run Service 创建 Run，并将其投递到队列。
- Agent Runtime Worker 加载 Conversation、Team、Agent、Skill、权限和文件清单。
- Worker 设置 Claude SDK 的 cwd 为当前 conversation workspace。
- Main Agent 根据用户消息进行推理。必要时调用一个或多个 subagent。
- Worker 持续监听 streamed messages，并写入事件流。
- Main Agent 生成最终回复；如有产物，写入 artifacts 目录。
- Run Service 将 Run 标记为 completed、failed、cancelled 或 timeout。

# 5. Skill 管理规范

- 平台管理的 Skill 遵循 Claude`Code`Skill 目录规范。长期 Skill 资产由平台 Skill Registry 管理，运行时按会话复制到当前 workspace。

## 5.1 Skill Registry

/data/agent-platform/skills/registry/
{skill_id}/
versions/
{version}/
SKILL.md
examples/
scripts/
references/

## 5.2 运行时注入

会话首次启动或会话中 Skill 授权发生变化时，Worker 将授权 Skill 复制到当前 conversation workspace。第一版采用 copy-on-conversation-start，不默认使用 symlink。

/data/agent-platform/workspaces/{user_id}/conversations/{conversation_id}/
.claude/
skills/
{safe_skill_name}/
SKILL.md
examples/
scripts/
references/

- 客户端只能查看和选择授权 Skill，不能下载 Skill 源文件。

- Team 可用 Skill 是 main agent 和 subagent 可选 Skill 的上限。

- Worker 只注入当前用户、当前会话、当前 Agent 有权使用的 Skill。

- Skill 注入必须记录 skill.injected 事件，包含 skill_id、version、checksum、target_path 和 injection_mode。

# 6. 文件与 Workspace 规范

平台区分用户上传文件库和会话执行现场。上传文件是用户级长期资产，workspace 是会话级执行目录。Agent 和 Team 只拥有配置，不拥有长期文件目录。

## 6.1 文件目录结构

/data/agent-platform/
uploads/
{user_id}/
{file_id}/
original.ext
metadata.`json`
extracted/

workspaces/
{user_id}/
conversations/
{conversation_id}/
.claude/skills/
inputs/
working/
artifacts/
logs/events.jsonl

| - **目录** | - **归属** | - **Agent 权限** | - **用途** |
| - uploads/{user_id}/ | - 用户级 | - 默认不可直接访问 | - 用户长期上传文件库。 |
| - conversations/{conversation_id}/.claude/skills/ | - 会话级 | - 只读 | - 当前会话授权 Skill 执行视图。 |
| - conversations/{conversation_id}/inputs/ | - 会话级 | - 只读 | - 当前会话允许读取的输入文件视图。 |
| - conversations/{conversation_id}/working/ | - 会话级 | - 读写 | - main agent 和 subagents 的共享工作目录。 |
| - conversations/{conversation_id}/artifacts/ | - 会话级 | - 写入 | - 当前会话生成的输出产物。 |
| - conversations/{conversation_id}/logs/ | - 会话级 | - 追加写 | - 会话运行日志；事件主数据以数据库 agent_events 为准。 |

## 6.2 上传文件读取机制

Claude Agent 不直接遍历全局 uploads 目录，也不通过猜路径读取文件。会话创建或用户向会话添加文件时，平台生成 ConversationInputManifest，并将授权文件复制到当前 workspace 的 inputs 目录。

- Claude SDK 的 cwd 设置为 workspaces/{user_id}/conversations/{conversation_id}。

- Main Agent prompt 中注入当前会话可读取文件清单。

- Agent 只能读取 inputs/ 中的授权文件。

- 平台 runtime 拦截文件访问，禁止访问当前 conversation workspace 之外的路径。

- 所有文件读取、写入、删除和列表操作均记录 file.accessed 事件。

# 7. 事件流与审计规范

事件流是客户端展示、管理员审计和问题定位的统一事实来源。第一版必须记录完整事件流，但不要求实现完整回放。

| - **事件类型** | - **说明** |
| - run.created / run.started / run.completed | - 记录 Run 生命周期。 |
| - plan.created | - 记录主 Agent 生成计划。 |
| - subagent.invoked / subagent.completed / subagent.failed | - 记录 subagent 调用和结果。 |
| - tool.called / tool.completed | - 记录工具调用。 |
| - skill.injected | - 记录 Skill 注入版本和校验信息。 |
| - file.accessed | - 记录文件访问路径、操作、是否允许和原因。 |
| - artifact.created | - 记录产物生成。 |
| - final.generated | - 记录最终回复生成。 |

- **日志策略：**事件主数据应写入数据库 agent_events。文件日志仅作为补充，可使用 conversation 级 logs/events.jsonl 或按日期分片，不为每个 Run 创建目录。

# 8. 安全与权限边界

- 安全边界必须由平台 runtime 强制，不依赖 prompt 约束。
- 用户只能访问自己的上传文件库和自己的 conversation workspace。
- Agent 只能访问当前 conversation 的 workspaces/{user_id}/conversations/{conversation_id}。
- Agent 默认不能直接访问全局 uploads，只能读取平台复制到 inputs 的会话授权文件。
- 客户端不能下载 Skill 源文件。
- Subagent 不能使用 Agent tool，避免递归委派。
- Worker 生成 Claude SDK options 前必须完成用户、Team、Agent、Skill 和文件权限校验。
- 所有文件访问、Skill 使用、subagent 调用都必须写入事件流。
- 必须禁止路径逃逸、软链接逃逸和绝对路径越权访问。
- Run 取消后，Worker 必须停止继续写入 artifacts。
- 管理员操作必须写入审计日志。

# 9. 实施阶段

| - **阶段** | - **目标** | - **主要交付** |
| - Phase 1：Architecture Spike | - 验证 Claude SDK main agent、subagent、Skill 注入、会话级 workspace 和事件捕获。 | - 主 Agent 调用两个 subagent；不同 subagent 使用不同 Skill；事件写入数据库或 JSONL；文件和 workspace 隔离。 |
| - Phase 2：Platform MVP | - 形成最小可用平台。 | - 登录、Skill 上传与授权、Agent/Team 创建、文件上传、消息触发 Run、事件流和产物查看。 |
| - Phase 3：Governance Hardening | - 支持内部真实使用。 | - RBAC、审计日志、Run 取消/超时、文件访问拦截、Skill checksum 和版本管理。 |
| - Phase 4：Production Readiness | - 为更大范围用户做准备。 | - Worker 队列化、并发控制、资源限制、对象存储适配、事件检索、失败重试。 |

# 10. 验收标准

- 用户可以创建一个 Team，包含一个 main agent 和至少两个 subagent。
- 每条需要 assistant 回复的用户消息会触发一个 Run。
- Main Agent 可以根据用户请求调用不同 subagent。
- Subagent 使用各自绑定的 Claude`Code`Skill，且不能调用其他 subagent。
- 用户上传文件进入全局 uploads/{user_id}/{file_id}。
- 会话创建或用户添加文件时，平台将授权文件复制到 conversation workspace 的 inputs/。
- 会话启动时，平台将授权 Skill 复制到 conversation workspace 的 .claude/skills/。
- Agent 只能访问当前 conversation workspace 内的授权目录。
- Agent 产物进入当前 conversation workspace 的 artifacts/。
- 平台能展示完整事件流，管理员能查看 Skill 使用记录和 Run 审计。
- Run 失败时，能定位失败发生在 main agent、subagent、工具调用、文件权限还是模型输出。