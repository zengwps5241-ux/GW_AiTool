# AI 顾问作战台 · 开发进度记录

> 基于《开发计划拆解V2.0.md》，按任务顺序逐一执行
> 启动日期：2026-07-08

---

## Phase 1：地基重构

### M1.1 认证体系重构 ✅ 已完成（commit 7bcf183，本会话补齐测试）

| 任务 | 状态 | 备注 |
|------|------|------|
| M1.1.1 注释企微认证代码 | ✅ | wechat_work.py + departments.py + auth.py 企微路由全注释保留 |
| M1.1.2 User 模型扩展 | ✅ | phone/status/registration_source 字段 |
| M1.1.3 注册 API | ✅ | POST /api/auth/register，默认 pending_approval |
| M1.1.4 登录 API | ✅ | POST /api/auth/login |
| M1.1.5 登出 API | ✅ | POST /api/auth/logout |
| M1.1.6 管理员审批 API | ✅ | pending-users + approve/reject |
| M1.1.7 前端登录页重构 | ✅ | LoginPage 表单登录 |
| M1.1.8 前端认证逻辑恢复 | ✅ | 删除 mock 绕过 |
| **测试补齐（本会话）** | ✅ | conftest 登录 fixtures 从企微流程改为自建注册登录；test_auth_api.py 重写为自建认证覆盖（24 测全过） |

### M1.2 组织架构 ✅ 已完成（commit 本会话）

| 任务 | 状态 | 完成时间 | 备注 |
|------|------|---------|------|
| M1.2.1 Organization 模型 | ✅ | 2026-07-09 | organizations 表，自引用树（修复 children/parent remote_side 冲突） |
| M1.2.2 User-Organization 关联 | ✅ | 2026-07-09 | user_organizations 表，position_title/is_primary |
| M1.2.3 组织 CRUD API | ✅ | 2026-07-09 | /api/admin/organizations 全套 CRUD + 树形 /tree + 成员管理 + 防环 |
| M1.2.4 批量导入 API | ✅ | 2026-07-09 | /import（JSON）+ /import-csv（CSV），按名称解析父级、去重、错误收集 |
| M1.2.5 前端组织管理页 | ✅ | 2026-07-09 | OrganizationPage 树形展示 + 增删改 + 成员 + 批量导入（JSON/CSV） |

**回归测试基线**（commit 后）：
- 后端全量：454 passed / 20 failed / 2 skipped / 3 errors
  - 新增测试：test_organizations_api.py（22 全过）、test_auth_api.py 重写（24 全过）
  - 20 fail + 3 error 均为**既有环境问题**（企微模块已注释致 Import/Attribute 错误、Windows 符号链接/CRLF/路径分隔符、本地 DB 口令、config 默认值），**与本任务无关，fail 集未扩大**
- 前端：npm run build 70 modules，0 错误

### M1.3 客户与项目模型 ✅ 已完成（commit 本会话）

| 任务 | 状态 | 完成时间 | 备注 |
|------|------|---------|------|
| M1.3.1 Customer 模型 | ✅ | 2026-07-09 | customers 表（Integer PK，决策#10；含 visibility/sensitivity_level；orgStructure 延后，决策#15） |
| M1.3.2 Project 模型 | ✅ | 2026-07-09 | projects 表（customer_id FK RESTRICT、agent_id、owner_id、fde_stage/status/visibility 等） |
| M1.3.3 ProjectMember 模型 | ✅ | 2026-07-09 | project_members（owner/deputy，UNIQUE(project,user)） |
| M1.3.4 ProjectDepartmentAccess 模型 | ✅ | 2026-07-09 | project_department_access（部门授权→成员自动获访问权） |
| M1.3.5 Customer CRUD API | ✅ | 2026-07-09 | /api/customers CRUD；admin 全部 / 普通用户「自建 ∪ 可访问项目」（决策#14） |
| M1.3.6 Project CRUD API | ✅ | 2026-07-09 | /api/projects CRUD + 成员管理 + 部门授权（owner 单一不变式） |
| M1.3.7 项目创建自动生成 Agent | ✅ | 2026-07-09 | 创建项目同事务生成 Agent（consultant_{id} + 7 Skill/3 Plugin，决策#11/#13） |
| M1.3.8 权限中间件 | ✅ | 2026-07-09 | require_project_member/owner + access.py 纯数据层（决策#12）；admin 越权、部门授权=deputy |
| M1.3.9 前端项目选择器 | ✅ | 2026-07-09 | ProjectSelector（客户→项目级联 + 新建项目弹窗）+ App 全局 selectedProject，嵌入 Topbar |

