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

## 决策 #37：M4.2.5 采购时间线 — 后端项目级单例持久化（非 localStorage）

- **背景**：M4.2.5「采购流程时间线视图 | 五阶段通用模板（需求识别→方案评估→供应商筛选→商务谈判→合同签署）| 用户手动填写」。后端 M2.2 四表（StakeholderCard/Relation/TalkScript/KnowledgeBase）**无采购时间线表**；规格明示数据源=「用户手动填写」。抉择：① 持久化在哪——后端新表 vs 浏览器 localStorage vs 前端纯内存；② 数据形态——5 行明细表 vs 单行 JSONB。
- **选择 A — 后端新建项目级单例表 `ProcurementTimeline`（非 localStorage）**：项目是 team 共享（visibility=team，成员全透明），「手动填写」的进度必须跨会话/跨成员持久，localStorage 仅浏览器本地、换人换设备即丢，与项目级数据语义冲突。故新建后端表，走 `require_project_member` 隔离，与 StakeholderCard 等同级。表结构仿 `PreAnalysis`（业务地图的项目级单例先例）：`UniqueConstraint(project_id)` 一项目一行 + `created_by` + 时间戳。
- **选择 B — 单行 JSONB `stages` 数组（非 5 行明细表）**：五阶段是**固定通用模板**（key/name 不可变，用户只填 status/起止日期/说明/关键角色），不是可任意增删的实体集合。单行 JSONB 整体读写最贴合「模板填充」语义；5 行明细表会引入 per-stage CRUD + 排序 + 模板初始化的过度设计。stages 内部 camelCase（`startDate`/`endDate`/`ownerCardId`，§5.2 JSONB 契约，与 StakeholderCard 分层一致），前端 types 用 `ProcurementStage`/`ProcurementStageStatus`/`ProcurementStageKey` 精确建模。
- **选择 C — upsert 整体替换（非逐阶段 PATCH）+ 前端显式保存**：GET 返回 null 时前端用 `DEFAULT_PROCUREMENT_STAGES` 默认模板渲染（与后端 `PROCUREMENT_STAGE_TEMPLATE` 对齐）；编辑全部在前端本地 state 完成，PUT 时整体替换 stages（前端管完整 5 阶段含 name 默认值，后端只存不解释）。用显式「保存时间线」按钮 + 「● 有未保存更改」脏标记，不做自动保存（避免 debounce 惊扰用户、与业务地图健康度等既有「动作触发 PUT」模式一致）。
- **为何后端默认模板也兜底**：`_default_procurement_stages()` 在 service `_proc_to_out` 与前端 `DEFAULT_PROCUREMENT_STAGES` 双端各一份——后端兜底防止脏数据（stages 为 null/空）时前端拿到空数组；前端兜底 + 与默认模板 merge 补齐缺失阶段/字段，保证渲染永远 5 阶段。两份模板是「契约常量」镜像，非重复逻辑。
- **理由**：team 共享项目数据须服务端持久（否 #35/#36 全局选择器 + require_project_member 的隔离体系就失去意义）；固定五阶段用 JSONB 单例最简；upsert 整体替换 + 显式保存贴合「手动填写模板」心智且改动可控。可校验性：23 测试零回归（test_marketing_map_api 12 + test_business_map_api 11，新表由 init_db `create_all` 在 test 库自动建）+ 真机 GET(null)→PUT(建 id=1)→GET(回读) 全链路通；前端 tsc -b + vite build 过。fail 集仅新增 procurement 路由分支，既有 stakeholder/relation/script/kb 路径行为不变 → 未扩大。

## 决策 #38：M4.2.6 角色卡牌视图 — 5 子 Tab 全字段 + 三栏关联面板（§5.2）

- **背景**：M4.2.6 把 M4.2.1 的角色卡「只读种子」（左列表 + 右单栏平铺部分字段）升级为「左侧角色列表 + 中间 5 子 Tab 详情卡（客观/主观/行为/态度历史/话术）+ 右侧关联面板」。开发计划明示详情字段须覆盖 §5.2 全量，且主观层含 M3.2.8 补的 `confidence`。抉择：① 5 子 Tab 怎么切；② 右侧「关联 L3 场景/拜访记录/话术」三项各用什么数据源——尤其 L3 场景。
- **选择 A — 5 子 Tab = §5.2 四大板块拆 + 话术独立 Tab**：客观信息（objectiveLayer 7 字段）/ 主观分析（subjectiveLayer 全含 confidence + 三维评分综合）/ 行为分析（behaviors[] observation-interpretation-suggestedAction 三行卡）/ 态度历史（stance_change_log[] 时间线 from→to）/ 话术（TalkScript 按 stakeholder_card_id 过滤）。这正好对应 §5.2「角色卡完整字段」的四大子节 + 「话术库（角色卡内子Tab）」。子 Tab 栏 sticky 吸顶，数组类 Tab 带数量角标（行为 N / 态度 N / 话术 N），客观/主观不带（字段固定无计数意义）。
- **选择 B — 全字段覆盖，confidence 等可选字段条件渲染**：客观 7 字段全列（education/previousCompanies/personality/communicationPreference/relationships/historyWithUs/historyWithCompetitor，缺则 Field 占位「未填写」+ 顶部「已填 X/7」）；主观层 stance + confidence + gradeLevel + compositeScore 作立场徽标行，其余 6 文本字段（explicitKPI/personalMotivation/attitudeToUs/attitudeToCompetitor/coreConcerns/leverage）作 Field，coreConcerns/leverage 高亮（关键阻力/可改变因素）。confidence 在历史卡（pre-M3.2.8）可能为 null → `sl.confidence && <Tag>` 条件渲染，不报错不占位（字段与 Skill 契约已由 M3.2.8 落定，新卡会有值）。
- **选择 C — 右侧关联面板三项，L3 场景诚实空态**：① **关联拜访记录** = `listVisitRecords(projectId, {card_id})`（card_id 过滤 related_card_ids/participants_client，M2.3 已支持），按日期倒序最多 6 条（日期/类型 Tag/summary 两行截断），超 6 提示去拜访记录页；② **关联话术** = cardScripts 数量 + 「查看 N 条 →」跳话术子 Tab；③ **关联 L3 场景** = 诚实 roadmap 空态。**为何 L3 不造假数据**：StakeholderCard 与业务地图 L3 节点在当前数据模型**无 FK**（StakeholderRelation 是卡↔卡，VisitRecord 是卡↔拜访，均不触达 L3）。规格「关联 L3 场景」的真正语义是「证据→角色→场景」关联链，须待 M4.3 拜访记录打通后才有数据基础。故渲染明确说明「待 M4.3 拜访记录打通后建立」，而非用 TalkScript.scenario 之类近似字段冒充 L3 场景（scenario 是初次拜访/方案汇报等话术场景，非业务地图 L3 节点，混用会误导）。
- **选择 D — 话术子 Tab 分「定制 + 同类型模板」两组**：§5.2 明示「选中角色后展示其关联话术 + 同类型角色的通用话术模板」。故 cardScripts（stakeholder_card_id === 本卡）+ templateScripts（stakeholder_card_id == null && role_type === 本卡 role_type，即跨客户通用模板）分组渲染，模板用虚线边区分。复用父级已拉取的 scripts（M4.2.1 一次 listTalkScripts），不额外发请求。
- **为何 visit 单独按卡拉取而非父级一次拉全**：拜访记录是项目级大列表（可能数十条），且只在选中某卡时需要该卡子集。父级 MarketingMapPage 已拉 cards+scripts（角色卡/话术是营销地图核心、多视图共享）；拜访记录是 M4.3 拜访页的主场，营销地图只在角色卡右侧面板需要「本卡关联」子集 → 在 CardsView 内 useEffect[current.id] 按 card_id 拉取最经济，切换角色时 cancelled flag 防竞态。
- **理由**：5 子 Tab 严格对齐 §5.2 四大子节 + 话术子 Tab 规格全字段；confidence 条件渲染兼容历史卡 null；右侧三项中拜访/话术用真实后端数据（M2.3/M2.2 已就绪），L3 诚实空态避免造假。与 #35/#36/#37 一致的工程范式（全局选择器 / snake_case+camelCase 分层 / 子任务独立提交 / 纯前端 tsc+build 校验）。可校验性：真机 GET stakeholder-cards（卡 id=1 客观全 7 字段 + 主观全字段 + 2 behaviors observation/interpretation/suggestedAction）+ visit-records?card_id=1（HTTP 200 [] 空态）+ talk-scripts（HTTP 200 [] 空态）全链路通；tsc -b 0 错 + vite build 72 模块过。纯前端无后端改动 → fail 集不涉及前端必然未扩大。

