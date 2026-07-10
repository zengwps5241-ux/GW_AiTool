# AI 顾问作战台 · 自动决策记录

> 遇到设计决策、技术选型或需求歧义时，自动采用行业最推荐方案，并在此记录。

---

## 决策 #1：认证体系实现方案

- **背景**：需求要求从企微 SSO 切换为自建注册登录体系（手机号/用户名+密码）
- **选项**：
  - A) JWT Token 认证
  - B) 继续使用现有 Session Cookie 认证
- **选择**：B — 继续使用 Session Cookie
- **理由**：项目已有完整的 Session 认证基础设施（SessionMiddleware、auth_guard 中间件、current_user 依赖），切换到 JWT 需要重写大量中间件和前端逻辑，收益不大。Session Cookie 方案对于当前 1-3 名用户规模完全够用，且更安全（HttpOnly cookie 不可被 JS 读取）。

## 决策 #2：密码哈希方案

- **背景**：需要为自建注册登录体系选择密码哈希方案
- **选项**：
  - A) 引入新的哈希库
  - B) 复用现有 passlib + bcrypt
- **选择**：B — 复用现有 passlib + bcrypt
- **理由**：项目已有 `app/core/security.py` 提供 `hash_password` 和 `verify_password`，使用 passlib + bcrypt，无需引入新依赖。

## 决策 #3：User 模型扩展策略

- **背景**：需求要求新增 phone（唯一）、password_hash（已有）、status、registration_source 字段
- **选项**：
  - A) 在现有 User 模型上直接添加新字段
  - B) 创建新的 UserProfile 模型关联 User
- **选择**：A — 直接在 User 模型上添加
- **理由**：字段数量少（4个），且与 User 强相关，拆分模型增加 JOIN 查询复杂度，无实际收益。现有 password_hash 字段已存在，phone 字段与现有 mobile 字段合并使用（mobile 设为唯一约束）。

## 决策 #4：前端 UI 组件方案

- **背景**：需要新增登录表单、注册页面、审批页面等 UI 组件
- **选项**：
  - A) 引入 UI 框架（如 Ant Design、shadcn/ui）
  - B) 继续使用项目现有的手写 UI 组件（ui/index.tsx）
- **选择**：B — 继续使用手写 UI 组件
- **理由**：项目已有统一的 UI 原语（Btn、Card、Tag、Avatar、Toast），引入新框架会导致风格不一致且增加依赖。保持一致性更重要。

## 决策 #5：前端路由方案

- **背景**：需要新增多个页面视图
- **选项**：
  - A) 引入 react-router
  - B) 继续使用现有 ViewName 状态路由
- **选择**：B — 继续使用 ViewName 状态路由
- **理由**：项目已有完整的 ViewName 路由体系，所有页面切换通过 useState 管理。引入 react-router 需要重构整个 App.tsx，风险大且收益小。当前方案对 1-3 用户规模完全够用。

## 决策 #6：测试登录 fixtures 改用自建注册登录流程（M1.1 测试补齐）

- **背景**：M1.1 将认证体系从企微 SSO 切换为自建注册登录，并注释了 wechat_work.py / departments.py 及 auth.py 中的企微路由。但 conftest.py 的 `logged_in_client`/`admin_client`/`super_client`/`other_logged_in_client` 仍驱动企微二维码流程（qrcode-config → callback → poll-code → login-by-code），这些端点已 404，导致约 30 个测试文件的登录 fixture 全部报错。
- **选项**：
  - A) 恢复企微代码（与 M1.1 决策相悖）
  - B) 改写 fixtures 为自建注册登录流程（DB 建用户激活 + /api/auth/login）
  - C) 各测试自建临时用户（重复代码、难维护）
- **选择**：B — 改写为自建注册登录流程
- **理由**：M1.1 已明确"企微代码注释保留，自建认证为正式体系"，测试必须与生产代码一致。B 方案一处改动即可修复全部依赖 fixture 的测试，且更贴近真实生产链路。同时修正 conftest 中硬编码的 DB 口令 `postgres:postgres` → `postgres:dev`（与 backend/.env 一致、本地可跑）。test_auth_api.py 同步重写：移除企微专用测试（约 15 个，测试已注释的死代码），补齐注册/登录/审批完整用例（24 个）。

## 决策 #7：组织树自引用关系修复（M1.2.1）

- **背景**：organization.py 初版对 `children` 和 `parent` 两个关系都设了 `remote_side="Organization.id"`，导致 SQLAlchemy 报 "both of the same direction MANYTOONE"。
- **选择**：`parent`（多对一）设 `remote_side="Organization.id"`；`children`（一对多）不设 remote_side；两者 back_populates 互指；children 加 `cascade="all, delete-orphan"`。
- **理由**：这是 SQLAlchemy 自引用邻接表（adjacency list）的标准写法——多对一端用 remote_side 指向被引用主键，一对多端无需设置。

## 决策 #8：批量导入按名称引用父级（M1.2.4）

- **背景**：批量导入 CSV/JSON 时，父级组织在导入过程中才创建，导入方无法预先知道 parent_id。
- **选择**：导入行用 `parent_name`（名称）引用父级，service 层在导入时维护"名称→id"映射（含已存在 + 本批次已 flush 的新增），按名称解析 parent_id；负责人用 `head_user_username` 引用 users 表。
- **理由**：名称引用对人工编辑 CSV 最友好；运行时解析避免了要求用户先查 id 的痛点。同名歧义取"最近创建"匹配，已在导入结果中暴露 errors 供人工核对。

## 决策 #9：组织 API 前缀与权限（M1.2.3）

- **选择**：组织 CRUD/树/成员/导入路由统一挂在 `/api/admin/organizations`，依赖 `require_admin`（admin+super 可访问，普通 user 403）。
- **理由**：对齐需求规格 §2.1「组织架构」位于"设置（admin 可见）"分组；与现有 `/api/admin/login-whitelist` 等 admin 路由风格一致。

## 决策 #10：业务实体主键采用 Integer 自增（非 UUID）（M1.3）

- **背景**：需求规格 §5.2 Customer/Project 标注 "auto (UUID)"，但全库现有模型（User/Organization/Agent/Category…）均为 Integer 自增主键，仅 ChatSession 因 SDK 用 String-UUID。
- **选项**：A) 按规格用 UUID 主键；B) 沿用 Integer 自增，保持全库一致。
- **选择**：B — Integer 自增。
- **理由**：交接说明已提示「业务实体主键建议 UUID，FK 到 users.id/agents.id 是 INTEGER」（即 UUID 表会带 Integer 外键，类型异构）。本系统为内部顾问工具（1-3 人），UUID 防枚举收益可忽略；而全库 Integer 一致可规避 mapper 分裂 / 外键类型混杂 / reload 舞蹈等已踩过的坑（与决策 #1-#5「复用现有 / 一致性优先」一脉相承）。FK 到 users.id/agents.id/organizations.id 均为 Integer，天然对齐。后续如确需对外暴露不可枚举 ID，可在响应层加 UUID 投影，无需改主键。