**回归测试基线**（commit 后）：
- 后端全量：488 passed / 20 failed / 2 skipped / 3 errors
  - 新增测试：test_customers_api.py（16）、test_projects_api.py（18）= 34 全过
  - 相比 M1.2 基线（454 passed）passed +34（恰好新增），failed/errors 不变 → **fail 集未扩大**（20 fail+3 err 全为既有环境问题）
- 前端：npm run build 71 modules，0 错误


### M1.4 导航重构 ✅ 已完成（commit 本会话）

| 任务 | 状态 | 完成时间 | 备注 |
|------|------|---------|------|
| M1.4.1 Sidebar 更新 | ✅ | 2026-07-09 | SidebarVariantA 分组对齐 §2.1：作战台(对话/业务地图/营销地图/拜访记录)·文件(个人/团队空间)·管理(智能体/技能/统计/反馈/白名单)·设置(组织架构/用户管理)；用户管理(用户审批)移入「设置」组 |
| M1.4.2 路由更新 | ✅ | 2026-07-09 | ViewName 类型已含 organization/businessMap/marketingMap/visitRecords/userApproval；App.tsx renderPage + 面包屑已覆盖（用户审批面包屑改「设置/用户管理」） |

> M1.4 Sidebar 分组在 M1.2 阶段(commit dd9a3a0 锁定 Sidebar A)已基本就绪，本次仅做 §2.1 对齐微调。前端 npm run build 71 modules 0 错误。

---

## ✅ Phase 1（地基重构）全部完成

M1.1 认证体系重构 → M1.2 组织架构 → M1.3 客户与项目模型 → M1.4 导航重构 全部交付。
后续 Phase 2（数据模型与 API）依赖 M1.3 的 Project 模型。

---

## Phase 2-5

### M2.1 业务地图数据 ✅ 已完成（commit 本会话）

| 任务 | 状态 | 完成时间 | 备注 |
|------|------|---------|------|
| M2.1.1 BusinessMapObject 模型 | ✅ | 2026-07-09 | business_map_objects（L1-L4，JSONB payload，决策#16；parentId/linkedHypothesisId 自引用） |
| M2.1.2 PreAnalysis 模型 | ✅ | 2026-07-09 | pre_analyses（项目级一份，UNIQUE(project_id)） |
| M2.1.3 BusinessMapVersion 模型 | ✅ | 2026-07-09 | business_map_versions（采纳快照，JSONB snapshot_data） |
| M2.1.4 BusinessMapDraft 模型 | ✅ | 2026-07-09 | business_map_drafts（整图一个草稿单元，7天过期） |
| M2.1.5 BusinessMap CRUD API | ✅ | 2026-07-09 | /objects 全套 CRUD + level/mapType/reviewStatus 筛选（默认 reviewed，决策#17） |
| M2.1.6 PreAnalysis API | ✅ | 2026-07-09 | /pre-analysis upsert（GET + PUT） |
| M2.1.7 草稿区 API | ✅ | 2026-07-09 | /drafts 获取/更新 + 采纳（Owner→reviewed / Deputy→pending_review + 版本快照，决策#18） |
| M2.1.8 版本管理 API | ✅ | 2026-07-09 | /versions 列表/详情/回滚（仅 Owner，审计快照，决策#19） |
| M2.1.9 五维健康计算服务 | ✅ | 2026-07-09 | health.py 简单规则版（完整度启发式，决策#20/风险#5）+ 计算/批量/手动覆盖 API |

**回归测试**：test_business_map_api.py（11 全过：对象CRUD+筛选 / 前置分析 / 草稿采纳Owner+Deputy / 版本回滚 / 五维健康 / 项目隔离+admin越权）。全量 **499 passed / 20 failed / 2 skipped / 3 errors**，相比 M1.3 基线（488 passed）passed +11（恰好新增），**fail 集未扩大**（20 fail+3 err 全为既有环境问题）。

### M2.2 营销地图数据 ✅ 已完成（commit 本会话）

| 任务 | 状态 | 完成时间 | 备注 |
|------|------|---------|------|
| M2.2.1 StakeholderCard 模型 | ✅ | 2026-07-09 | stakeholder_cards（客观层/主观层/behaviors/stanceChangeLog JSONB，决策#21） |
| M2.2.2 StakeholderRelation 模型 | ✅ | 2026-07-09 | stakeholder_relations（reports_to/influences/collaborates/opposes，决策#22） |
| M2.2.3 TalkScript 模型 | ✅ | 2026-07-09 | talk_scripts（五类角色×场景，isTemplate 通用模板） |
| M2.2.4 KnowledgeBase 模型 | ✅ | 2026-07-09 | knowledge_base（项目级，决策#24；三类 category） |
| M2.2.5 StakeholderCard CRUD API | ✅ | 2026-07-09 | 全套 + department/role_type/stance(JSONB) 筛选 + 综合评分自动计算 |
| M2.2.6 StakeholderRelation CRUD API | ✅ | 2026-07-09 | CRUD + 防自环 + 关系网络图 /graph（nodes+edges） |
| M2.2.7 TalkScript CRUD API | ✅ | 2026-07-09 | 全套 + role_type/scenario 筛选 |
| M2.2.8 KnowledgeBase CRUD API | ✅ | 2026-07-09 | 全套 + category 筛选 |
| M2.2.9 态度变化自动记录 | ✅ | 2026-07-09 | record_stance_change 服务函数 + 手动 API（M2.3 证据联动复用，决策#23） |