## 决策 #39：M4.2.7 知识库视图 — 三板块 CRUD + Markdown 富文本，不臆造附录种子（§2.4 §5.2）

- **背景**：M4.2.7「知识库视图 | 三板块（角色识别/行为速查/入职指南），支持丰富格式」。后端 KnowledgeBase（M2.2）= 项目级（project_id + category[role_recognition/behavior_quick_ref/onboarding_guide] + title + content[Text]），全套 CRUD 已就绪，**无种子逻辑**，dev 库为空。规格称内容「跨客户通用 / 团队共享资产 / 来源于《营销地图设计文档V2.0》附录」。抉择：① 标准参考内容怎么来——前端臆造种子 vs 后端种子 vs 团队手动；② 丰富格式用什么渲染。
- **选择 A — 完整 CRUD + Markdown 富文本，不臆造附录种子**：KnowledgeBaseView 三分类可折叠 Card（角色识别速查/行为分析速查/新人培养流程），每分类列该 category 的条目（title + content 富文本），条目级编辑/删除，分类级「+ 新增」。编辑走 KBEntryEditor 弹窗（标题 input + 内容 textarea，**编辑/预览切换**），保存调 create/update。**为何不臆造种子**：规格明示内容来源于设计文档附录（.docx），而该附录**未解析入库**；角色识别 6 维度×5 类、行为速查 8 条+ 的具体内容只有附录里有，凭空撰写会是缺乏依据的杜撰（违反「不造假数据」原则，同 #38 L3 诚实空态）。故 M4.2.7 只交付承载载体（CRUD 视图），标准附录内容由团队手动沉淀或**后续后端种子任务**（仿 skills/plugins_seed 解析附录 md 入库）批量导入——决策记录此为后续工作。
- **选择 B — 复用 MarkdownView 渲染富文本（非自造渲染器）**：「支持丰富格式」用既存 `components/workspace/MarkdownView`（marked 引擎，breaks:true，支持标题/列表/粗体/表格/代码）。basePath 省略时图片重写为 no-op，工作区无关内容正常渲染。`.md-content` CSS 全局已加载（WorkspacePreview 同源）。编辑器提供「✎ 编辑 / 👁 预览」切换，让用户即时看到 Markdown 渲染效果。**安全姿态**：marked 不做 HTML sanitize，但内容为项目成员（已认证内部用户）创作，与 WorkspacePreview 对工作区文件的危险等级一致，沿用既有 posture 不新增风险面。
- **选择 C — 空态给规格化引导（非泛泛「暂无数据」）**：每分类空态显示「暂无内容」+ 该分类应含内容的规格提示（角色识别：为五类角色各建一条；行为速查：8 条以上；新人培养：四阶段各建一条，理论学习 1 周/模拟演练 2 天/跟岗实践 2 周/独立拜访）。提示文案直接来自 §2.4 规格，引导团队按方法论结构沉淀，弥补无种子的初始空白。
- **为何 KnowledgeBase 是项目级而非全局共享**：规格说「跨客户通用」，但 M2.2 数据模型是 project_id 作用域（每项目独立 KB）。这是 M2.2 既定事实（决策#24），M4.2.7 前端如实映射——按项目渲染该项目 KB。真正的「跨客户通用共享」需后端改造（全局 KB 表 + 项目引用），超出本前端视图任务范围，记录为后续考量。
- **理由**：CRUD + Markdown 是知识库的完整功能闭环（团队可即时沉淀方法论经验）；不臆造附录种子守住「不造假」底线（同 #38）；复用 MarkdownView 零新依赖；空态规格化引导对接方法论结构。与 #35-#38 一致的工程范式（全局选择器 / 子任务独立提交 / 纯前端 tsc+build）。可校验性：真机 KB CRUD 全链路（create HTTP 201 id=1 → update HTTP 200 title→v2 → list 回读 → delete HTTP 204 → list count=0）+ tsc -b 0 错 + vite build 过。（curl 中文+换行 body 在 Windows Git Bash 编码失败，纯 shell 测试假象，前端 fetch 用 UTF-8 不受影响，已用 ASCII body 验证全链路。）纯前端无后端改动 → fail 集不涉及前端必然未扩大。

## 决策 #40：M4.2.8 角色关系网络图 — ReactFlow 视图（圆形布局 + 4 类边样式），关系 CRUD 留 M4.2.9（§5.2）

- **背景**：M4.2.8「角色关系网络图 | 节点=角色卡，边=关系（4 种类型不同颜色/线型），可交互 | 可用 D3/ReactFlow」。后端 M2.2 已就绪 `GET /api/projects/{id}/stakeholder-relations/graph`（nodes:[{id,name,role_type,department}] + edges:[{id,source,target,relation_type,description}]）+ createStakeholderRelation/deleteStakeholderRelation。ReactFlow v11 已 npm i（决策#36 预装）。抉择：① ReactFlow vs D3；② 节点布局（graph 端点不返坐标）；③ 关系 CRUD 是否纳入本任务。
- **选择 A — ReactFlow（非 D3）+ 圆形自动布局**：§5.2「前端使用 ReactFlow/D3」二选一，ReactFlow v11 声明式 nodes/edges + 内置拖拽/缩放/小地图/控件，4 类 relation_type 用 edge.style（stroke 颜色 + strokeDasharray 虚实）+ markerEnd 箭头区分，远省于 D3 手写力导向。**graph 端点不返节点坐标** → 前端圆形自动布局（N 节点均匀分布圆周，半径随 N 自适应 150-300px），用户可拖拽节点重排（ReactFlow 内置交互）。fitView 自适应视口。
- **选择 B — 关系 CRUD 留 M4.2.9，本任务纯视图**：开发计划明示 M4.2.9 =「角色 CRUD **+ 关系编辑**」，故关系增删属 M4.2.9 范畴。M4.2.8 只做交互式渲染：节点（自定义 RelationNode 头像+姓名+部门，边框色=角色类型色）+ 4 类边样式 + **onNodeClick → onJump(卡id) 跳角色卡详情**（与组织架构/决策链/立场矩阵视图一致的跳转模式）+ 图例（SVG 线段示意 4 类颜色/线型/箭头）+ MiniMap（节点色=角色类型）。无关系时渲染孤立节点 + 顶部「暂无关系，M4.2.9 上线后可手动添加」提示，不造假边。
- **选择 C — nodeTypes 模块级常量 + onNodeClick（非 data 内函数）**：ReactFlow v11 要求 nodeTypes 引用稳定（否则重渲染循环）→ `RELATION_NODE_TYPES` 定义为模块级常量。节点点击跳转**不**把 onJump 塞进 node.data（会让 nodes 数组随父级 inline onJump 变化失去 useMemo 稳定性），而用 ReactFlow 的 `onNodeClick={(_,node)=>onJump(Number(node.id))}` 回调——node.id 即卡 id（String 化），干净避开「函数进 data」反模式。
- **选择 D — 4 类关系语义化样式**：reports_to 汇报=实线 accent / influences 影响=实线 info / collaborates 协作=实线 success / opposes 对立=**虚线 danger**（对立用虚线+红强化负向语义）。三类正向用不同色相区分，对立用线型+红双区分。RELATION_META 单表驱动样式 + 图例 + 边 label（中文），单一真源。
- **为何数字 id 全 String 化**：graph 端点 nodes/edges 的 id/source/target 是 number，ReactFlow 要求 string。node.data 保留原始 number cardId 供 onJump，ReactFlow 内部 id/source/target 用 String()——onNodeClick 取 node.id 再 Number() 还原跳转，双向一致。
- **理由**：ReactFlow 是 §5.2 钦定二选一的声明式更优解（决策#36 已预装）；关系 CRUD 归 M4.2.9 遵循计划拆分使本任务单一关注点（渲染）；onNodeClick 避开函数进 data 的反模式。与 #35-#39 一致的工程范式。可校验性：真机 graph 端点 seed 测试（建卡 id=3 + 关系 3→1 reports_to）→ GET graph 返回 2 nodes/1 edge 结构正确 → **测后清理恢复 dev 库**（删关系 204 + 删卡 204，回到 1 节点/0 边/1 卡原状）；tsc -b 0 错 + vite build 过（CSS 5.44→12.76kB / JS 574→728kB 为 reactflow 注入，正常）。纯前端无后端改动 → fail 集不涉及前端必然未扩大。

