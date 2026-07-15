# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

咨询顾问作战台 — 基于 `claude-agent-sdk` 的多智能体对话与文件管理平台。

- **Backend**: Python 3.13 + FastAPI + SQLAlchemy 2.0(async) + PostgreSQL
- **Frontend**: React 18 + TypeScript + Vite
- **AI 运行时**: `claude-agent-sdk` (封装 Claude Code 能力)
- **认证**: 企业微信扫码/SSO 登录
- **文档转换**: MinerU (Office/PDF → Markdown)

## 常用命令

### 后端

```bash
cd backend

# 安装依赖 (uv)
uv sync

# 开发运行 (需要 .env 配置,见下方)
uv run uvicorn app.main:app --reload --port 8000

# 运行全部测试 (需要本地 PostgreSQL + gokagent_test 数据库)
uv run pytest

# 运行单个测试文件
uv run pytest tests/test_auth_api.py

# 运行单个测试用例
uv run pytest tests/test_auth_api.py::test_login_flow -v

# 创建管理员用户 (命令行)
uv run python -m app.scripts.create_user <username> <password> --role admin
```

### 前端

```bash
cd frontend

# 安装依赖
npm install

# 开发服务器 (代理 /api 到 localhost:8000)
npm run dev

# 生产构建
npm run build

# 预览构建产物
npm run preview

# 前端测试 (Node.js assert,无框架)
npm test   # 如果 package.json 中配置了 test 脚本
```

### Docker 部署

```bash
cd docker

# 启动 PostgreSQL + Backend
docker-compose up -d

# 查看日志
docker-compose logs -f backend
```

### 项目根目录快捷操作

```bash
# 一次性启动前后端 (需要两个终端)
# 终端1
cd backend && uv run uvicorn app.main:app --reload
# 终端2
cd frontend && npm run dev
```

## 环境配置

后端依赖 `backend/.env` 文件。必填项:

- `APP_SECRET` — Cookie 签名密钥
- `DATABASE_URL` — PostgreSQL 连接串 (默认 `postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent`)
- `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BASE_URL` — AI 供应商凭证
- `WECHAT_WORK_CORP_ID` / `WECHAT_WORK_AGENT_ID` / `WECHAT_WORK_SECRET` — 企业微信配置
- `WECHAT_WORK_LOGIN_MODE` — `qrcode`(自建二维码) 或 `sso`(企微跳转)

参考: `backend/.env.example`

## 代码架构

### 后端 (`backend/app/`)

采用分层架构,依赖方向: `api` → `modules` → `models`/`db`, `integrations` 独立。

| 目录 | 职责 |
|------|------|
| `app/main.py` | FastAPI 应用工厂,生命周期管理 (数据库初始化、转换队列、企微部门同步) |
| `app/api/` | HTTP 路由层,薄适配器,不做业务逻辑。`api/router.py` 聚合所有路由 |
| `app/api/deps.py` | FastAPI 依赖: `current_user`, `require_admin` (session-based 认证) |
| `app/modules/` | 业务逻辑层 |
| `app/modules/agents/` | 智能体 CRUD + **独立工作目录管理** (`workdir.py`) |
| `app/modules/sessions/` | 会话 CRUD + **SSE 流式对话编排** (`streaming.py`) + 运行态管理 (`run_state.py`) |
| `app/modules/workspace/` | 用户个人空间文件树、预览、下载、Markdown 索引 |
| `app/modules/conversions/` | Office/PDF → Markdown 转换任务队列 (基于 asyncio Queue 的 worker 池) |
| `app/modules/catalog/` | 技能/插件/命令扫描 |
| `app/modules/auth/` | 企微认证 + 部门同步 |
| `app/modules/usage/` | 使用量统计与聚合 |
| `app/models/` | SQLAlchemy ORM 模型 (DeclarativeBase) |
| `app/schemas/` | Pydantic 请求/响应模型 |
| `app/db/` | 引擎、会话工厂、兼容性迁移 (`migrations.py` 自动建表/加列) |
| `app/integrations/claude/` | Claude SDK 封装: `runner.py` (对话流), `serializers.py` (消息序列化), `guard.py` (工具钩子) |
| `app/integrations/mineru.py` | MinerU API 调用 (文档转 Markdown) |
| `app/core/config.py` | 配置读取 + 多供应商模型解析 (`ANTHROPIC_PROVIDER_*` 前缀) |

### 核心数据流:对话