**回归测试**：test_marketing_map_api.py（12 全过：角色卡+综合评分+筛选 / 态度变化 / 关系+图 / 话术+模板 / 知识库 / 项目隔离+admin越权）。全量 **511 passed / 20 failed / 2 skipped / 3 errors**，相比 M2.1 基线（499 passed）passed +12（恰好新增），**fail 集未扩大**。

### M2.3 拜访记录数据 ✅ 已完成（commit 本会话）

| 任务 | 状态 | 完成时间 | 备注 |
|------|------|---------|------|
| M2.3.1 VisitRecord 模型 | ✅ | 2026-07-09 | visit_records（日期/类型/参与人/摘要/下一步/KeyTakeaways，决策#25） |
| M2.3.2 EvidenceSource 模型 | ✅ | 2026-07-09 | evidence_sources（类型/强度/内容 + 关联角色卡 sourceRoleId + 关联假设 relatedHypothesisId，决策#25） |
| M2.3.3 VisitRecord CRUD API | ✅ | 2026-07-09 | /visit-records 全套 + 时间倒序 + 按类型/角色卡(JSONB @>) 筛选 |
| M2.3.4 EvidenceSource CRUD API | ✅ | 2026-07-09 | /evidence-sources 全套 + 多维筛选（拜访/类型/强度/角色/假设） |
| M2.3.5 证据验证联动 | ✅ | 2026-07-09 | §7.5 建议验证状态(强度计数)+人工确认→更新 verificationStatus+推翻自动入偏差池；§7.6 角色态度信号证据→自动 record_stance_change（决策#26/#27） |

**设计要点**：
- 派生统计 `evidenceCount`/`verifiedHypotheses` 不落库，读取时按关联证据动态计算（避免同步问题）。
- §7.5 建议状态规则：0→未验证 / 强≥3→成立 / 强≥1或中≥2→部分成立 / 仅弱→待补充；推翻确认自动新增 current 偏差节点（已存在则复用）。
- §7.6 触发条件：`evidenceType=角色态度信号` + `sourceRoleId` + `impliedFromStance/toStance` 齐备 → 复用 M2.2 `record_stance_change`（决策#27）。

**回归测试**：test_visit_api.py（9 全过：拜访CRUD+时间倒序+角色筛选 / 证据CRUD+多维筛选+派生统计 / §7.5建议规则+确认+偏差池 / §7.6态度自动触发+非信号不触发 / 项目隔离+跨项目关联拒绝）。全量 **520 passed / 20 failed / 2 skipped / 3 errors**，相比 M2.2 基线（511 passed）passed +9（恰好新增），**fail 集未扩大**（20 fail+3 err 全为既有环境问题）。

### M2.4 采纳与审批机制 ✅ 已完成（commit 本会话）

| 任务 | 状态 | 完成时间 | 备注 |
|------|------|---------|------|
| M2.4.1 采纳 API | ✅ | 2026-07-09 | `POST /api/projects/{id}/adopt` 统一派发器：business_map_draft→adopt_draft（Owner→reviewed+版本快照 / Deputy→pending_review）；营销/拜访草稿留待 M3.1.1 扩展 |
| M2.4.2 审批 API | ✅ | 2026-07-09 | `GET /api/projects/{id}/pending-reviews` 跨四类实体聚合（+entity_type 筛选）；`POST /reviews/{type}/{id}/approve\|reject`（Owner 翻状态） |
| M2.4.3 采纳后数据流转 | ✅ | 2026-07-09 | 采纳→草稿写正式表+版本快照+草稿置adopted；approve→reviewed 立即页面可见（§7.3）；reject→rejected 退回（§3.4） |