## 决策 #41：M4.2.9 角色 CRUD + 关系编辑 — 全字段编辑器 + 选中边删除（§2.4 §5.2）

- **背景**：M4.2.9「角色 CRUD | 手动新增/编辑/删除角色卡 + 关系编辑」。后端 create/update/delete stakeholder-cards + create/delete stakeholder-relations 全套就绪（M2.2）；createStakeholderCard 的 review_status **默认 reviewed**（schema Field("reviewed")，手动建卡直接进正式库，§2.4 line 335）；compositeScore/gradeLevel 由后端按 §5.2 公式算回写（不收集）。抉择：① 编辑器覆盖多少字段；② 关系编辑入口放哪；③ M4.2.6 遗留的 hooks 顺序隐患（删除最后一张卡时 useEffect 在早期 return 之后 → hooks 数量变化崩溃）。
- **选择 A — 全字段编辑器 CardEditModal（5 可折叠分区）**：基本信息（姓名*/职位/部门/汇报对象/联系方式/角色类型/决策权）+ 客观层 7 字段 + 主观层（立场/置信度 select + 参与度/影响力/支持度 number 1-10 + 6 文本字段）+ behaviors 数组（observation/interpretation/suggestedAction 增删行）+ stance_change_log 数组（date/from/to/reason 增删行）。基本信息默认展开，其余折叠（避免巨型表单压迫感）。**compositeScore/gradeLevel 不收集**（后端按 §5.2 公式 eng×0.3+inf×0.4+sup×0.3 算回写，编辑器明示此规则）。空值裁剪：objective_layer/subjective_layer 仅含非空键（全空则传 undefined 保 null），数组空则传 null。
- **选择 B — 关系编辑挂 RelationsView（M4.2.8 图视图）**：「添加关系」按钮（disabled when cards<2， RelationEditModal 选 from/to/type/desc，校验 from≠to）+ **onEdgeClick 选中边 → 边加粗高亮 + 顶部「删除选中关系」按钮** + onPaneClick 清除选中。关系编辑天然属于图视图的交互（而非角色卡视图），与 M4.2.8 视图同处一个组件。RelationEditModal 不支持「编辑关系」（关系无业务编辑语义，改类型=删旧建新，故只做增删）。
- **选择 C — 修复 M4.2.6 hooks 顺序隐患**：M4.2.6 的 CardsView 把 `if (cards.length === 0) return` 置于 useState 与 useEffect 之间——无 delete 时不触发，但 M4.2.9 引入删除最后一张卡时 cards 由 >0 变 0，early return 跳过 useEffect → React「Rendered fewer hooks than expected」崩溃。重构为：所有 hooks（含新增 cardEditor state）置于早期 return 之前，`current = selectedCard ?? cards[0] ?? null`，useEffect 以 `current?.id` 为依赖并在内部 guard null。空态也提供「新增角色卡」入口（不止提示）。
- **选择 D — CRUD 入口分布**：CardsView 左列表头「+」按钮 + 空态「新增角色卡」按钮（新建）；CardDetailHeader 右上角 Edit/Trash 图标按钮（编辑/删除当前卡）；删除带 confirm 提示关系/话术受影响。RelationsView 头部「添加关系」+ 选中边删除。onChange/refresh 回调驱动父级重新拉取列表。
- **为何关系无编辑只有增删**：StakeholderRelation 业务语义轻（from/to/type/description），改类型等同于重建关系，UI 上「删旧+建新」比「编辑」更清晰，且后端 update relation 端点本就不在 M2.2 套件（只有 create/delete）。故 RelationEditModal 固定新建语义。
- **理由**：全字段编辑器兑现「手动新增/编辑角色卡」规格（§2.4 line 335），compositeScore 后端算避免前后端重复公式；关系增删补齐 M4.2.8 图视图的编辑能力；hooks 顺序修复消除 M4.2.6 遗留的 delete-last-card 崩溃隐患（测试时删卡回 0 节点不再崩）。与 #35-#40 一致的工程范式。可校验性：真机 ASCII 全 CRUD（建卡 id=4 review_status=reviewed composite=6 grade=倾向我方 / 更新三维全 9→composite=9 grade=Champion 公式正确 / 关系 create id=2 / 删关系 204 / 删卡 204）→ **测后清理恢复 dev 库**（1 节点/0 边）；tsc -b 0 错 + vite build 过。（中文 curl body 仍受 Windows Git Bash 编码限制，前端 fetch UTF-8 不受影响，已用 ASCII 验证全链路含计算字段。）纯前端无后端改动 → fail 集不涉及前端必然未扩大。

## 决策 #42：M4.2.10 话术库管理 — 角色类型分组 + Markdown 编辑 + CRUD（M4.2 收尾，§5.2）

