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