**设计要点**：
- **架构（决策 #28）**：保留各模块自有 adopt（business_map.adopt_draft 带「整图草稿单元+版本快照」专有语义，§7.4 仅业务地图支持版本回溯）；新增统一审批层 `app/modules/reviews/`，用「实体注册表」覆盖四类可审批实体（BusinessMapObject/StakeholderCard/VisitRecord/EvidenceSource 共享 review_status/reviewed_by/reviewed_at 三列）。
- **§3.3 审批范围**：仅 WF07（业务地图）Deputy 产出需 Owner 审；非 WF07 自确认。故 adopt 时 business_map Deputy→pending_review（需审），营销/拜访未来 Deputy→reviewed（自确认，不进待审批列表）；统一审批机制对任何 pending_review 通用。
- **权限**：GET pending-reviews = require_project_member（项目内透明）；approve/reject = require_project_owner（发布/退回限 Owner）；adopt = require_project_member（角色决定状态）。admin 越权可审任意项目。
- **驳回意见**：M2.4 数据层不持久化（Phase 3 对话 Banner 审核流承载「修改意见」）。

**回归测试**：test_reviews_api.py（11 全过：采纳派发 Owner+Deputy / 不支持类型 400 / 跨模块聚合+筛选 / business_map 审批发布 / 逐类 approve / reject+意见 / Deputy 403 / 404+非pending 400 / 项目隔离 / admin 越权）。全量 **531 passed / 20 failed / 2 skipped / 3 errors**，相比 M2.3 基线（520 passed）passed +11（恰好新增），**fail 集未扩大**。

---

## Phase 3：Skill 与 Plugin

### M3.1 Tool Use 基础框架（后端 M3.1.1-3）✅ 已完成（commit 本会话）

| 任务 | 状态 | 完成时间 | 备注 |
|------|------|---------|------|
| M3.1.1 Tool Use 注册机制 | ✅ | 2026-07-09 | `app/integrations/claude/tools.py`：用 claude_agent_sdk `create_sdk_mcp_server`+`@tool` 把 3 个草稿工具注册为进程内 MCP server（决策#29） |
| M3.1.2 Tool JSON Schema 定义 | ✅ | 2026-07-09 | 三个工具输入 JSON Schema（jsonschema Draft7 校验，单一真源同时作工具定义 inputSchema） |
| M3.1.3 Tool 调用拦截与存储 | ✅ | 2026-07-09 | handler 校验→落库（business_map→BusinessMapDraft / stakeholder→StakeholderCard(draft) / visit→VisitRecord(draft)）→SSE 推送 `draft_pending` 事件→回写 Claude；reviews.adopt 扩 stakeholder/visit 草稿分支（§3.3 自确认→reviewed） |
| M3.1.4 前端采纳交互 | ✅ | 2026-07-09 | ChatWorkspace 渲染 `draft_pending` 事件为「待采纳」卡片（结构化预览+采纳/驳回按钮）；采纳调 `api.adoptDraft`→POST /adopt；驳回=前端暂不采纳（草稿留存） |

**设计要点**：
- **注册机制（决策#29）**：Claude Agent SDK 支持「进程内 MCP server」（`create_sdk_mcp_server`+`@tool`，`McpSdkServerConfig`），无需起子进程。`build_draft_tool_server(ctx)` 把会话上下文（project_id/user_id/source_session_id/publish 回调）闭包注入 3 个 handler。Claude 侧工具名 `mcp__consultant_drafts__save_xxx_draft`，经 `allowed_tools` 放行，权限仍由 `tool_approval.auto_approve_tool` 放行。
- **校验单一真源**：JSON Schema 既作工具 inputSchema（Claude 据之生成结构化入参）又作 handler 入参校验（`jsonschema.Draft7Validator`）；非法入参返回 `is_error=True` + 人类可读错误回写 Claude 自我修正，不落库不推送。
- **草稿落库 + 采纳**：business_map→整图草稿单元（复用 M2.1 `upsert_draft`/`adopt_draft`，带版本快照语义）；stakeholder/visit→实体行 review_status=draft（复用 M2.2/M2.3 create）。统一采纳派发器 `reviews.adopt` 扩两分支：stakeholder_card_draft/visit_record_draft → draft→reviewed（§3.3 非 WF07 自确认，不进 pending_review 待审批列表，不生成版本快照）。
- **SSE 待采纳事件**：`{type:"draft_pending", entity_type, entity_label, draft_id, project_id, preview}`，由 handler 经 `ctx.publish` 推送（与 tool_use/tool_result 同走 on_message → run_state + SSE）。
- **会话↔项目绑定 = M3.4.2**：`stream_chat` 已支持 `draft_context` 参数（注入则挂载草稿 MCP server）；ChatSession 尚无 project_id 列，故 streaming.py 暂不构造 draft_context，待 M3.4.2 会话关联项目后接入。框架全链路由 handler 级测试覆盖（不依赖真实 Claude 会话）。