- **背景**：M4.2.10「话术库管理 | 按角色类型×场景组织，支持 Markdown 编辑」。后端 TalkScript（M2.2）= stakeholder_card_id（关联角色，可空）+ role_type + scenario + content（Text）+ source_customer_quote + is_template；create/update/delete/list 全套就绪。规格 §5.2「话术库（角色卡内子Tab）」要求按角色类型×场景组织 + 关联话术 + 同类型通用模板 + 手动增删改。M4.2.6 已在角色卡详情做了「话术子 Tab」（只读展示），M4.2.10 是**项目级独立话术库视图**（8 顶 Tab 之「话术库」），是话术的全局管理入口。
- **选择 A — 分组：通用模板 + 5 角色类型 + 未分类**：is_template 的话术归「🌐 通用模板（跨客户通用）」组；非模板按 role_type 分入五类角色组（经济决策人/技术评估人/终端用户/教练支持者/采购财务）；无 role_type 且非模板归「未分类」。空组不渲染。每条话术卡显示 scenario Tag + 关联角色 Tag（stakeholder_card_id 命中）+ 📎原话标记（source_customer_quote）+ Markdown 内容 + 编辑/删除。「按角色类型×场景组织」= 组内每条带的 scenario Tag 即场景维度，组=角色类型维度，二维清晰。
- **选择 B — 复用 Markdown 编辑器模式（同 M4.2.7 KB）**：TalkScriptEditor 弹窗 = 场景 input + 角色类型 select + 关联角色 select（cards 列表，可空）+ is_template checkbox + content Markdown（编辑/预览切换，复用 MarkdownView）+ source_customer_quote textarea。保存调 create/updateTalkScript。与 KB 编辑器一致的 Markdown 编辑/预览交互，零新组件。
- **选择 C — 消费父级 scripts + onChanged 刷新（非自取）**：MarketingMapPage 父级 refresh() 已拉 cards+scripts（M4.2.1 起 CardsView 复用），TalkScriptsView 接收 `scripts` prop + `onChanged`（父级 refresh）——CRUD 后 onChanged 触发父级重拉，scripts 更新传入。**不自取 listTalkScripts**（避免与 KB/Relations 自取模式不同的双取；scripts 已在父级内存，复用最经济）。TalkScriptEditor 的关联角色 select 用父级 `cards` prop。
- **为何角色卡子 Tab（M4.2.6）与本项目级视图（M4.2.10）并存**：M4.2.6 的话术子 Tab 是「选中某角色卡 → 看其定制话术 + 同类型模板」的**角色视角**（只读，按卡过滤）；M4.2.10 是「全项目话术库 → 按角色类型分组管理」的**全局视角**（CRUD）。两者数据同源（listTalkScripts），视角互补：浏览某角色时看子 Tab，管理全部话术时用顶 Tab。无重复造数据。
- **理由**：分组兑现「角色类型×场景组织」；Markdown 编辑复用 M4.2.7 模式零新依赖；消费父级 scripts 避免双取。**M4.2 营销地图页面 10/10 全部完成**（M4.2.1-10）。与 #35-#41 一致的工程范式。可校验性：真机话术 CRUD（create id=1 scenario=demo role=technical_evaluator template=true / list 回读 / update scenario=demo-v2 / delete 204 / 恢复 0）全链路通；tsc -b 0 错 + vite build 过。（8 顶 Tab 现已全部落地，PlaceholderView 沦为不可达安全网，保留不删避免额外 churn。）纯前端无后端改动 → fail 集不涉及前端必然未扩大。






## 决策 #43：M4.3 拜访记录页面 — 6 子任务渐进拆分 + 展开 Option B + 单一数据源（§2.5）

- **背景**：M4.3「拜访记录页面」（开发计划行 211-220，6 子任务）替换 VisitRecordsPage 原型为真实后端。布局 §2.5 = 拜访记录列表（时间倒序）+ 证据筛选面板。后端 M2.3 全套就绪（/visit-records + /evidence-sources CRUD，派生 evidenceCount/verifiedHypotheses 读取时算）。抉择：① 6 子任务如何切分使每提交可回滚且页面始终可用；② 拜访卡折叠/展开如何分到 M4.3.2 与 M4.3.4；③ 数据加载范围。
- **选择 A — 6 子任务渐进、每提交页面可用**：M4.3.1 骨架（项目 prop + 上下文栏 + 统计 + 列表加载 + 证据概览 + 加载/错误/空态）→ M4.3.2 折叠卡全字段（参与人姓名解析/地点/时长/关联角色卡数）→ M4.3.3 筛选面板（类型/强度/角色 + 结果列表 + 统计，替换概览）→ M4.3.4 展开体（KeyTakeaways/NextSteps/本次证据清单）→ M4.3.5 §7.6 态度联动 → M4.3.6 CRUD。每子任务独立 commit，页面始终可构建可运行。
- **选择 B — 展开 Option B（M4.3.2 放基本信息行，M4.3.4 追加洞察/证据）**：避免「M4.3.2 加展开 toggle 但无内容」的半成品——M4.3.2 折叠头部可点击展开，展开体先放基本信息行（我方/客户/地点/时长），M4.3.4 再往同一展开体追加 KeyTakeaways + NextSteps（MarkdownView）+ 证据清单（EvidenceDetail 组件，M4.3.5 在其上扩展态度联动）。每个展开都是自洽可用的。
- **选择 C — 单一数据源 + 客户参与人姓名解析**：refresh 并行拉 reviewed VisitRecord + reviewed EvidenceSource + reviewed StakeholderCard（cardMap 解析 participants_client 角色 ID→姓名，未知回退 角色#id）。统计栏「涉及角色」= related_card_ids 去重计数；「总证据」= evidences.length（与强度分布自洽）；拜访时间倒序（visit_date 降序，空置底）。与 §2.5「reviewed VisitRecord + 已确认 EvidenceSource 单一数据源」一致。
- **理由**：渐进拆分兑现「每子任务独立提交保持可回滚」的自主授权要求；Option B 避免半成品 toggle；单一数据源对齐 §2.5。可校验性：GET /visit-records?review_status=reviewed 及 /evidence-sources 烟测 200 字段对齐 types；tsc -b 0 错 + vite build 过（6 子任务逐个）。与 #35-#42 一致工程范式。纯前端无后端改动。

## 决策 #44：M4.3.6 拜访/证据 CRUD — 表单字段映射 + §7.6 态度信号录入（§2.5 §7.5 §7.6）

- **背景**：M4.3.6 为 M4.3 补齐手动 CRUD（新增/编辑/删除拜访 + 拜访内证据）。后端 create/update 默认 review_status=reviewed（手动写入直接进正式库，§7.3）。抉择：① 拜访表单 participants_client（角色 ID 列表）与 related_card_ids 关系；② 证据表单是否收集 related_hypothesis_id；③ §7.6 角色态度信号证据的立场变化如何录入。
- **选择 A — 客户参与人多选同步 related_card_ids**：手动录入场景「参与人」与「关联角色卡」高度重合（你见的角色即关联角色），VisitFormModal 单个角色卡 checkbox 多选同时写 participants_client 与 related_card_ids，简化表单避免两套近似多选。我方参与 participants_our 是自由文本（顿号/逗号/换行分割）。
- **选择 B — 证据手动表单省略 related_hypothesis_id**：假设节点关联（§7.5 验证联动）本质是 AI/对话驱动的流程，手动录入证据时让用户从 BusinessMapObject 下拉选假设节点价值低且需额外加载业务地图对象。EvidenceFormModal 只收集 evidence_type/strength/content(必填)/source_role_id（单选角色卡自动带出 source_role_name）。related_hypothesis_id 留 null，AI 流程负责挂接。
- **选择 C — §7.6 角色态度信号条件录入立场变化**：EvidenceFormModal 当 evidence_type==='角色态度信号' 时条件显示「态度变化：从→到」（STANCES=支持/中立/反对/观望 两 select），写 implied_from_stance/implied_to_stance；非态度信号证据不显示。与 EvidenceDetail（M4.3.5）的展示对称——录入侧与展示侧同一字段集。
- **选择 D — 复用既定 Modal/表单样式 + window.confirm 删除**：modalOverlay/modalCard/modalInput/fieldLabel/saveBtn/ghostBtn/iconBtn 对齐 MarketingMapPage（同仓内复制，非共享导出）；删除用 window.confirm（与 M4.2.x 角色卡/话术删除一致约定）；EvidenceDetail 右上角可选 onEdit/onDelete 图标（filter 面板不传则不显示，复用组件不污染筛选结果）。
- **理由**：client 同步 related 简化表单契合手动录入语义；省略 hypothesis 手动挂接聚焦 AI 流程；§7.6 录入与展示对称闭环。可校验性：真机 UTF-8 文件传 body（规避 Git Bash 中文编码）全 CRUD——拜访 CREATE 201→PUT 200→DELETE 204→GET 404；证据 CREATE 201（含立场变化字段反对→中立）→PUT 200→DELETE 204→临时拜访级联删 204；**测后清理 dev 库**（仅剩原始 visit 1，0 证据）。tsc -b 0 错 + vite build 过。

