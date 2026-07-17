# GW AiTool

GW AiTool 是一个面向企业咨询与项目协作场景的 AI Agent 工作平台。系统以客户和项目为业务入口，将大模型对话、顾问工作流、业务地图、团队空间、文件处理及后台管理等能力整合在同一套 Web 应用中。

项目采用前后端分离的开发架构，并支持将前端构建产物与后端服务打包为统一的 Docker 应用。

## 主要功能

- 客户、项目和项目成员管理
- AI Agent、Skill 与 Plugin 管理
- 流式 AI 对话与业务工作流
- 业务地图、营销地图及相关顾问成果管理
- 个人工作区、团队空间与文件协作
- 用户、组织、角色、菜单和审计管理
- 模型配置、用量统计与系统反馈
- 文档上传、转换和在线预览

## 技术栈

| 层级 | 主要技术 |
| --- | --- |
| 前端 | React 18、TypeScript、Vite、React Flow |
| 后端 | Python 3.13、FastAPI、SQLAlchemy、Pydantic |
| AI 集成 | Claude Agent SDK、Anthropic 兼容模型接口、MCP |
| 数据存储 | PostgreSQL、Redis、本地或挂载文件目录 |
| 工程化 | uv、npm、pytest、Docker、Docker Compose |

## 项目架构

```mermaid
flowchart LR
    U[浏览器] --> F[React / Vite 前端]
    F -->|HTTP / SSE| A[FastAPI API 服务]

    A --> B[业务模块]
    B --> DB[(PostgreSQL)]
    B --> R[(Redis)]
    B --> FS[工作区与文件存储]

    A --> AI[AI 编排与 Agent 运行层]
    AI --> LLM[大模型兼容接口]
    AI --> MCP[MCP 与外部工具]

    A --> DOC[文档转换与预览服务]
```

后端按领域模块组织业务逻辑。前端通过 REST API 完成常规数据交互，通过 SSE 接收 AI 对话和任务执行过程中的流式事件。PostgreSQL 保存核心业务数据，Redis 用于运行状态和协作锁等临时状态，用户及团队文件存放在独立工作区目录中。

## 目录结构

```text
GW_AiTool-main/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI 路由
│   │   ├── core/             # 配置、日志、安全与基础设施
│   │   ├── db/               # 数据库连接和初始化
│   │   ├── integrations/     # 大模型、MCP、文档服务等集成
│   │   ├── models/           # SQLAlchemy 数据模型
│   │   ├── modules/          # 按业务领域划分的服务模块
│   │   ├── plugins_seed/     # 内置 Plugin 模板
│   │   └── skills_seed/      # 内置 Skill 模板
│   ├── tests/                # 后端测试
│   ├── pyproject.toml        # Python 项目与依赖配置
│   └── uv.lock               # Python 依赖锁文件
├── frontend/
│   ├── src/
│   │   ├── api/              # API 客户端
│   │   ├── components/       # 通用组件
│   │   ├── pages/            # 页面与业务界面
│   │   ├── styles/           # 样式资源
│   │   └── types/            # TypeScript 类型
│   ├── tests/                # 前端测试
│   └── package.json          # 前端依赖与脚本
├── docker/                   # 镜像与 Compose 配置
├── docs/                     # 设计和开发文档
├── design/                   # 产品及业务设计资料
├── scripts/                  # 构建和发布脚本
└── Makefile                  # 常用开发命令
```

## 本地启动

### 环境要求

- Linux 或 macOS 开发环境
- Docker
- GNU Make
- Node.js 20 或更高版本及 npm
- [uv](https://docs.astral.sh/uv/)

### 1. 初始化项目

在项目根目录执行：

```bash
make init
```

该命令会：

1. 创建本地 `backend/.env` 占位配置；
2. 启动 PostgreSQL 和 Redis；
3. 安装后端及前端依赖。

### 2. 配置环境变量

编辑 `backend/.env`，至少确认以下配置：

```dotenv
APP_ENV=development
APP_SECRET=请替换为随机且足够长的字符串

ANTHROPIC_AUTH_TOKEN=模型服务密钥
ANTHROPIC_BASE_URL=Anthropic兼容模型接口地址
ANTHROPIC_MODEL=模型名称

ZHIPU_WEB_SEARCH_API_KEY=智谱联网搜索密钥

DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent
REDIS_URL=redis://localhost:6379/0

WECHAT_WORK_CORP_ID=本地或实际配置
WECHAT_WORK_AGENT_ID=本地或实际配置
WECHAT_WORK_SECRET=本地或实际配置
```

`ZHIPU_WEB_SEARCH_API_KEY` 只在启用联网搜索时需要。文档转换、Office 预览和多模型供应商等扩展能力可根据部署环境继续配置。

不要将包含真实密钥的 `.env` 文件提交到代码仓库。

### 3. 启动后端

打开一个终端执行：

```bash
make backend
```

后端默认地址为 `http://localhost:8000`，健康检查地址为：

```text
http://localhost:8000/api/health
```

### 4. 启动前端

打开另一个终端执行：

```bash
make frontend
```

前端默认地址为：

```text
http://localhost:5173
```

Vite 开发服务器会将 `/api` 请求代理到本地 `8000` 端口。

### 5. 创建初始管理员

首次启动后可执行：

```bash
cd backend
uv run python -m app.scripts.create_user admin 请替换为安全密码 --role admin
```

随后使用该账号登录系统。普通用户也可以通过注册页面申请账号，并由管理员审批。

## Docker 启动

项目的常规 Docker 镜像依赖本地基础镜像。首次使用时，在项目根目录执行：

```bash
docker build -f docker/Dockerfile_base -t gokagent-backend:base .
docker compose -f docker/docker-compose.yml up --build -d
```

启动后通过 `http://localhost:8000` 访问应用。Compose 会同时启动 PostgreSQL、Redis 和应用服务，并将运行数据保存到 `docker/volumes/`。

查看或停止服务：

```bash
docker compose -f docker/docker-compose.yml ps
docker compose -f docker/docker-compose.yml logs -f backend
docker compose -f docker/docker-compose.yml down
```

生产或离线镜像交付方式参见 `docker/release/README.md`。

## 常用开发命令

```bash
make help              # 查看全部 Make 命令
make infra             # 启动 PostgreSQL 和 Redis
make status            # 查看基础服务状态
make test              # 运行后端测试
make down              # 停止本地基础服务

cd frontend && npm run build   # 检查并构建前端
```

## 开发说明

- 后端启动时会自动初始化数据库结构和必要的内置数据。
- 开发模式下，前端与后端分别运行；部署镜像中由 FastAPI 同时提供前端静态资源和 API。
- AI 能力依赖所配置模型服务的协议兼容性、账号余额和网络连通性。
- Redis、工作区目录和团队空间目录属于运行时数据，部署时应配置持久化存储和备份策略。
- 新增配置项时，应同步更新部署环境、Compose 配置和本文档。

## License

本项目当前未附带公开许可证。使用、复制和分发前，请确认项目所有者及所在组织的授权要求。