**回归测试**：test_draft_tools.py（14 全过：Schema 合法 + 校验通过/拒绝 / 三 handler 落库+推送+回写 / 非法入参 is_error 无副作用 / build_draft_tool_server 经 list_tools 暴露三工具 / reviews.adopt stakeholder+visit 草稿采纳 + 非法状态 400）。全量 **545 passed / 20 failed / 2 skipped / 3 errors**，相比 M2.4 基线（531 passed）passed +14（恰好新增），**fail 集未扩大**（20 fail+3 err 全为既有环境问题）。

**前端（M3.1.4）**：ChatWorkspace.tsx 新增 `DraftPart` + `foldEvents` 处理 `draft_pending` 事件；TurnView 渲染「待采纳」卡片（entityLabel + 待采纳徽标 + 结构化预览 + 采纳/驳回按钮）；采纳调 `api.adoptDraft`（POST /api/projects/{id}/adopt），状态机 adopting→adopted/error；驳回=前端暂不采纳（草稿留存可后续处理）。types 增 `draft_pending` ChatEvent + `AdoptResult`。**验证**：`tsc -b` + `vite build` 通过（71 模块，构建 1.33s）。前端无组件测试基建（既有 9 个测试均为 src/lib 纯函数 Node assert），UI 渲染以类型检查+生产构建验证。

### M3.4.2 项目级会话关联 ✅ 已完成（commit 本会话）

| 任务 | 状态 | 完成时间 | 备注 |
|------|------|---------|------|
| ChatSession 加 project_id | ✅ | 2026-07-09 | `chat_sessions.project_id`（FK projects ON DELETE SET NULL）+ 迁移 + idx_sessions_project 索引 |
| schemas/service/route 支持项目绑定 | ✅ | 2026-07-09 | CreateSessionRequest/SessionOut 增 project_id/project_name；create_session 校验成员资格（404/403）+ 未显式给 agent_id 时自动加载项目 Agent（§5.2） |
| streaming.py 接入 DraftToolContext | ✅ | 2026-07-09 | `_build_draft_context`（成员→上下文 / 非成员→None / 未绑定→None）+ `publish_draft_event`（draft_pending 同走 run_state+SSE，可重连回放）→ stream_chat(draft_context=…) |

**设计要点**：
- **绑定语义（决策#30）**：会话创建时可选传 `project_id`；绑定后该会话即为「项目级会话」——自动加载项目 Agent（`cs.agent_id = project.agent_id`，未显式给 agent_id 时），并在对话时挂载草稿工具上下文，使 AI 调 `save_xxx_draft` 写入对应项目的草稿区。普通会话（无 project_id）行为不变，不挂载草稿工具。
- **成员校验**：创建项目会话时用 `get_user_project_role` 校验（§3.5 项目内透明、项目外隔离），非成员 403、不存在 404。对话时再次校验（防御：用户退出项目后旧会话不再向无权项目写草稿，role 为 None 则不挂载）。
- **后台 runner 安全**：`project_id` 在 runner 前捕获为局部量（与既有 session_id/prior_session_id 同处理，因后台 runner 可能在请求会话关闭后仍运行，不直接访问 cs 对象）；`_build_draft_context` 入参显式传 project_id/source_session_id，不依赖 cs。
- **draft_pending 可回放**：M3.1 的 publish 回调在 streaming.py 构造为 `publish_draft_event`——草稿「待采纳」事件同走 `run_state_store.append_event` + SSE，客户端断开重连（/running/stream）仍可回放草稿卡片（补齐 M3.1 文档所述「与 tool_use/tool_result 同走 run_state + SSE」）。

**回归测试**：test_sessions_project_binding.py（11 全过：绑定项目+自动加载 Agent / 非成员 403 / 不存在 404 / 显式 agent 不被覆盖 / 列表含 project 字段 / `_build_draft_context` 成员·非成员·未绑定 / stream_session_chat 项目会话传 draft_context·普通会话不传 / draft_pending 入 run_state 可回放）。全量 **556 passed / 20 failed / 2 skipped / 3 errors**，相比 M3.1 基线（545 passed）passed +11（恰好新增），**fail 集未扩大**（20 fail+3 err 全为既有环境问题：企微注释致 ImportError、Windows 路径/符号链接、本地 DB 口令、config 默认值、Claude SDK 真实依赖；与本任务无关）。

### M3.2 七个 Skill 编写 ✅ 已完成（commit 本会话）