1. 前端通过 SSE 连接 `/api/sessions/{id}/chat`
2. `streaming.py::stream_session_chat` 创建 run,启动 `claude-agent-sdk` (`runner.py::stream_chat`)
3. SDK 消息经 `serializers.py` 转成前端事件,写入 `run_state_store` 内存缓存
4. 同时通过 SSE 推送给前端;客户端断开后可从 `/api/sessions/{id}/running/stream` 恢复
5. 对话结束后写入 `chat_sessions` 表 + `usage_events` 表

### 智能体隔离模型

- 每个智能体在 `AGENT_WORKDIRS_DIR/<agent_code>/` 下有**独立**的 `CLAUDE_CONFIG_DIR`
- 运行时从主目录 (`CLAUDE_DATA_DIR`) 拷贝勾选的 `plugins/`、`skills/`、`CLAUDE.md`
- 对话时通过 `ClaudeAgentOptions.env` 注入 `CLAUDE_CONFIG_DIR`,实现并发隔离
- `override_claude_config_dir()` 用于必须走全局 env 的 SDK 工具函数 (历史读取/删除)

### 前端 (`frontend/src/`)

| 目录 | 职责 |
|------|------|
| `src/App.tsx` | 根组件:鉴权门 + 主题切换 + 视图路由 (Sidebar/Topbar/页面) |
| `src/api/client.ts` | 所有 API 调用封装 + SSE 流解析 (`streamChat`, `streamRunningSession`) |
| `src/pages/` | 页面级组件: `ChatWorkspace`, `WorkspacePage`, `AgentsPage`, `SkillsPage`, `UsageAnalyticsPage`, `FeedbackAdminPage`, `LoginPage` |
| `src/components/` | 共享组件: `Sidebar`, `Topbar`, `ToolCall`, `FeedbackDialog` |
| `src/lib/` | 业务工具库: `workspace.ts`, `commandMenu.ts`, `chatModelSelection.ts` |
| `src/types/index.ts` | 全局 TypeScript 类型 |

### 数据库关键表

- `users` — 用户 (企微字段 + role: user/admin)
- `agents` — 智能体 (name, code, system_prompt, skills, plugins, category_id)
- `chat_sessions` — 会话 (UUID,关联 agent_id, claude_session_id 存 SDK 会话标识)
- `categories` / `skill_bindings` / `plugin_bindings` — 分类管理
- `conversion_tasks` — 文档转换任务队列状态
- `feedback_issues` / `feedback_attachments` — 问题反馈
- `usage_events` / `usage_resource_events` — 使用量统计
- `departments` — 企微部门同步缓存

### 测试

- **后端**: `pytest` + `pytest-asyncio`, 使用 `AsyncClient` + `ASGITransport` 测完整 API
  - `conftest.py` 提供 `client`(未登录), `logged_in_client`(普通用户), `admin_client`(管理员)
  - 测试数据库: `gokagent_test` (自动 DROP SCHEMA + 重建)
  - 大量 mock 企微 API (`wechat_work` 模块)
- **前端**: Node.js 原生 `assert`,无测试框架,直接 `node tests/xxx.test.ts`

## 开发注意事项

- **认证**: 全站基于 `session` (非 JWT),`current_user` 从 `request.session["user_id"]` 读取
- **权限**: `require_admin` 检查 `user.role == "admin"`,管理接口统一使用
- **文件上传**: 前端用 `XMLHttpRequest` 支持进度条;`multipart/form-data` **不能**手动设置 Content-Type
- **路径安全**: 所有用户传入的相对路径必须经过 `resolve_inside_workspace()` 校验,禁止逃出工作区
- **模型供应商**: 新增供应商只需加环境变量 `ANTHROPIC_PROVIDER_<NAME>_{AUTH_TOKEN,BASE_URL,MODELS}`
- **转换任务**: 进程内 asyncio Queue 调度,启动时从数据库恢复 `queued` 状态任务
- **企微登录模式**: `qrcode` 模式下前端轮询 `/api/auth/wechat-work/poll-code`;`sso` 模式下后端直接跳转授权

## Commit 规范
commit message必须以feat,fix,docs,style,refactor,test,chore,revert,Merge,deploy开头。
示例: feat:添加用户登录功能

## 其他规范

- 使用中文进行交互。
- 给代码增加必要的中文注释。
- 每次完成任务自动提交相关的变更，非本次任务相关的变更不要提交。