## 决策 #45：M4.4.4 对话页待审核 Banner — 绑定项目 Owner + 自包含刷新 + 静默（§3.4）

- **背景**：M4.4.4「审批提醒 Banner | Deputy 采纳后 Owner 在对话 Banner 收到待审核提醒」。后端 M2.4：GET /pending-reviews（跨模块聚合 pending_review）+ POST /reviews/{type}/{id}/approve|reject（require_project_owner）。抉择：① Banner 绑定哪个项目上下文；② 仅提醒还是可处置；③ 失败如何处理。
- **选择 A — 绑定 selectedProject（Topbar 选择）+ my_role==='owner' 守卫**：Topbar selectedProject 携带 my_role（owner/deputy），是用户当前工作的项目上下文。Banner 仅当 selectedProject.my_role==='owner' 时渲染（Deputy/非成员不渲染——审批是 Owner 权限）。未选项目或非 owner → 不渲染。
- **选择 B — 提醒 + 就地处置（approve/reject）**：Banner 不止提醒——warn 条「本项目 N 项待审核」可展开列出每项（entity_label/name/提交人/时间），逐项「通过/驳回」直接调 approve/review 端点，处置后自刷新（处置完该项移出列表，全处置完 Banner 自动隐藏）。API 已 trivial，就地处置让 Banner 立即可用而非等 M5.2.3 审核通知。
- **选择 C — 自包含 fetch + 静默错误**：PendingReviewBanner 自管 items/loading/acting 状态，useEffect 依 projectId 拉取，approve/reject 后 refresh 自身。**失败静默**（catch 空）——Banner 是辅助提醒，绝不应因它失败阻塞对话主流程（与主对话错误处理隔离）。items.length===0 时 return null（DOM 不留痕）。
- **选择 D — 复用 CSS 变量 + 顶部 Banner 位**：warn-soft 背景（global.css 已定义 light/dark），插在 ChatWorkspace 头部（agent/project Tag 行）与消息流之间，flexShrink:0 不被滚动区吞掉。ChevronDown 旋转表展开态，与拜访卡展开交互一致。
- **理由**：owner 守卫对齐审批权限；就地处置兑现「收到提醒」并提前可用；静默错误保护对话主流程。可校验性：真机全链路——建 pending_review 拜访 → GET /pending-reviews 返回该条（PendingReviewItem 字段 entity_label/name/submitted_by_name 与渲染匹配）→ POST approve 置 reviewed → 复查 pending-reviews 为空 → 删除清理。tsc -b 0 错 + vite build 过。纯前端无后端改动。

## 决策 #46：M4.3.7 证据关联跳转交互 — 一次性跨页聚焦机制 + 可点击标签（§2.5 §7.5，M4.3 闭环）

- **背景**：交接指令把 M4.3.6 定义为「证据 CRUD」（已做，决策#44），但官方开发计划拆解V2.0.md 行 220 的 M4.3.6 实为「证据关联交互 = 证据→点击跳转业务地图节点 / 点击跳转角色卡」。本仓 M4.3.6 已用于 CRUD，故跳转任务顺延为 M4.3.7。缺口：VisitRecordsPage 的 EvidenceDetail 里 `🔗 {related_hypothesis_name}` 与 `{source_role_name}` 是纯展示 span 无跳转。后端无改动（EvidenceSource 含 related_hypothesis_id→BusinessMapObject.id / source_role_id→StakeholderCard.id，两 list 端点已接线）。抉择：① 跨页定位机制怎么搭；② 业务地图如何让目标节点在树中可见；③ 一次性消费防重复触发。
- **选择 A — App.focusTarget 一次性聚焦 + onFocusConsumed 回调（复用 M4.4.5 focusSessionId 范式）**：App 增 `focusTarget: {view:'businessMap',objectId} | {view:'marketingMap',cardId} | null` 状态 + jumpToHypothesis/jumpToCard 回调（setFocusTarget + setView）。BusinessMapPage 收 `focusObjectId`/`onFocusConsumed`，MarketingMapPage 收 `focusCardId`/`onFocusConsumed`，props 按 `focusTarget.view` 匹配派发。目标页 useEffect 命中后调 onFocusConsumed→setFocusTarget(null) 清空，**一次性消费**防重复触发（与 M4.4.5 待采纳徽标跳回对话的 focusSessionId/onFocusSessionConsumed 完全同构，是仓内已验证范式）。数据未加载完（objects/cards 为空）时 return 等待，加载后无论命中与否均消费，避免「空数组提前消费导致 focus 丢失」。
- **选择 B — 业务地图选中+切子视图+展开祖先链**：focus effect 命中后 setSelectedId(obj.id) + 按 obj.map_type 切 subView（current→现状/hypothesis→假设）+ 沿 parent_id 上溯展开 L1/L2 祖先（仅跟踪 parentId 的 while 循环，规避 `let` 重赋值+闭包的 TS 推断怪癖）。右侧详情面板 selected 由 objects.find 派生，即使树未滚动到目标也立即显示——展开祖先链是锦上添花让左侧树也可见。
- **选择 C — 营销地图复用既有 selectedCardId/onJump 模式**：MarketingMapPage 已有 selectedCardId + 各子视图 onJump→setSelectedCardId+setSubView('cards') 模式（决策#40），focus effect 只需 setSelectedCardId(focusCardId)+setSubView('cards')，CardsView 自动选中并展示详情，零新逻辑。
- **选择 D — 标签条件渲染为 button（有 id+回调时）/span（否则）**：EvidenceDetail 的角色/假设标签：当 onJumpToCard 且 source_role_id!=null → 渲染 `<button onClick=onJumpToCard(id)>`，否则保留 span；假设标签同理。抽出 roleTagStyle/hypoTagStyle/jumpTagBtnStyle 静态样式供 button/span 复用，hover 加 underline 作可点击暗示。无 id（AI 未挂接）或无回调时退化为纯展示，组件仍可独立复用（如筛选面板未传回调时不显示按钮）。
- **理由**：复用 M4.4.5 一次性聚焦范式（仓内已验证，非新发明）；业务地图展开祖先是「定位节点」规格的完整实现；条件 button/span 保持组件复用性。**M4.3 拜访记录 7/7 全完成**（M4.3.1-7），Phase 4 彻底闭环。可校验性：tsc -b 0 错 + vite build 过；逻辑自检——点击标签→App setFocusTarget+setView→目标页 mount 加载数据后 effect 选中定位+展开祖先→onFocusConsumed 清空，幂等一次性跨页正确。纯前端无后端改动。

## 决策 #47：M5.5.5 五维健康自动计算 — 三写入路径派生 + manual 覆盖保留（§7.7，Phase 5 起步）