| 任务 | 状态 | 完成时间 | 备注 |
|------|------|---------|------|
| M3.2.1 WF02 consultant-upload | ✅ | 2026-07-09 | 资料上传与归档：7 类 materialType 分类 + 覆盖度评估 + 用户确认归档（无草稿工具，文件归档） |
| M3.2.2 WF03 consultant-gap-check | ✅ | 2026-07-09 | 信息缺口识别（辅助 Skill）：覆盖度计算 + 四类缺口维度 + 建议搜索关键词；WF06/WF07 前置自动执行 |
| M3.2.3 WF06 consultant-visit-plan | ✅ | 2026-07-09 | 拜访前方案：目标/沟通要点/访谈问题/资料清单 + 策略推理；前置 WF03；方案可归档个人空间 |
| M3.2.4 WF07 consultant-hypothesis-map | ✅ | 2026-07-09 | 假设地图分步生成：5 Step 强制定步（前置分析→L1→L2→L3→L4+跨层一致性）+ L1-L4 字段契约 + 搜索公开信息 → `save_business_map_draft`（map_type=hypothesis） |
| M3.2.5 WF09 consultant-interview | ✅ | 2026-07-09 | 拜访纪要结构化：四维度证据抽取（客户原话/痛点/角色态度/业务术语）→ `save_visit_record_draft` |
| M3.2.6 WF10 consultant-verify | ✅ | 2026-07-09 | 假设验证与现状更新：证据匹配 + 逐条对比 + 状态判定规则（强≥3成立…）+ 现状节点关联回假设 → `save_business_map_draft`（map_type=current，推翻入偏差池） |
| M3.2.7 WF12 consultant-stakeholder | ✅ | 2026-07-09 | 角色卡生成：客观/主观层 + 三维度加权评分（参与度×0.3+影响力×0.4+支持度×0.3）+ Champion 三要素 + 角色去重 → `save_stakeholder_card_draft` |

**设计要点**：
- **落点 = 版本化模板 + 启动播种（决策#31）**：master SKILL.md 置于包内版本化目录 `app/skills_seed/<name>/`（`claude_data/` 被 gitignore，是运行时数据，直接落那里会随运行时丢失）；新增 `workdir.seed_default_skills()` 在启动 `init_db` 后、`ensure_all_agent_workdirs` 前，把模板**非破坏性**播种到 `claude_data/skills/`（同名已存在则跳过，保留用户后台上传的自定义），使新建项目 Agent 经 `init_agent_workdir` 自动拷贝加载。目录名严格对齐 M1.3.7 `DEFAULT_PROJECT_SKILLS` 的 7 个名字。
- **草稿工具接线**：4 个产出结构化数据的 Skill（WF07/WF10→business_map、WF09→visit、WF12→stakeholder）SKILL.md 明确指示调用 `mcp__consultant_drafts__save_xxx_draft`，入参对齐 M3.1 工具 Schema（单一真源）；3 个非结构化 Skill（WF02 文件归档 / WF03 文本 / WF06 方案 Markdown）不引用草稿工具，输出走文件或文本。
- **方法论对齐规格**：WF07 L1-L4 字段契约严格对齐 §5.2 BusinessMapObject payload（5/8/11/9 要素 + 五维健康 + L3 先本体后 AI）；WF12 三维度评分公式与 Champion 三要素对齐 §5.2 StakeholderCard；WF10 状态判定规则对齐 §7.5（强≥3 成立…）；WF03 四类缺口维度（行业/场景/角色/证据）。
- **约束**：所有 Skill 遵守 runner rule_prompt——不调用 AskUserQuestion（分步确认用纯文本）、不泄露 Skill 元数据、不臆造数据（无依据留空标低置信度）、保持中文。

**回归测试**：test_consultant_skills.py（18 全过：7 文件齐备 / 名称与 DEFAULT_PROJECT_SKILLS 一致 / 每文件 frontmatter+WF 编码 / 4 草稿 Skill 指示正确工具 / 3 非草稿 Skill 不误引 / scan_skills 发现全部 7 个 / seed_default_skills 播种+非破坏性）。全量 **574 passed / 20 failed / 2 skipped / 3 errors**，相比 M3.4.2 基线（556 passed）passed +18（11 绑定 + 7 本任务新增；含 1 seed 测），**fail 集未扩大**（20 fail+3 err 全为既有环境问题，与本任务无关）。

### M3.4.1 WF chip 按钮 ✅ 已完成（commit 本会话）

| 任务 | 状态 | 完成时间 | 备注 |
|------|------|---------|------|
| 前端项目会话打通 | ✅ | 2026-07-09 | Session 类型加 project_id/project_name（同步后端 M3.4.2 SessionOut）；CreateSessionPayload 加 project_id；App.tsx 把 Topbar 的 selectedProject 传入 ChatWorkspace |
| 项目会话创建 | ✅ | 2026-07-09 | sendMessage 新建会话时若 selectedProject 非空→传 project_id（不传 agent_id，后端自动加载项目 Agent）；普通会话行为不变 |
| 5 个 WF chip | ✅ | 2026-07-09 | ChatInput 输入区上方加 5 个工作流 chip（生成假设地图/生成拜访前方案/整理拜访纪要/验证假设/营销地图），点击发 `/${command} ${hint}` 触发对应 Skill；仅项目上下文显示 |

