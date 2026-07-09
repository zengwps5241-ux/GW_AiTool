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