- **背景**：M5.5.5「对话更新地图数据后触发五维健康重新评估」。审计发现 `compute_five_dim_health`（health.py 规则版，按 payload 关键字段完整度映射 1-5 分）+ 手动 recompute/override（M4.1.7）已就绪，但**三条写入路径 create_object / update_object / adopt_draft 都直接落 payload 未触发健康计算**——新对象/采纳对象无 fiveDimHealth，必须手动点「重新计算全部」才有。缺口确认：adopt_draft(line 417) `payload=spec.get("payload")`、create_object(line 137) `payload=payload.payload`、update_object(line 162) `obj.payload=payload.payload` 均未调 compute。抉择：① 哪些路径接入；② update 时如何对待 manual 覆盖；③ 0 完整度节点是否给健康。
- **选择 A — 三写入路径全部自动派生**：create_object（手动新建）+ adopt_draft（对话采纳，plan 明示的「对话更新」场景）创建时对 L1/L2/L3 计算 `compute_five_dim_health` 并 `merge_health_into_payload(source="auto")` 入 payload；L4 等无健康维度的层级原样返回。抽取模块级 helper `_payload_with_auto_health(payload, level)` 供两处复用（DRY）。健康随版本快照落库（_snapshot_reviewed_objects 含 payload），采纳即固化。
- **选择 B — update_object 重算但保留 manual 覆盖**：helper `_merge_updated_payload(prev, new, level)`——上一版 `_healthSource==='manual'` 时把人工评分携带到新 payload（source 保持 manual，不覆盖人工判断）；否则（auto/首次）基于新 payload 重算 auto。这样新建/编辑刷新 auto 评分，而人工覆盖（§7.7 set_node_health）在后续 payload 编辑中持久，除非用户显式「重新计算全部」或重新覆盖。对齐规格「人工评分优先于自动」语义。
- **选择 C — 0 完整度节点也给健康（score 1）**：compute_five_dim_health 对 None/空 payload 返回全维 score=1（_rule_score ratio=0→1），而非跳过。即「空节点也有健康分（低分）」而非「无健康分」。理由：五维健康是观测体系，未填=观测不足=低分，比「无数据」更可操作；前端五维健康视图对空节点也能渲染条形（而非空态）。L4 仍明确不计算（规格 L4 无 fiveDimHealth）。
- **理由**：三路径全覆盖兑现「更新地图数据后触发重评估」；manual 保留尊重人工判断不被自动覆盖；空节点给低分让健康视图处处可渲染。可校验性：新增 6 测试（create 全字段→5/部分→3/L4 无；adopt L1 满+L2 空都有+快照含健康；update auto 重算 3→5；update 保留 manual）全过；test_business_map_api 17（原 11+6）+ test_reviews_api+test_draft_tools 30 零回归。既有 test_five_dim_health_compute_and_override 仍过（创建已自带 auto 健康，POST /health 重算同分，逻辑不变）。**Phase 5 首个任务**。纯后端改动（service.py 三函数 + 2 helper + 6 测试）。

## 决策 #48：M5.1.3 草稿过期采纳校验 — adopt 主动强制过期（§7.1.6）

- **背景**：M5.1.3「草稿过期测试 | 7天过期提醒 + 过期后草稿不可采纳」。审计发现过期机制**大部分已实现**：BusinessMapDraft 有 `expires_at`（create/update 时设 `now + DRAFT_TTL_DAYS=7`，line 353/364）+ `status: active/adopted/expired` + `_mark_expired_drafts`（懒标记 active→expired，line 288，在 get_active_draft/upsert_draft 调用）。**唯一缺口 = adopt_draft**：它只查 `status != "active"`（line 433）却**未先调 `_mark_expired_drafts`** → 一个 expires_at 已过但未被 get/upsert 触发懒标记的草稿 status 仍="active"，会被错误采纳。抉择：① 在哪强制；② 如何对待 status 缓存。
- **选择 A — adopt_draft 前置 `_mark_expired_drafts` + refresh 复验**：adopt 是写路径（有副作用：创建正式对象+版本快照），必须在产生副作用前主动强制过期，不能依赖读/写路径的懒标记。在 fetch 草稿后、status 校验前插入 `await _mark_expired_drafts(db, project_id)` + `await db.refresh(draft)`——bulk UPDATE 绕过 ORM unit of work，须 refresh 让 `draft` 对象拿到新 status，复验 `status == "active"` 才放行。过期则抛 ValueError（route 映射 400，与既有 adopted 草稿再采纳同模式）。
- **选择 B — 不引入新阈值/配置，复用 DRAFT_TTL_DAYS=7**：过期判定单一真源 = `expires_at < now`，而 expires_at 由既有 create/update 逻辑按 DRAFT_TTL_DAYS 设定。adopt 只校验 status（由 _mark_expired_drafts 按 expires_at 翻转），不重复实现"7天"逻辑，避免双源。
- **选择 C — 「7天过期提醒」(UI) 留作前端跟进**：draft 输出已暴露 `expires_at`（line 282），前端可据此算"N天后过期"显示徽标。本任务聚焦**正确性关键**的「过期不可采纳」(后端强制)，UI 提醒属打磨性质且数据已就绪，留独立前端任务。
- **理由**：补齐 adopt 写路径的过期强制，消除「过期草稿可被采纳」的正确性漏洞；复用既有 _mark_expired_drafts 不造新逻辑。可校验性：新增 2 测试（过期草稿 adopt→400 且被标 expired / 新鲜草稿 adopt→200 回归保护）全过；test_business_map_api 19 + test_reviews_api + test_draft_tools 共 49 零回归。改动仅 adopt_draft 4 行前置校验，新鲜草稿（所有既有测试）no-op，无法扩大 fail 集。纯后端改动。

## 决策 #49：M5.3.2 版本对比 — 快照 vs 当前 diff 端点（§7.4）

- **背景**：M5.3.2「版本对比 | 查看历史版本 + 与当前版本 diff」。审计发现 M4.1.9 已实现版本列表/快照查看(SnapshotModal)/回滚，缺「与当前版本 diff」。数据已就绪：`_snapshot_reviewed_objects` 快照含 payload/level/name/map_type/verification_status（无 id），BusinessMapVersion.snapshot_data.objects 可用。抉择：① diff 比对键（无 id）；② 比哪些字段；③ 前后端分工。
- **选择 A — 按 (level, name) 键比对（非 id）**：快照对象不存 id（_snapshot_reviewed_objects 只序列化业务字段），且对象采纳时每次新建（id 变化），故 id 不可作比对键。用 (level, name) 复合键——同名同层视为同一节点。重命名会被误判为 remove+add，但 v1 可接受的近似（完整 diff 需稳定 id，超出 M5.3.2 范围）。
- **选择 B — 只比结构性字段 map_type / verification_status，不比 payload**：payload 含五维健康派生数据（M5.5.5 后自动变化）+ 大量业务字段，diff payload 噪声大且语义模糊。仅比 map_type（假设↔现状切换）+ verification_status（未验证→成立/推翻等，最有价值的演进信号）。三类结果：added（当前有快照无）/ removed（快照有当前无）/ changed（结构性字段变）。
- **选择 C — 后端 diff 端点 + 前端渲染留跟进**：`GET /api/projects/{id}/business-map/versions/{vid}/diff` 返回 VersionDiffOut（version_number/snapshot_count/current_count + added[]/removed[]/changed[]），require_project_member 只读。复用 `_snapshot_reviewed_objects` 取当前数据。前端 VersionView 增「对比当前」按钮渲染 diff 是自然跟进（端点是可测核心，先落）。
- **理由**：(level,name) 键规避无 id 限制；只比结构性字段避开 payload 噪声聚焦演进信号；后端端点可测先行。可校验性：新增 3 测试（added+changed 命中 / removed 命中 / 404）全过；test_business_map_api 22 零回归。纯增量（新 schema+service 函数+端点），不改既有逻辑，无法扩大 fail 集。纯后端改动。

## 决策 #50：M5.3.2 版本对比前端渲染 — VersionView 对比当前弹窗（§7.4，前端跟进 #49）