## 决策 #11：项目 Agent 命名规则（M1.3.7）

- **背景**：规格 §5.2 规定项目 Agent `code = consultant_{projectId前8位}`（针对 UUID 设计）。主键改 Integer 后（决策 #10）取前 8 位无意义。
- **选择**：`code = consultant_{project.id}`（整数 id，全局唯一）；`name = "{项目名} Agent"`；初始 system_prompt 注入项目上下文骨架（客户/目标），完整「道层」防御 Prompt 留待 Phase 3 consultant-defense Plugin 注入。
- **理由**：整数 id 保证 Agent.code 唯一约束成立；命名直观可追溯。标准 Skill/Plugin 名称（7 Skill + 3 Plugin）先以字符串占位绑定，SKILL.md 实体在 M3.2 落地，`init_agent_workdir` 会静默跳过尚不存在的模板源。

## 决策 #12：项目级权限判定（M1.3.8）

- **背景**：规格 §3 三层权限（系统级 admin/user + 项目级 Owner/Deputy + 跨项目隔离）需落到 FastAPI 依赖。
- **选择**：
  - 成员判定 `get_user_project_role`：admin/super → "admin"（§3.2 可访问任意项目）；否则 `project_members` 命中 → owner/deputy；否则所属组织（`user_organizations`）命中 `project_department_access` → deputy（部门授权视为 deputy 级，可见项目全部数据）。
  - `require_project_member`：成员或 admin 放行，否则 403。
  - `require_project_owner`：admin/super 或 role=owner 放行；deputy → 403「仅 Owner 可执行此操作」；非成员 → 403。
  - 权限逻辑放纯数据层 `app/modules/projects/access.py`，HTTP 层 `app/api/project_deps.py` 仅翻译 404/403（避免 modules → api 反向依赖）。
- **理由**：部门授权→deputy 的映射对齐 §3.5「被邀请/被授权即获得全部数据访问权」。未加 dev 环境绕过：项目隔离是核心特性，测试以 APP_ENV=production 运行本就强制校验，且 admin/super 已能越权。

## 决策 #13：项目与 Agent 原子创建 / 删除级联（M1.3.6 / M1.3.7）

- **选择**：创建项目时同一事务内「建项目（agent_id 暂空）→ flush → 建 Agent → 回填 agent_id → 建 Owner 成员记录」一次 commit，`init_agent_workdir` 放提交之后（文件系统副作用不回滚 DB）。删除项目时级联（DB ON DELETE CASCADE 清 members/dept-access）并删除自动创建的项目 Agent + `remove_agent_workdir`（失败不阻断）。
- **理由**：保证项目与 Agent 原子性，避免半成品；项目 Agent 是项目专属资源，删项目应清理，避免孤儿 Agent（chat_sessions.agent_id FK ON DELETE SET NULL，M1.3 阶段项目尚无会话，无副作用）。

## 决策 #14：单 Owner 不变式 + 客户列表可见性（M1.3.5 / M1.3.6）

- **选择**：① 项目保持单一 Owner（创建时确立），`add_member` 拒绝 role=owner、`remove_member` 拒绝移除 Owner（所有权转让不在 M1.3 范围）。② 客户列表对普通用户 = 「自己创建的客户 ∪ 可访问项目所属客户」（创建者即使尚无项目也能在选择器看到自己的客户）；客户编辑/删除仅限 admin 或创建者，删除时存在项目则拒绝。
- **理由**：单 Owner 简化权限与 WF07 审核流（§3.3/§3.4）。客户列表合并「自建」避免「我建了客户却在选择器看不到」的体验问题，同时跨用户隔离不变。

## 决策 #15：Customer.orgStructure 字段延后（M1.3.1）

- **背景**：规格 §5.2 Customer 含 `orgStructure`（嵌套 departments + stakeholderCardIds），但 stakeholderCardIds 引用营销地图角色卡（M2.2），Phase 1 尚不存在。
- **选择**：M1.3 仅实现核心字段（name/industry/scale/region/description/created_by + visibility/sensitivity_level），暂不建 orgStructure 列；待营销地图（M2.2）落地时以可空 JSON 列追加（migrations.py 的 ALTER TABLE 加列模式已成熟）。
- **理由**：避免引入引用尚未存在实体的结构；visibility/sensitivity_level 已含，支撑 §3.5 跨项目公开机制；延后字段后期加列成本低。

## 决策 #16：业务地图对象 payload 用 JSONB，schema 不约束内部结构（M2.1.1）

- **背景**：规格 §5.2 BusinessMapObject.payload 按 L1/L2/L3/L4 层级差异化，含大量专属字段 + fiveDimHealth 嵌套结构。
- **选择**：payload 列用 PostgreSQL `JSONB`（来自 sqlalchemy.dialects.postgresql）；Pydantic schema 仅声明 `dict[str, Any] | None`，**不**用嵌套模型约束 payload 内部（层级字段结构由 Skill 结构化输出与前端约定）。
- **理由**：JSONB 二进制存储、可索引、支持 JSON 查询，是 PG 存半结构化大对象的标准选择。payload 字段集合会随方法论（L1/L2/L3/L4 五要素/八要素/十一要素）演化，用 schema 强约束会频繁返工且与 Skill 输出耦合；宽松 dict + Skill/前端契约更灵活。sharedWith 亦用 JSONB（uid 列表）。

## 决策 #17：业务地图默认查询只返回 reviewed；手动新增默认 reviewed（M2.1.5 / §7.3）

- **背景**：§7.3 数据页面单一真源 = `reviewStatus = 'reviewed'`；M4.1.8 手动新增「直接进正式库」。
- **选择**：`list_objects` 默认过滤 `review_status='reviewed'`；显式传 `review_status` 或 `include_drafts=true` 才查其它状态。BusinessMapObjectCreate 的 `review_status` 默认 `'reviewed'`（手动新增立即可见）。
- **理由**：把 §7.3「页面只看 reviewed」做成安全默认，避免草稿/pending 数据意外泄漏到页面；AI 产出走草稿→采纳流程（不直接用此 schema 入库），故默认 reviewed 不冲突。

## 决策 #18：草稿采纳的 Owner/Deputy 区分 + 采纳后生成版本快照（M2.1.7 / §3.4 §7.1 §7.4）