**设计要点**：
- **触发机制（决策#32）**：chip 点击发送 `/${command} ${hint}`——`command` = Skill 名（复用既有命令菜单的斜杠命令机制：`scan_agent_commands` 已把 skills 暴露为 `/command`），`hint` = 一句中文意图作双重保险（既走 `/skill-name` 路径又给模型自然语言信号）。5 个 chip 映射 5 个产出型 Skill：WF07 consultant-hypothesis-map / WF06 consultant-visit-plan / WF09 consultant-interview / WF10 consultant-verify / WF12 consultant-stakeholder。
- **项目会话驱动**：Topbar 的 ProjectSelector（M1.3.9 selectedProject）传入 ChatWorkspace；新建会话绑定 project_id（后端 M3.4.2 自动加载项目 Agent 含 7 Skill/3 Plugin + 挂载草稿工具）。**零新 UI 入口**——复用既有项目选择器。
- **chip 显隐**：仅「项目上下文」显示——空状态 selectedProject 非空（待绑定）或当前会话 project_id 非空（已绑定）。普通会话/非项目会话不显示（5 个 Skill 绑定在项目 Agent，普通 Agent 无这些 Skill）。streaming 中 chip 禁用。
- **可视化项目绑定**：标题栏 + 会话列表项显示项目名 Tag；空状态显示「新会话将关联项目 X」横幅并隐藏智能体选择器（项目 Agent 固定）。

**验证**：纯前端任务，无后端改动 → 无需 pytest 回归。`tsc -b` 通过 + `vite build` 通过（71 模块，构建 1.24s，0 错误）。前端无组件测试基建（既有 9 个测试均为 src/lib 纯函数，本次未触及），UI 渲染以类型检查 + 生产构建验证（同 M3.1.4 前端验证口径）。

### M3.3 三个 Plugin 实施 ✅ 已完成（commit 本会话）

| 任务 | 状态 | 完成时间 | 备注 |
|------|------|---------|------|
| M3.3.1 consultant-router | ✅ | 2026-07-10 | 意图路由（斜杠/chip 直达→LLM 分类≥0.7→关键词兜底→chat 兜底）+ 7 类意图 + IntentRoutingLog 新表（commit 30c137f） |
| M3.3.2 consultant-search | ✅ | 2026-07-10 | search_web/search_company_registry/fetch_webpage 三进程内 MCP 工具 + 个人空间归档（去重）（commit b958e1b） |
| M3.3.3 consultant-defense | ✅ | 2026-07-10 | 防线1 道层 System Prompt 注入 + 防线2 PostOutputFilter 确定性指纹过滤（commit b958e1b） |

**架构（决策#33）**：三个 Plugin 的「绑定/发现/资产」由 `app/plugins_seed/<name>/` 版本化模板目录承载（`.claude-plugin/plugin.json` + Prompt/规则资产，供 SDK 加载 + scan_plugins 发现 + init_agent_workdir 拷贝），**实际运行逻辑在 app 层 Python 模块**（router.py / search_tools.py / defense.py）接入 streaming/runner。延续 M3.1/M3.2 既定的「app 层逻辑 + seed 模板」模式——SDK 插件 hook 脚本无法干净访问 DB/LLM/Material 且 Windows 脆弱难测，故真实逻辑放 app 层（同决策 #29 草稿工具选进程内 MCP 的理由）。`seed_default_plugins()`（镜像 seed_default_skills）启动时非破坏性播种 3 个 Plugin 到 `claude_data/plugins/`。

