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