- **选择**：`adopt_draft` 按采纳者项目角色决定对象 review_status——Owner/admin → `reviewed`（直接发布）；Deputy → `pending_review`（待 Owner 审核，§3.4）。采纳成功后对项目当前 reviewed 对象生成 `BusinessMapVersion` 快照（version_number 自增），并把草稿置 `adopted`。整个业务地图为一个草稿单元（draft_data = `{objects:[...]}`，§7.1.7）。
- **理由**：把 §3.4「Owner 采纳直接发布 / Deputy 采纳待审核」落到采纳动作；版本快照在采纳后生成（捕获采纳后的正式状态），支撑 §7.4 版本对比与回滚。草稿单元粒度=整图，对齐 §7.1.7。

## 决策 #19：版本回滚仅替换 reviewed 正式数据 + 自动留存审计快照（M2.1.8 / §7.4）

- **选择**：`rollback_to_version` 仅 Owner/admin 可执行；先对当前 reviewed 对象生成一条审计版本快照（保证回滚可追溯），再删除当前 reviewed 对象、用目标版本快照重建。草稿 / pending_review 对象不受影响。
- **理由**：回滚是破坏性操作 → 限 Owner（决策 #12）。仅替换 reviewed（页面真源），避免误删进行中的草稿/pending 数据。审计快照使回滚本身可被「撤销」，符合版本管理可追溯原则。

## 决策 #20：五维健康采用简单规则版（占位，待总纲文档）（M2.1.9 / 风险 #5）

- **背景**：§7.7 五维健康计算规则需对齐总纲《企业数字健康分层地图·整体说明（V2.0）》（本仓库未含）；开发计划风险 #5 明确「M2.1.9 先实现简单规则版本，P5 打磨」。
- **选择**：`health.py` 以「关键字段完整度」启发式给 1-5 分（按 L1/L2/L3 各自的关键字段填充比例映射），写回 `payload.fiveDimHealth` 并标 `_healthSource`（auto/manual）。L4 无五维健康（规格 L4 无 fiveDimHealth）。
- **理由**：在总纲观测体系落地前提供可用的计算/手动覆盖服务骨架与 API（POST 计算 / 批量重评估 / PUT 手动覆盖），P5 对齐总纲时只需替换 `compute_five_dim_health` 规则函数，调用方不变。

## 决策 #21：角色卡分层用 JSONB + 综合评分服务端计算（M2.2.1 / §5.2）

- **选择**：StakeholderCard 的 objectiveLayer / subjectiveLayer / behaviors / stanceChangeLog 均为独立 JSONB 列（schema 层不约束内部结构，由 Skill/前端契约）。写入时 service 层按 §5.2 公式 `compositeScore = round(engagement×0.3 + influence×0.4 + support×0.3)`、`gradeLevel（8-10 Champion / 5-7 倾向我方 / 3-4 中立 / 1-2 反对）` 自动算回 subjectiveLayer，前端无需自己算。
- **理由**：与决策 #16 一致（半结构化大对象用 JSONB、schema 不强约束）。评分公式是确定规则，服务端集中计算避免各端重复实现/不一致；stance 筛选用 PG JSONB `subjective_layer->>'stance'` 查询。

## 决策 #22：角色关系显式建模 + 关系网络图端点（M2.2.2 / M2.2.6 / §5.2）

- **选择**：StakeholderRelation 显式存 from_card_id/to_card_id/relation_type（reports_to/influences/collaborates/opposes），替代角色卡 reportsTo 文本字段。提供 `GET /stakeholder-relations/graph` 返回 `{nodes:[角色卡], edges:[关系]}` 供前端 ReactFlow/D3 渲染。建关系时校验两端角色卡存在且非自环。
- **理由**：§5.2 V2.2 明确要求显式关系模型支撑关系网络图；nodes=reviewed 角色卡、edges=全部关系，结构直接对应图可视化。

## 决策 #23：态度变化记录作为可复用服务函数（M2.2.9 / §7.6）

- **背景**：§7.6 要求「新证据关联角色卡时自动生成 stanceChangeLog」，但证据（EvidenceSource）属 M2.3，本阶段尚不存在。
- **选择**：实现纯服务函数 `record_stance_change(db, project_id, card_id, from, to, reason)`：追加 `{date, from, to, reason}` 到 stanceChangeLog 并联动更新主观层 stance。同时暴露 `POST /stakeholder-cards/{id}/stance-changes` 供手动追加。M2.3 证据联动会直接调用同一服务函数实现「自动记录」。
- **理由**：把「记录」逻辑与「触发条件」解耦——触发条件（证据关联）在 M2.3 接，记录逻辑现在就绪且可测，避免回头改。

## 决策 #24：知识库项目级存储（M2.2.4）

- **背景**：§2.4 称知识库为「跨客户通用 / 团队共享资产」，但开发计划 M2.2.4 的 KnowledgeBase 模型带 `projectId`。
- **选择**：按开发计划实现为 project_id 必填（FK projects CASCADE），category ∈ role_recognition/behavior_quick_ref/onboarding_guide。「跨客户通用」的团队共享诉求后续通过 §3.5 公开机制（isPublic/团队空间）满足，不另建全局表。
- **理由**：开发计划是实施权威；项目级存储与其它营销地图实体一致，权限/隔离复用 require_project_member；跨客户共享用既有的公开机制更统一，不引入全局表带来的权限复杂度。

## 决策 #25：拜访记录派生统计不落库 + JSONB 参与人/角色筛选（M2.3.1 / M2.3.2 / M2.3.3）

- **背景**：规格 §5.2 VisitRecord 含 `evidenceCount`/`verifiedHypotheses` 两个派生字段，且需按参与角色卡筛选拜访。
- **选择**：
  - `evidence_count`/`verified_hypotheses` **不落库**，service 读取时按关联证据动态计算（evidence_count = 该拜访 reviewed 证据数；verified_hypotheses = 这些证据中 distinct 非空 relatedHypothesisId 数）。Out schema 填充返回。
  - 按角色卡筛选用 PG JSONB `@>` 数组包含（`participants_client @> '[card_id]'::jsonb`），命中 participants_client 或 related_card_ids 任一。
  - participantsOur/Client、keyTakeaways、sharedWith、relatedCardIds 均 JSONB 列，schema 不约束内部结构（与决策 #16/#21 一致）。
- **理由**：派生统计落库需在证据增删时同步维护计数，易出现不一致；动态计算保证始终准确（拜访列表规模小，无性能压力）。用 `@>` 数组包含而非 text cast contains，避免 card_id=1 误匹配 [11] 的正确性 bug。

## 决策 #26：证据验证联动规则版（强度计数）+ 推翻自动入偏差池（M2.3.5 / §7.5）

