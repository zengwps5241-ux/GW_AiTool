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

### M1.3 客户与项目模型 ⏳ 待开始

| 任务 | 状态 |
|------|------|
| M1.3.1 Customer 模型 | ⏳ |
| M1.3.2 Project 模型 | ⏳ |
| M1.3.3 ProjectMember 模型 | ⏳ |
| M1.3.4 ProjectDepartmentAccess 模型 | ⏳ |
| M1.3.5 Customer CRUD API | ⏳ |
| M1.3.6 Project CRUD API | ⏳ |
| M1.3.7 项目创建自动生成 Agent | ⏳ |
| M1.3.8 权限中间件 | ⏳ |
| M1.3.9 前端项目选择器 | ⏳ |

### M1.4 导航重构 ⏳ 待开始

| 任务 | 状态 |
|------|------|
| M1.4.1 Sidebar 更新 | ⏳ |
| M1.4.2 路由更新 | ⏳ |

---

## Phase 2-5

（Phase 1 完成后展开）