- **背景**：决策 #49 已落 diff 后端端点（3c1c318），前端 VersionView 仅「查看快照」「回滚」，缺「对比当前」入口。补齐 M5.3.2 全闭环。契约已定（VersionDiffOut 后端 schema），前端只需镜像类型 + 渲染。
- **选择 A — 弹窗（DiffModal）而非内联展开**：与既有 SnapshotModal 一致（版本行→点按钮→浮层），用户心智模型统一，且 diff 内容较多（统计+三分组）适合弹窗承载。复用 modalOverlayStyle/modalCardStyle。
- **选择 B — DiffModal 挂载即拉取（自含 async），非 VersionView 预拉全量**：版本可能很多，预拉每个版本的 diff 浪费请求；按需在点「对比当前」时拉对应版本一个 diff 最省。DiffModal 内 useEffect[projectId, version.id] 调 diffBusinessMapVersion，含 loading/error/空差异三态。与 NodeEvidenceSection 同款「挂载即拉 + alive 防竞态」模式。
- **选择 C — 渲染分三色组 + 概览统计**：顶部 5 计数块（快照数/当前数/新增/删除/变更）；added 绿分组（success-soft）/ removed 红分组（danger-soft）/ changed 黄行（warn-soft，snapshot→current 用 ChevronRight 过渡，字段中文标签 map_type→地图类型 / verification_status→验证状态）；空差异显示 CircleCheck；底部口径说明（仅看 map_type/verification_status，口径同 #49）。changed 的 snapshot 值灰底、current 值黄框高亮，视觉对比清晰。
- **理由**：弹窗对齐 SnapshotModal 心智；按需拉取省请求；三色分组让 added/removed/changed 一眼可辨，snapshot→current 过渡直观体现演进方向。可校验性：tsc -b 0 错 + vite build 过（纯前端，无后端改动，未跑 pytest——后端端点 #49 已测）。types 镜像后端 Pydantic schema（VersionDiff/Item/ChangedItem），api client 仿 listBusinessMapVersions 加 diffBusinessMapVersion。纯增量，不改既有渲染逻辑。

## 决策 #51：M5.5.4 个人空间项目筛选 — 客户端顶层目录过滤（§2.6，纯前端）

- **背景**：M5.5.4「个人空间项目筛选 | 顶部项目筛选框 + 按项目过滤文件」。规格 §2.6：个人空间按项目自动归档（`个人空间/项目名/资料/...`），顶部下拉框选"全部项目"或指定项目过滤文件树。现状：WorkspaceFileManager（personal/team 共用）头部只有标题，无筛选；个人空间 tree 顶层 = 工作区根目录下的目录/文件。抉择：① 筛选项来源；② 过滤在前端还是后端；③ 共用组件如何隔离。
- **选择 A — 筛选项 = 用户可访问项目（api.listProjects），非 tree 顶层目录枚举**：规格明示"项目"筛选，项目列表是权威来源（同 Topbar ProjectSelector 数据源）。tree 顶层目录名是自由文本，未必与项目对齐；用项目名去匹配顶层目录更符合"按项目筛选"语义。项目列表加载失败静默（不阻塞文件管理），无项目时隐藏下拉框。
- **选择 B — 客户端过滤（useMemo 过滤 nodes），非后端按路径取子树**：tree 已整树返回（api.workspaceTree 无子路径参数），客户端 filter 顶层 `dir.name===projectFilter` 最简，零后端改动、零新端点。后端按项目归档（自动归档，独立 P0 任务）落地后筛选自然生效，本任务只做视图层。
- **选择 C — 筛选逻辑放进共用 WorkspaceFileManager，isPersonal 门控**：WorkspaceFileManager 拥有 nodes 状态与头部，过滤须在 nodes 所在地做；团队空间（api.kind==='team'）不应有项目筛选，故用 `api.kind==='personal'` 门控状态/effect/UI 三处。visibleNodes 仅传给 WorkspaceTree（视图），选中/上传/CRUD 等路径操作仍用原 nodes 不受筛选影响——筛选是纯视图层，不改变工作区真实结构。
- **理由**：客户端过滤零后端成本、随自动归档落地即可用；isPersonal 门控保证团队空间零影响；visibleNodes 仅切视图不切操作语义，路径正确性不受损。可校验性：tsc -b 0 错 + vite build 过（纯前端）。已知边界：当前 consultant-search 归档到 `公开信息/`（非项目作用域，search_tools.py 既有），故筛选某项目时 `公开信息/` 不显示——符合预期（它本就不属于任何项目），随独立自动归档任务把文件按项目名归类后筛选更具实用性。



## 决策 #52：M5.5.1 角色去重 — person_disambiguation 候选生成 + 用户确认（§7.1，后端先行）

- **背景**：M5.5.1「发现重名或相似角色 → 对话中生成 person_disambiguation 候选 → 用户确认 → 更新或新建」。既有：save_stakeholder_card_draft 工具（tools.py）新建角色卡草稿（review_status=draft），POST /adopt(entity_type=stakeholder_card_draft) 已支持 draft→reviewed 自确认采纳。缺口：① 新建草稿不检测疑似同人；② 无候选持久化模型；③ 无候选列表/确认 API；④ 无确认后的合并语义。抉择：① 评分算法；② 合并语义；③ 检测触发点；④ 新模型放哪。
- **选择 A — 评分：姓名为主信号 + 部门/角色加成，阈值 0.6**：完全同名 1.0 / 姓名包含（双方均≥2字）0.6 / 同部门 +0.2 / 同角色类型 +0.2（上限 1.0）。仅 score≥0.6 入候选——姓名不同仅部门角色相同=0.4<阈值，不误报。姓名是规格「重名或相似」的核心信号，部门/角色只作加成区分同名不同人。多候选按分降序全列入 candidates（用户选最像的合并）。
- **选择 B — 合并语义：目标为主、草稿填充缺失（不覆盖既有数据）**：merge 时目标卡为主——标量字段（position/department/reports_to/contact_info/role_type/decision_power）目标为空才用草稿；objective_layer/subjective_layer 浅合并（目标键优先，草稿补缺），主观层重算 compositeScore；behaviors 按 observation 去重追加；stance_change_log 拼接，然后删除草稿。语义：用户认定「草稿=既有卡」，故既有数据不可被草稿覆盖，只补缺。new=草稿独立建卡→promote reviewed（与 /adopt 同语义，幂等：草稿已采纳/删除则只标记候选 resolved）。merge 强约束 merge_into_card_id 必须在候选列表内 + 草稿仍为 draft 态，否则 400。
- **选择 C — 检测在 tools.py 新建分支触发，失败不阻塞**：仅 update_id 为空（新建草稿）时调 detect_and_create_disambiguation，try/except 包裹——去重是辅助提醒，绝不应阻塞草稿主流程（has_dup 前置初始化=False，规避 update 分支引用未定义变量）。更新既有草稿（update_id 有值）不重复检测。检测命中即落库 PersonDisambiguationCandidate(status=pending)，工具结果文本追加「已生成去重候选」提示给 Claude。
- **选择 D — 新模型挂 marketing_map.py（非独立文件），规避 reload 舞蹈**：PersonDisambiguationCandidate 与 StakeholderCard 同属营销地图域，放进既有 models/marketing_map.py（model_marketing_map 已在 conftest Layer2 reload），schemas/service/routes 同样挂既有 marketing_map 文件——零新 reload 行，避免漏接 reload 导致 mapper 分裂（交接指令第5节警示）。仅 models/__init__ 加一行导出。表 person_disambiguation_candidates 由 migrations.py CREATE TABLE IF NOT EXISTS 建立（draft_card_id/merge_into_card_id 用 SET NULL，草稿删除后保留候选行作审计）。
- **理由**：姓名为主信号+阈值规避误报；合并「填充不覆盖」尊重既有数据；tools.py 触发对齐规格「对话中生成」；挂既有文件零 reload 风险。可校验性：新增 7 测试（完全同名+resolve new / 姓名包含 0.6 / 弱信号不误报 / merge 填充+主观层重算+删草稿 / merge 拒绝非候选目标 400 / 重复 resolve 400 / 404）全过；test_marketing_map_api 19（12+7）+ test_draft_tools 19 零回归（中途修一个 has_dup 在 update 分支未定义的真 bug，复测全过）。全量 674 passed/20 failed/3 errors——fail+error 与基线 662/20/3 完全一致（增量 12 含 7 新测），fail 集未扩大。后端先行，前端确认 UI（候选列表渲染 + 新建/合并按钮）作为跟进子任务。