- **背景**：§7.5 要求「证据关联假设节点 → AI 给建议验证状态 → 人工确认 → 更新 verificationStatus + 偏差池自动新增」。M2.3 为数据层，尚无真实 AI。
- **选择**：
  - `suggest_verification_status`：聚合假设节点全部 reviewed 证据按强度计数 → 规则建议（0→未验证 / 强≥3→成立 / 强≥1 或 中≥2→部分成立 / 仅弱→待补充），附 strong/medium/weak 计数与 evidence_ids 便于前端展示。
  - `confirm_verification`：人工确认（status 缺省采纳建议）→ 更新假设节点 verificationStatus；若确认为「推翻」→ 自动新增一条 `current` 型 BusinessMapObject（verificationStatus=推翻、linkedHypothesisId 指回假设、name 加「（偏差）」后缀）作为偏差池条目；已存在同假设的推翻型 current 节点则复用不重复创建（§7.5.3/§7.5.4 现状从假设复制并标记）。
- **理由**：偏差池 = verificationStatus=推翻 的节点（规格 line 203/1127）；推翻时复制假设为 current 节点并标推翻，既满足「偏差池自动新增一条记录」又满足「现状从假设复制」。规则版建议状态在真实 AI 落地前提供可测骨架，P5 接 AI 时只需替换 suggest 实现，确认/偏差逻辑不变。

## 决策 #27：态度变化自动触发的条件与字段扩展（M2.3.5 / §7.6）

- **背景**：§7.6 要求「证据 sourceRoleId 关联角色卡且内容暗示态度变化时自动生成 stanceChangeLog」，但 EvidenceSource 规格字段不含立场 from/to，无法确定变化内容。
- **选择**：
  - EvidenceSource 扩展两个可选列 `implied_from_stance`/`implied_to_stance`（String nullable，文档说明为 §7.6 扩展字段）。
  - 触发条件（仅创建时触发一次，避免重复）：`evidence_type='角色态度信号'` + `source_role_id` 非空 + 两个 stance 字段齐备 → 调用 M2.2 `record_stance_change`（追加 stanceChangeLog + 联动主观层 stance，决策 #23 的可复用函数）。非角色态度信号类证据（如客户原话）即便关联角色卡也不触发。
  - 证据关联的拜访/角色卡/假设必须属本项目，跨项目关联 → 400。
- **理由**：立场 from/to 是记录态度变化的必要数据，规格遗漏故补两个可选列（向后兼容）。把「触发条件」收窄为「角色态度信号类 + 显式 stance」，使自动记录确定可测、不误触；复用 M2.2 已实现的 record_stance_change，记录逻辑零重复。仅创建时触发避免编辑证据反复追加日志（编辑场景由顾问手动维护）。

## 决策 #28：M2.4 采纳/审批——保留各模块 adopt + 新增统一审批层（实体注册表）（M2.4 / §3.3 §3.4 §7.1 §7.3）

- **背景**：M2.1 已在 business_map 实现 `/drafts/{id}/adopt`（Owner→reviewed / Deputy→pending_review + 版本快照，决策 #18）。M2.4 要求「跨模块统一的采纳/审批层」：`POST /api/projects/{id}/adopt`、`GET /pending-reviews`、`POST /reviews/{type}/{id}/approve|reject`。需抉择：抽象一个通用 adopt 服务复用各模块，还是各模块保留各自 adopt + 新增统一审批列表 API。
- **选择**：**保留各模块自有的 adopt + 新增统一审批层**（`app/modules/reviews/`，实体注册表模式）。
  - **采纳（adopt）保留模块自有**：business_map.adopt_draft 带「整张图为一个草稿单元（§7.1.7）+ 采纳即版本快照（§7.4/#18）」的专有语义，仅业务地图支持版本回溯（§7.4），抽象为通用服务会丢失这些。统一 `POST /adopt` 是**派发器**：按 `entity_type` 委派——`business_map_draft`→`business_map.adopt_draft`；营销/拜访草稿留待 M3.1.1（`save_xxx_draft` 工具）落地后扩展。不与 `/business-map/drafts/{id}/adopt` 重复（前者是统一入口/后者是模块入口，逻辑单一来源）。
  - **统一审批层（新）**：四类可审批实体（BusinessMapObject/StakeholderCard/VisitRecord/EvidenceSource）共享 `review_status`/`reviewed_by`/`reviewed_at` 三列，故用「实体注册表」`REGISTRY` 把列表/审批动作参数化——`list_pending_reviews` 跨模块聚合 `pending_review`，`approve_review`/`reject_review` 统一翻这三列。新增可审批实体只需登记一行。
  - **§3.3 审批范围**：规格仅 WF07（业务地图）Deputy 产出需 Owner 审核；非 WF07（营销/拜访）Owner+Deputy 均可自确认。故 adopt 时 business_map Deputy→pending_review（需审，决策 #18 已实现），营销/拜访未来的 adopt 将 Deputy→reviewed（自确认，§3.3）不进待审批列表；统一审批机制对「任何 pending_review」通用，不限定来源。
  - **权限**：`GET /pending-reviews` 用 `require_project_member`（§3.5 项目内透明）；`approve`/`reject` 用 `require_project_owner`（决策 #12，破坏性/发布操作限 Owner）；`adopt` 用 `require_project_member`（采纳者是产出方，角色决定状态）。驳回意见 comment M2.4 不持久化（Phase 3 对话 Banner 审核流承载「修改意见」）。
- **理由**：采纳的草稿单元粒度+版本快照是业务地图专有（§7.4 明确营销/拜访不需版本回溯），强抽象会污染通用层；而「跨模块待审批聚合 + Owner 审批」是真正共有的需求，注册表模式以最小耦合覆盖且易扩展。与决策 #16/#21（半结构化用 JSONB、不强约束）、#17/#18（reviewed 真源 + Owner/Deputy 区分）一脉相承。

## 决策 #29：M3.1 草稿工具用「SDK 进程内 MCP server」注册，校验单一真源（M3.1.1 / M3.1.2 / M3.1.3）