**M3.3.1 设计要点**：
- **三级路由（决策#33）**：路径 A（斜杠/chip 命中已知 Skill）→ 跳过意图识别直达（`confidence_source=chip`）；路径 B（自然语言）→ ① LLM 分类（DeepSeek flash，置信度≥0.7 直接路由，`llm`）→ ② 关键词兜底（命中唯一类路由，`keyword`）→ ③ 多类命中/零命中 → Chat Mode（`chat_fallback`，多类时 `needs_confirmation=True` 供前端未来弹窗）。路由到 Skill 时把提示改写为 `/<skill> <原提示>`，**复用 M3.4.1 斜杠命令触发机制**（scan_agent_commands 已把 skills 暴露为 /command）。
- **7 类意图**：hypothesis_map→WF07 / current_map_verify→WF10 / stakeholder_card→WF12 / interview_summary→WF09 / visit_plan→WF06 / file_upload→WF02（行为触发，不参与 NL 路由）/ chat。file_upload 与 chat 无关键词、skill=None。
- **IntentRoutingLog**：每次自然语言输入必入一条（session/project/user + prompt + 三级路由全过程：llm_label/llm_confidence/keyword_hits/llm_raw/confidence_source/final_prompt）。session_id 沿用 usage_events 的 plain String（chat_sessions.id 为 UUID 字符串主键，不加 FK 避免迁移复杂度）。
- **降级**：未配 DeepSeek 凭据 / LLM 调用失败 → classify 返回 None → 关键词兜底；路由整体异常只记日志不阻断对话（按原始提示继续）。门控：仅 `router_plugin_active(agent)`（项目 Agent）启用。
- **接入点**：streaming.runner() 在调 stream_chat 前，对项目 Agent 自然语言输入执行 route_user_prompt + log_routing，用 decision.final_prompt 替换下发提示。

**M3.3.2 设计要点**：
- **三工具 = 进程内 MCP server**（`build_search_tool_server(ctx)`，与 M3.1 草稿工具同模式，决策#29）：`mcp__consultant_search__search_web/search_company_registry/fetch_webpage`。SearchToolContext 闭包注入 workspace_root/project_id/user_id/source_session_id。
- **外部 HTTP 隔离**：所有联网调用在模块级 `_http_web_search/_http_company_registry/_http_fetch_webpage` + `_*_configured` seam，单测 monkeypatch 覆盖接线/归档/兜底，不依赖真实网络；真实连通性由运营 CC-21 保证。search_web/company_registry 未配置时返回明确兜底（AI 据已有资料作答），fetch_webpage 直接 httpx 抓取（HTML→文本，无需凭据）。
- **归档 + 去重（§7.8）**：搜索结果写 `<workspace>/公开信息/<safe-slug>.md`，同名文件已存在则跳过（同一关键词不重复归档）。safe_slug 保留中文。
- **接入点**：streaming 对项目 Agent（search_plugin_active）构造 SearchToolContext（workspace_root=会话工作区）；runner 注入后挂载 MCP server + 加入 allowed_tools。

**M3.3.3 设计要点**：
- **防线1（道层注入）**：runner 组装 system_prompt.append 时，defense_plugin_active(agent) 则前置 `load_dao_layer_prompt()`（dao_layer.md 全文，含身份/方法论三层道法器/根本准则），不可被 RAG 覆盖（§7.10 注入模式）。append = `"\n\n".join(dao_layer, agent_prompt, rule_prompt)`。
- **防线2（PostOutputFilter）**：streaming.on_message 对 `assistant_text` 事件应用 `apply_output_filter`（never_visible.json 规则：substring→replace / regex→re.sub，命中替换为 `[已过滤]`，非法正则跳过），**100% 确定性、不依赖 LLM**。思维链 assistant_thinking 不过滤（§8.2）。门控：仅 defense_plugin_active。
- **资产单一真源**：dao_layer.md / never_visible.json 置于 `app/plugins_seed/consultant-defense/rules/`（版本化），defense.py 经 `_plugins_seed_dir()` 读取。

**回归测试**：test_consultant_router.py（35 过：7 意图结构 / parse_slash / keyword_fallback 唯一·多·零 / _parse_llm_json 合法·fenced·embedded·非法·clamp / route_user_prompt 三级路由全覆盖 / classify_intent_llm env 处理与异常降级 / log_routing 落库 / seed+scan / streaming 集成路由改写+落库）、test_consultant_search.py（24 过：Schema 校验 / list_tools 暴露三工具 / allowed_names / _safe_slug / 归档写入+去重 / _html_to_text / search_web 未配置·已配置归档·失败·非法 / registry 未配置·已配置·无结果 / fetch_webpage 成功·非http·失败 / streaming 集成项目会话挂载·普通会话不挂载）、test_consultant_defense.py（15 过：道层资产 / never_visible 加载 / apply_filter substring·regex·多规则·无命中·空规则·非法正则·默认资产 / defense_plugin_active / seed+scan / streaming 集成 assistant_text 过滤+thinking 不过滤·普通会话不过滤）。全量 **648 passed / 20 failed / 2 skipped / 3 errors**，相比 M3.4.1 基线（574 passed）passed +74（35 router + 24 search + 15 defense），**fail 集未扩大**（20 fail+3 err 全为既有环境问题：企微 ImportError、Windows 路径/符号链接、本地 DB 口令、config 默认值、Claude SDK 真实依赖；与本任务无关）。