## 决策 #53：M5.5.1 角色去重前端 — DisambiguationBanner 候选确认（§7.1，前端跟进 #52）

- **背景**：决策 #52 已落后端候选生成 + GET/resolve 端点（8025c69），缺前端确认 UI。规格 §7.1「对话中生成候选 → 用户确认 → 更新或新建」。契约已定（DisambiguationCandidateOut 后端 schema），前端镜像类型 + 渲染。抉择：① 渲染形态（Banner vs 弹窗 vs 独立页）；② 拉取时机；③ 处置后状态。
- **选择 A — 营销地图页内 Banner（非弹窗/独立页）**：去重候选是项目级、角色卡域的辅助提醒，挂在 MarketingMapPage 顶部（子视图 Tab 之上、主内容区首），跨所有子视图可见（不限于「角色卡」Tab）。pending 为空时组件自返回 null（DOM 不留痕），与 PendingReviewBanner（决策#45）同款「辅助提醒不占位」范式。复用 warn-soft 背景 + AlertTriangle 图标。
- **选择 B — 自管 fetch + 静默错误（同 PendingReviewBanner 范式）**：DisambiguationBanner 自管 items/loading/acting/expanded 状态，useEffect[projectId] 拉 pending 候选。**失败静默**（catch 空）——去重是辅助提醒，绝不应因它失败阻塞营销地图主流程（与主页面错误处理隔离）。处置（resolve）成功才 toast，失败 toast error 但不抛。
- **选择 C — 每候选一行：新草稿快照 + 候选既有卡逐个「合并」按钮 + 「确认为新人」按钮**：每条候选渲染新草稿名/职位/部门/角色（new_draft_snapshot），候选既有卡列表（candidates）每个一个蓝「合并到「X」%」按钮（含相似度% + title 显示 reasons），中间分隔线后绿「确认为新人」按钮。处置后本地 filter 移除该项 + onChanged 刷新角色卡列表（new→新卡 reviewed / merge→既有卡填充+草稿删除，两种结果都需主列表刷新反映）。折叠态（expanded）复用 ChevronDown 旋转，与拜访卡展开一致。
- **理由**：Banner 对齐 PendingReviewBanner 辅助提醒心智；自管+静默保护主流程；逐候选逐卡按钮让「合并到 X / 新建」一步可达。可校验性：tsc -b 0 错 + vite build 过（纯前端，无后端改动，未跑 pytest——后端端点 #52 已测 7 用例）。types 镜像后端 Pydantic schema（DisambiguationCandidate/DisambiguationCandidateCard/DisambiguationResolveInput），api client 仿 listStakeholderCards 加 listDisambiguationCandidates/resolveDisambiguationCandidate。纯增量，不改既有渲染逻辑。**M5.5.1 角色去重全闭环**（后端 #52 + 前端 #53）。

## 决策 #54：M5.5.3 对象公开机制 — 跨项目可见性聚合端点（§2.6 / §5.x / §6.3，后端先行）

- **背景**：M5.5.3「标记'完全公开'→团队空间可见；'共享给'→指定用户可见」。审计：`is_public`/`shared_with` 字段早已存在于 StakeholderCard / BusinessMapObject / VisitRecord 三模型（§3.5），marketing_map/business_map/visits 三 service 的 create/update 已写入，对应 PUT 端点就绪——**标记机制后端已完成**。真实缺口仅「跨项目可见性聚合」：现有列表查询全按 project_id 限项目内（§7.3 项目内透明），无端点让 is_public=true 或 shared_with∋我的对象被跨项目看到。另：现有 `team_spaces` 模块是 V1.0 文件协作工作区（TeamSpace + 成员 + 文件锁），非规格 §2.6 所述「公开资产区 + 方法论库」，公开资产区是**新概念**。抉择：① 覆盖哪些对象类型；② 挂哪个模块规避 reload 风险；③ 是否动项目级访问控制；④ 用户搜索（共享给 picker）放哪。
- **选择 A — 范围限定为有字段的 3 类（角色卡/业务地图片段/拜访记录）**：规格 §5.x 列公开类型含「方案/知识片段」，但这两者无 is_public 字段（TalkScript/KnowledgeBase 无此列），超范围。聚合端点按 cards/business_objects/visits 三组返回，与有字段的模型一一对应，不造半成品。
- **选择 B — 复用既有 team_spaces 模块（schema+service+route 全在 reload 舞蹈内），零 conftest 改动**：新增 PublicAssetItem/PublicAssetsOut/UserSearchOut 挂 schemas/team_spaces.py（Layer2 已 reload），list_public_assets/list_shared_with_me/search_users 挂 modules/team_spaces/service.py（Layer4 已 reload），3 端点挂 api/routes/team_spaces.py（Layer5 已 reload）——**零新 reload 行**，规避漏接 reload 致 mapper 分裂（交接指令第5节警示，M5.5.1 决策#52 同款手法）。team_spaces 语义上也合理：它是跨项目协作模块，公开资产 + 用户搜索皆跨项目对象级共享。
- **选择 C — 加法式设计，不碰 require_project_member**：公开资产端点只用 current_user 鉴权（公开=对所有登录用户可见，§5.x），**不改**项目级 list/get 的项目成员校验。公开对象同时「原项目内正常可见 + 团队空间公开资产区可见」（§6.3）——项目内走既有项目级端点，跨项目走新聚合端点，两套互不干扰。聚合返回最小展示信息（object_type/object_id/project_name/title/subtitle/created_by_name），不放大对象全字段，亦不放行单对象深链（避免在项目级 GET 上开后门）。
- **选择 D — 仅 reviewed 进聚合（§7.3）+ JSONB @> 查 shared_with**：草稿/待审/驳回即便 is_public=1 或 shared_with 含我也不进聚合（与项目级页面「只展示 reviewed」一致）。shared_with 查询用 `cast([uid], JSONB)` + `.op("@>")(cond)`（与 visits/service.py:200 同款成熟范式，规避 asyncpg JSONB 类型陷阱）。另加 `/users/search` 端点（active 用户 ilike 搜索，镜像既有 search_member_candidates 但去团队空间范围限制），供前端「共享给」picker。
- **理由**：标记机制后端已成→只补聚合；复用 team_spaces 零 reload 风险；加法式不动项目级访问控制降风险；仅 reviewed + JSONB @> 语义正确。可校验性：新增 5 测试（公开聚合排除草稿/私有+跨类型+enrichment / 空公开返回三空数组 / shared-with-me 仅命中且公开未共享不进 / 草稿 shared 不进 / 用户搜索命中+空关键字 422）全过；test_team_spaces_api + test_team_workspace_api + test_team_space_file_locks 共 20 零回归（路由顺序改动：3 新端点置于 /{space_id}:int 之前避免字面量误匹配）。纯后端增量。**测试关键学习**：直接用 ORM 的测试必须在函数内晚导入 app.models（app_env reload 后），collection 阶段顶层导入会绑定旧 Base 致 mapper 分裂（FeedbackIssue↔FeedbackAttachment 报错）——conftest test_user fixture 同款晚导入范式。后端先行，前端标记 UI（CardEditModal/NodeEditModal/VisitFormModal 暴露 is_public/shared_with）+ 公开资产区 tab 作为跟进子任务。