- **背景**：开发计划 M3.1.1 要求「扩展 guard.py 工具钩子，支持注册自定义 Tool（save_business_map_draft / save_stakeholder_card_draft / save_visit_record_draft）」。需抉择：自定义工具如何让 Claude 可调用 + 入参如何校验 + 草稿如何落库 + 如何回推前端。
- **选择**：用 `claude_agent_sdk.create_sdk_mcp_server` + `@tool` 把 3 个草稿工具注册为**进程内 MCP server**（新模块 `app/integrations/claude/tools.py`）。
  - **机制**：SDK 原生支持「进程内 MCP server」（`McpSdkServerConfig`，instance=`mcp.server.Server`），无需起子进程/IPC。`build_draft_tool_server(ctx)` 闭包注入会话上下文（project_id/user_id/source_session_id/publish），Claude 调用 `mcp__consultant_drafts__save_xxx_draft` → SDK 路由到 handler。工具名经 `draft_tool_allowed_names()` 加入 `allowed_tools`，权限仍由 `tool_approval.auto_approve_tool` 放行（安全边界由 handler 自身校验保证）。
  - **为何不用 PreToolUse hook 承载**：PreToolUse hook（guard.py）只能 allow/deny + 设上下文，**不能合成工具结果**；而草稿工具需「校验→落库→回写结果文本」三步，必须由可执行 handler 完成。故 guard.py 的 Bash 黑名单/文件锁安全钩子保持不变，草稿工具的拦截/校验/落库在 MCP handler 内完成（同处 integrations/claude/ 包，符合「工具钩子位于 integrations/claude」）。
  - **校验单一真源**：每个工具的 JSON Schema 既作工具 inputSchema（Claude 据之生成结构化入参）又作 handler 入参校验（`jsonschema.Draft7Validator` 经 `validate_tool_input`）。非法入参返回 `is_error=True` + 人类可读错误回写 Claude（自我修正），不落库不推送。
  - **草稿落库 + 采纳**：business_map→整图草稿单元（复用 M2.1 `upsert_draft`/`adopt_draft`，带版本快照语义）；stakeholder/visit→实体行 review_status=draft（复用 M2.2/M2.3 create）。统一采纳派发器 `reviews.adopt`（决策 #28）扩两分支：stakeholder_card_draft/visit_record_draft → draft→reviewed（§3.3 非 WF07 自确认，不进 pending_review 待审批列表，不生成版本快照，故 AdoptResult.version_number=0）。
  - **SSE 待采纳事件**：handler 经 `ctx.publish` 推送 `{type:"draft_pending", entity_type, entity_label, draft_id, project_id, preview}`，与 tool_use/tool_result 同走 on_message → run_state + SSE，前端 M3.1.4 渲染为采纳/驳回卡片。
- **理由**：SDK 进程内 MCP server 是「让 Claude 调用自定义 Python 工具」的原生正确路径（性能/调试/进程简洁均优），避免造子进程或假装「扩展 guard.py」（hook 无法回写结果）。JSON Schema 双用作工具定义与校验，消除「定义/校验两套 schema 漂移」。草稿落库复用 M2.1/M2.2/M2.3 已测的 create/upsert，零新表。会话↔项目绑定（draft_context 的 project_id 来源）属 M3.4.2，本任务把 `stream_chat` 接 `draft_context` 参数、框架全链路用 handler 级测试覆盖（不依赖真实 Claude 会话，与 test_claude_runner 同类环境依赖测试隔离）。

## 决策 #30：M3.4.2 会话↔项目绑定——project_id 列 + 创建期成员校验 + 对话期防御性重校验 + publish 走 run_state（M3.4.2 / §3.5 §5.2）

- **背景**：M3.1 的 `stream_chat` 已支持 `draft_context` 参数，但 ChatSession 无 project_id 列、streaming.py 不构造 DraftToolContext，草稿工具未接入对话流。M3.4.2 要求「会话创建时关联 projectId，会话内自动加载项目 Agent（含 Skill/Plugin 绑定）」。需抉择：列存 project_id 还是派生？成员校验放哪层？草稿 publish 是否入 run_state？
- **选择**：
  - **列存 project_id（FK projects ON DELETE SET NULL）**：项目级会话是显式语义（绑定后才挂草稿工具/加载项目 Agent），用一列表达比「靠 agent_id 反查项目」更直接、可索引、可空（普通会话 = 无项目）。创建期 `agent_id is None` 时自动取 `project.agent_id`（§5.2），显式给 agent_id 则尊重（不覆盖）。
  - **成员校验两道**：创建期在路由层用 `get_user_project_role` 翻 404/403（§3.5，与 project_deps 同模式）；对话期在 `_build_draft_context` 再校验一次——用户退出项目后旧会话 role 为 None 则不挂载草稿工具（防御：避免向无权项目写草稿）。
  - **后台 runner 不访问 cs**：`project_id`/`session_id`/`prior_session_id` 在 runner 创建前捕获为局部量（后台 runner 可能在请求会话关闭后仍运行，expire_on_commit=False 虽使 detached 属性可读，但与既有写法保持一致更稳）；`_build_draft_context` 入参显式接收 project_id/source_session_id，不依赖 cs 对象，便于单测。
  - **publish 走 run_state + SSE**：M3.1 的 publish 回调在 streaming.py 构造为 `publish_draft_event`——草稿「待采纳」事件同走 `run_state_store.append_event` + SSE，使客户端断开重连（`/running/stream`）仍可回放草稿卡片，兑现 M3.1 文档「与 tool_use/tool_result 同走 run_state + SSE」。
- **理由**：列存 project_id 是最小且可表达的方案（可空=普通会话不变，FK 级联删除安全）；两道成员校验兼顾「创建期清晰报错」与「对话期防御」；publish 入 run_state 补齐 M3.1 的回放韧性。全链路由 mock stream_chat 的接线测试覆盖（不依赖真实 Claude 会话）。

## 决策 #31：M3.2 七个 Skill 落点 = claude_data/skills 模板目录，草稿 Skill 对齐 M3.1 工具 Schema（M3.2 / §4.2 §5.2 §6.2 §7.5）

- **背景**：M3.2 要求编写 7 个 Skill（WF02/03/06/07/09/10/12）的 SKILL.md。需抉择：SKILL.md 放哪里？哪些 Skill 调草稿工具？字段契约写到什么粒度？
- **选择**：
  - **落点 = 版本化模板目录 + 启动播种**：master SKILL.md 置于包内版本化目录 `app/skills_seed/<name>/`（而非 `claude_data/skills/`——后者被 `.gitignore` 视为运行时数据，直接落那里模板会随运行时数据丢失且无法版本化）。新增 `workdir.seed_default_skills()`：启动时（`init_db` 后、`ensure_all_agent_workdirs` 前）把 `app/skills_seed/*` **非破坏性**播种到 `claude_data/skills/`（同名已存在则跳过，保留用户经管理后台上传的同名自定义）。播种后 `init_agent_workdir` 即可把 Skill 拷贝进项目 Agent 工作目录，`scan_skills()` 也能扫描到。目录名严格对齐 M1.3.7 `DEFAULT_PROJECT_SKILLS` 的 7 个名字（consultant-upload/-gap-check/-visit-plan/-hypothesis-map/-interview/-verify/-stakeholder）。既有项目 Agent 需 reinit 同步（运营步骤，非本任务）。
  - **草稿工具接线（4 个结构化 Skill）**：WF07/WF10（假设/现状地图）→ `save_business_map_draft`（map_type=hypothesis/current）；WF09（拜访纪要）→ `save_visit_record_draft`；WF12（角色卡）→ `save_stakeholder_card_draft`。SKILL.md 用代码块示范调用 `mcp__consultant_drafts__save_xxx_draft`，入参与 M3.1 工具 JSON Schema（单一真源）对齐。3 个非结构化 Skill（WF02 文件归档 / WF03 缺口文本 / WF06 方案 Markdown）不引用草稿工具——WF02 走文件移动到个人空间（§6.2）、WF03 输出缺口报告文本、WF06 输出方案 Markdown（可 Write 归档）。
  - **字段契约内嵌**：把规格 §5.2 的 L1-L4 payload 要素、StakeholderCard 三维度评分公式（参与度×0.3+影响力×0.4+支持度×0.3，Champion 三要素）、§7.5 假设状态判定规则（强≥3 成立…）、§6.2 七类 materialType 直接内嵌进对应 SKILL.md，使 AI 无需另查文档即可产出对齐规格的结构化输出。
  - **WF07 五步强制定步**：Step1 前置分析+WF03 缺口 → Step2 L1 → Step3 L2 → Step4 L3（先本体后 AI）→ Step5 L4+跨层一致性校验；每步用纯文本询问是否继续（runner rule_prompt 禁用 AskUserQuestion），禁止一次输出四层。
