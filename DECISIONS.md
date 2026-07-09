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