- **理由**：落点选 claude_data/skills 是平台既有「master 模板→Agent 工作目录拷贝」机制的自然延伸，零新机制；草稿 Skill 对齐 M3.1 Schema 消除「Skill 期望字段 vs 工具校验字段」漂移；字段契约内嵌降低 AI 跑偏（M3.2 风险#3「Skill Prompt 质量」的直接缓解）。可校验性：用文件级测试（存在性/frontmatter/工具引用/scan_skills 发现）覆盖交付物，不依赖真实 Claude 会话。

## 决策 #32：M3.4.1 WF chip 触发 = 斜杠命令 + 意图；项目会话由 Topbar selectedProject 驱动新建（M3.4.1 / §4 §5.2）

- **背景**：M3.4.1 要求对话底部加 5 个工作流 chip（生成假设地图/生成拜访前方案/整理拜访纪要/验证假设/营销地图）。需抉择：① chip 如何可靠触发「特定」Skill（runner 只给模型 Skill 工具 + 元数据，无「强制某 Skill」入参）；② 项目会话如何创建（5 个 Skill 绑定在项目 Agent，普通会话无这些 Skill，chip 必须落在项目会话）；③ 是否为本任务新建项目会话 UI 入口。
- **选择**：
  - **触发 = `/${command} ${hint}`**：`command` = Skill 名（如 consultant-hypothesis-map），`hint` = 一句中文意图。复用既有命令菜单的斜杠命令机制（`scan_agent_commands` 已把 `workdir/skills/*` 暴露为 `/command`，前端 commandMenu 早已这么发）——零新机制。slash 给模型明确的 Skill 调用信号，hint 给自然语言意图作双重保险：即便 `/skill-name` 解析不完美，模型据 hint 仍会调对应 Skill 工具。5 chip 映射 5 个产出型 Skill（WF07/WF06/WF09/WF10/WF12；WF02 文件归档/WF03 缺口为辅助/非结构化，不入 chip）。
  - **项目会话 = Topbar selectedProject 驱动**：把 M1.3.9 的 `selectedProject`（ProjectSelector，已支持「未选项目」清空）传入 ChatWorkspace；`sendMessage` 新建会话时若 `selectedProject` 非空→`createSession({ project_id })`（不传 agent_id，后端 M3.4.2 自动加载项目 Agent），否则沿用用户挑选的 Agent。**不为本任务新建项目会话入口**，复用既有 ProjectSelector。
  - **chip 显隐 = 项目上下文**：仅当 `activeProjectId != null` 显示（空状态取 selectedProject.id / 已进入会话取 currentSession.project_id）。普通会话与「选了项目但停在旧的非项目会话」均不显示——旧会话非项目会话，无项目 Skill，需新建会话才生效（空状态横幅已提示绑定）。streaming 中 chip 禁用。
- **理由**：斜杠命令是平台既有「Skill 作为命令」的既有路径，chip 直接复用，避免造新触发协议；slash+hint 双重信号兼顾「可靠触发」与「可读意图」；项目会话由既有 ProjectSelector 驱动，零新 UI 入口，与 M3.4.2 后端「createSession 校验成员 + 自动加载项目 Agent」天然衔接。纯前端任务，无后端改动（后端 SessionOut/CreateSessionRequest 早在 M3.4.2 支持 project_id），故以 tsc + vite build 验证（同 M3.1.4 前端口径），不跑 pytest 回归。

## 决策 #33：M3.3 三个 Plugin = 版本化模板目录 + app 层执行模块（M3.3.1/2/3 / §4.3 §7.8 §7.9 §7.10 §8.2）

- **背景**：M3.3 要求实施 3 个 Plugin（consultant-router 意图路由 Hook + IntentRoutingLog / consultant-search 三个 MCP 工具 / consultant-defense 道层注入 + PostOutputFilter）。规格描述为「打包目录含 Hook 脚本 / MCP 配置」。需抉择：做成真正的 Claude SDK 插件（shell/node hook 脚本 + 子进程 MCP）还是延续平台既有的「app 层逻辑 + seed 模板」模式。
- **选择**：**版本化模板目录 + app 层执行模块**（延续决策 #29/#31/#32）。每个 Plugin 双层落地：
  - **绑定/发现/资产层** = `app/plugins_seed/<name>/`（`.claude-plugin/plugin.json` + Prompt/规则资产，如 intent_classifier.md / dao_layer.md / never_visible.json）。`seed_default_plugins()`（镜像 `seed_default_skills`）启动时非破坏性播种到 `claude_data/plugins/`，使 `scan_plugins` 发现、`init_agent_workdir` 拷贝、SDK 以 `{"type":"local","path":...}` 加载。`DEFAULT_PROJECT_PLUGINS`（M1.3.7 早已定义）绑定到项目 Agent。
  - **执行层** = app 层 Python 模块，接入 streaming/runner：router.py（意图路由 + IntentRoutingLog 落库）/ search_tools.py（三进程内 MCP 工具）/ defense.py（道层加载 + 指纹过滤）。
- **为何不做 shell hook 脚本插件**：① SDK 插件 hook 是可执行脚本（shell/node），Windows 跨平台脆弱、无法干净访问 app 的 DB/ORM/LLM 客户端/Material；② 意图路由需 DB 写日志 + LLM 分类 + 提示改写，搜索需落库归档，防御需读资产 + 确定性过滤——这些都不适合塞进无状态 shell 脚本；③ 与决策 #29（草稿工具选进程内 MCP 而非 PreToolUse hook，因 hook 不能合成结果）同一理由：真实逻辑放 app 层才可测、可维护。模板目录满足「Plugin 目录」交付物 + 绑定/发现机制，app 层满足可测的真实行为。
- **M3.3.1 三级路由**：路径 A（斜杠/chip 命中已知 Skill）→ chip 直达跳过识别；路径 B（NL）→ LLM 分类（DeepSeek flash，≥0.7 路由）→ 关键词兜底（命中唯一类路由）→ chat 兜底（多类 needs_confirmation）。路由到 Skill 改写为 `/<skill> <原提示>`，**复用 M3.4.1 斜杠命令机制**（零新触发协议）。LLM 未配置/失败 → 关键词兜底；路由异常只记日志不阻断。IntentRoutingLog 每次必入（三级全过程字段），session_id 沿用 usage_events plain String（避免 UUID 字符串主键 FK 迁移复杂度）。
- **M3.3.2 三工具 = 进程内 MCP**：`build_search_tool_server(ctx)` 与 M3.1 草稿工具同模式（决策#29），非子进程 MCP。外部 HTTP 隔离在 `_http_*` seam 供单测 monkeypatch；search_web/company_registry 未配置返回兜底（§4.3「后续对接」），fetch_webpage 直接抓取。归档 `<workspace>/公开信息/<slug>.md` 同名去重（§7.8）。
- **M3.3.3 两防线门控**：均按 `defense_plugin_active(agent)`（仅项目 Agent）。防线1 runner 在 system_prompt.append 前置 dao_layer（§7.10 注入不可 RAG）；防线2 streaming.on_message 对 assistant_text 应用 never_visible 确定性过滤（思维链不过滤 §8.2）。资产单一真源 = plugins_seed/rules/。
- **理由**：双层落地是平台既有模式的自然延伸（M3.1 进程内 MCP + M3.2 seed 模板），零新机制、全链路可单测（不依赖真实 Claude 会话/网络）。可校验性：router 35 / search 24 / defense 15 测试覆盖纯逻辑 + handler + seed/scan + streaming 接线（mock stream_chat）；全量 648 passed、fail 集未扩大。两 Plugin 共享 runner/streaming/conftest 集成点且单提交需自洽，故 M3.3.2+M3.3.3 合并为一个提交（M3.3.1 因改动隔离单独提交）。

## 决策 #34：M3.4.3 Chat 调整循环 — 草稿版本化(previous_data/revision) + update_draft_id + 对话流 brief 注入 + 前端 diff（M3.4.3 / §1.6 §2.2 §7.1.7 §7.2）

- **背景**：§7.2「Chat 调整机制」要求所有 WF 产出在采纳前支持自然语言调整循环：产出 → 用户描述修改 → AI 基于原文+指令重新生成 → 展示 diff → 确认后更新候选 → 再问采纳 → 直到采纳/驳回。现状差距：① business_map `upsert_draft` 已覆盖式（天然支持重新生成），但无版本历史，覆盖即丢旧内容 → 无法 diff；② stakeholder/visit 每次 `create` 新建草稿行，"调整"会变新增第二张草稿而非更新；③ AI 缺少"当前待采纳草稿原文"的可靠上下文，难以"基于原文重新生成"。
- **选择**：四层联动（数据/工具/对话流/前端），均延续既有架构、零新机制：
  1. **数据层**：`BusinessMapDraft` 加 `previous_data: JSONB`（上一版 draft_data）+ `revision: int`（首次=1，更新+1）。`upsert_draft` 覆盖前把旧 `draft_data` 存入 `previous_data`、`revision+=1`。业务地图"整图一个草稿单元"（§7.1.7）天然适配"基于原文覆盖更新"。迁移补 `ALTER TABLE business_map_drafts ADD COLUMN`（dev 库已有表）。
  2. **工具层**：`_draft_pending_event` 增 `is_update/revision/previous`。business_map handler 从 upsert 返回的 `previous_data/revision` 带入事件（持久化版）；stakeholder/visit handler 增**可选** `update_draft_id` 参数 → 命中则校验存在/属本项目/仍 draft 态 → 抓字段快照（`_snapshot_card/_snapshot_visit`）作 previous → 复用 `update_card/update_visit`（partial、不强制 review_status，保持 draft）覆盖更新；不命中则 create（M3.1 行为不变）。三类 `draft_pending` 都能 diff。
  3. **对话流**：`streaming._build_draft_brief` 读项目当前 active 业务地图草稿（按 level 概要节点名）+ draft 态角色卡/拜访记录，生成摘要文本；`runner.stream_chat` 加 `draft_brief` 参数注入 system_prompt.append（`dao_layer, agent_prompt, draft_brief, rule_prompt`），使 AI"基于原文+用户指令重新生成并覆盖更新"而非新建重复草稿，并提示"角色卡/拜访需带 update_draft_id"。
  4. **前端**：`DraftPart` 加 `isUpdate/revision/previous`；卡片渲染——更新时徽标由"待采纳"变为"第 N 版·已更新"，新增 diff 对比块（business_map 节点增删 / stakeholder/visit 字段"旧→新"高亮），并在按钮区加调整提示（"在下方输入框用自然语言描述修改，AI 会更新草稿再请你确认"）。business_map preview 补节点摘要 `objects:[{level,name}]` 供 diff 对照。
- **为何 previous 只存一版**：§7.2「展示 diff」即对比"上一版 vs 当前版"，单 `previous_data` 足够；独立多版历史表是过度设计（business_map 采纳时已有 `BusinessMapVersion` 全量快照承载正式版本回溯，§7.4）。stakeholder/visit 是实体行草稿，previous 不落实体表（避免侵入 StakeholderCard/VisitRecord 加列），只在事件里携带供前端即时 diff——`draft_pending` 经 `run_state` 入栈（M3.4.2），断开重连仍可回放拿到 previous。
- **为何 update_draft_id 可选**：保留 M3.1 create 行为完全不变（向后兼容，既有测试零改动）；AI 据 brief 注入的提示在"更新"语义时带 id，"首次生成"不带。update_draft_id 指向不存在/非本项目/非 draft 态 → `is_error` 回写 Claude 自我修正，不落库不推送（与既有校验一致）。
- **理由**：四层均在既有「草稿工具进程内 MCP（#29）+ run_state 回放（#30）+ 整图草稿单元（#18）」地基上扩展，零新表（仅加列）、零新协议。business_map 是 diff 主战场（整图草稿单元语义最清晰、规格 §7.1.7 明确"增量更新草稿"）；stakeholder/visit 的 previous 走事件级快照避免侵入实体表。可校验性：test_draft_tools +5（revision/diff/update_draft_id 各分支含 wrong-state/not-found）/ test_sessions_project_binding +3（brief 无草稿/有草稿/stream 传入）聚焦全过，test_business_map_api/test_reviews_api 既有 22 测零回归；前端 tsc -b + vite build（71 模块 0 错）。改动为纯增字段+新增分支，create/既有路径行为不变 → fail 集未扩大。

## 决策 #35：M4.1 业务地图页面 — 复用全局项目选择器 + 子任务打包（M4.1.1-5 / §2.3 §5.2）

- **背景**：进入 Phase 4 前端页面。M4.1 要求「替换 BusinessMapPage 原型」，原型自带 MOCK 项目选择器 + MOCK 数据。需抉择：① 项目选择器放页内还是复用全局；② 10 个子任务（M4.1.1 骨架→M4.1.10 证据）如何切分提交。
- **选择 A — 复用全局 Topbar ProjectSelector**：BusinessMapPage 接收 `project: Project | null` prop（App.tsx 传入 `selectedProject`），不在页内重复选择器。理由：M1.3.9/M4.4.1 已确立「Topbar ProjectSelector 驱动全局 selectedProject，业务地图/营销地图/拜访记录/对话共享」的模式（决策#32 同源）；页内再放一个选择器会造成双真源、状态不同步。页内仅显示项目上下文（名称+客户+my_role）只读栏 + 统计。
- **选择 B — 数据契约确认**：顶层对象字段 snake_case（`map_type`/`verification_status`/`parent_id`/`linked_hypothesis_id`，对齐后端 BusinessMapObjectOut），payload 内部 camelCase（`coreActivities`/`fiveDimHealth`/`domainType`，§5.2 规格 + test_business_map_api 的 `payload:{"coreActivities":...}` + 草稿 `draft_data.objects[].payload` 双重确认）。types 用 BusinessMapPayload 单一接口覆盖 L1-L4 全部字段（可选 + 索引签名），前端按 `node.level` 渲染对应字段，不为每层建独立类型（payload 本是自由 JSONB，schema 层都不约束）。
- **选择 C — 子任务打包 M4.1.1-5 一个提交**：原型 1194 行一次性重写为真实数据，骨架（M4.1.1）的「主内容」即 L1-L4 树（M4.1.2），假设/现状（M4.1.3/4）只是同一棵树的 map_type 过滤，偏差池（M4.1.5）是推翻节点的纯派生——四者共用一次 list objects 调用 + 一套树渲染，强拆会让骨架提交只剩空占位、随即被下一提交覆盖，浪费且不可独立回滚验证。故打包为「骨架+树+假设/现状/偏差」一个连贯提交；前置分析（M4.1.6，需 GET+编辑表单）、五维健康（M4.1.7，需评分表+重算+覆盖）、节点 CRUD（M4.1.8）、版本管理（M4.1.9）、关联证据（M4.1.10）各为独立关注点，分别独立提交。前置分析/五维健康本次以 PlaceholderView（含任务编号）占位，不污染数据流。
- **为何一次性把 client 全套 API 都接上**：M2.1 后端早已就绪（objects/pre-analysis/versions/health 全套），本次顺手接全，后续 M4.1.6-10 直接复用、无需再改 client.ts，减少跨提交冲突。
- **理由**：复用全局选择器避免双真源（与 #32 一致）；snake_case/camelCase 分层是后端 schema 既定事实，前端类型如实映射；子任务打包遵循「一个连贯可独立验证的功能单元一个提交」，骨架不可无树独立。可校验性：纯前端、无后端改动 → tsc -b 0 错 + vite build（71 模块 1.25s）；fail 集不涉及前端，必然未扩大。

## 决策 #36：M4.2 营销地图页面 — 复用 M4.1 模式 + 数据契约 + 子任务切分（M4.2.1-10 / §2.4 §5.2）

- **背景**：M4.2「替换 MarketingMapPage 原型」（原型 1022 行 MOCK 数据）。后端 M2.2 已就绪：`/api/projects/{id}/{stakeholder-cards,stakeholder-relations[+/graph],talk-scripts,knowledge-base}/*` 全套。StakeholderCard 分层 JSONB（objectiveLayer/subjectiveLayer/behaviors/stanceChangeLog），综合评分/等级由后端 `service._compute_subjective` 按 §5.2 公式（engagement×0.3+influence×0.4+support×0.3）算回写。
- **选择 A — 复用全局 Topbar ProjectSelector**：MarketingMapPage 接收 `project: Project | null` prop（App.tsx `selectedProject` 传入），与 #35/#32 同源；页内只读项目上下文栏 + 统计。App.tsx 由 `<MarketingMapPage />` 改为 `<MarketingMapPage project={selectedProject} />`。
- **选择 B — 数据契约**：顶层字段 snake_case（`role_type`/`reports_to`/`decision_power`/`review_status`/`from_card_id`，对齐后端 *Out），分层 JSONB 内部 camelCase（`objectiveLayer.education`/`subjectiveLayer.compositeScore`/`behaviors[].suggestedAction`/`stanceChangeLog[].from`，§5.2 规格 + service._compute_subjective 写回 compositeScore/gradeLevel 双重确认）。前端 types 用 StakeholderObjectiveLayer/SubjectiveLayer/BehaviorEntry/StanceChangeEntry 精确建模（含索引签名兼容宽松数据），不退化为 `any`。
- **选择 C — 视图拓扑 = 8 顶 Tab**：原型 6 视图（组织架构/决策链/立场矩阵/采购时间线/角色卡/知识库）基础上，M4.2.8 加「关系网络」(ReactFlow)、M4.2.10 加「话术库」各为独立顶 Tab；角色 CRUD（M4.2.9）作为编辑弹窗挂在角色卡视图 + 关系网络视图。8 Tab 用图标+小字号水平排布可容纳。
- **选择 D — 子任务切分**：M4.2.1 骨架 = 数据加载层（cards+scripts 父级一次拉取，relations/kb 各视图自取，与 #35 同）+ 项目上下文栏 + 统计栏 + 8 Tab 切换 + 角色卡视图种子（左列表+右只读详情，作为数据主干，使骨架提交即可用）；其余 7 视图以含任务编号的 PlaceholderView 占位。M4.2.2-5/7/8/10 各替换一个占位为真实视图，M4.2.6 把角色卡种子升级为 5 子 Tab + 右侧关联面板，M4.2.9 加 CRUD 弹窗。每个子任务独立提交保持可回滚。
- **选择 E — ReactFlow（非 D3）**：§5.2 明示「前端使用 ReactFlow/D3」；选 ReactFlow（v11 `reactflow`，`import 'reactflow/dist/style.css'`），声明式 nodes/edges + 内置拖拽/缩放，4 种 relation_type 用不同边样式区分，无需手写力导向。已 `npm i reactflow`。
- **理由**：与 #35 完全一致的工程范式（全局选择器 / snake_case+camelCase / 子任务独立提交 / 纯前端 tsc+build 校验）；ReactFlow 是 §5.2 钦定二选一中的声明式更优解。可校验性：无后端改动 → tsc -b + vite build；fail 集不涉及前端必然未扩大。





