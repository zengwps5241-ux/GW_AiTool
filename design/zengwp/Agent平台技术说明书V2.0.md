# AI 顾问作战台 · 技术说明书 V2.0

> 基于 Claude Agent SDK 的轻咨询 AI 作战平台技术方案
>
> **文档版本**：V2.0
> **上一版本**：V1.0（通用 Agent 平台技术说明书，已退役）
> **编写日期**：2026-07-06
> **依赖文档**：[需求规格说明书 V2.1](需求规格说明书V2.0.md)
> **技术栈**：Python 3.13 + FastAPI + PostgreSQL + React 18 + TypeScript + Vite + Claude Agent SDK

---

## 目录

- [1. 文档概述](#1-文档概述)
- [2. 总体架构](#2-总体架构)
- [3. 核心数据模型](#3-核心数据模型)
- [4. 多智能体协作机制](#4-多智能体协作机制)
- [5. Skill 与 Plugin 技术设计](#5-skill-与-plugin-技术设计)
- [6. 前端架构](#6-前端架构)
- [7. API 设计](#7-api-设计)
- [8. 文件与 Workspace 规范](#8-文件与-workspace-规范)
- [9. 事件流与审计规范](#9-事件流与审计规范)
- [10. 安全与权限边界](#10-安全与权限边界)
- [11. LLM 技术能力](#11-llm-技术能力)
- [12. 实施阶段](#12-实施阶段)
- [13. 验收标准](#13-验收标准)
- [附录 A：与 V1.0 的关系](#附录-a与-v10-的关系)

---

## 1. 文档概述

### 1.1 文档定位

本文档是 **AI 顾问作战台**（内部代号 `consultant-war-room`）的技术实施方案，说明系统架构、数据模型、组件交互、接口契约、安全边界和分阶段实施计划。

本文档是 [需求规格说明书 V2.1](需求规格说明书V2.0.md) 的技术落地文档。需求规格说明书定义"做什么"，本文档定义"怎么做"。

### 1.2 建设目标

在现有智能体平台底座（`agent-platform-main`）基础上，扩展建设面向轻咨询业务场景的 AI 协作平台，实现：

- **全流程闭环**：假设地图 → 拜访方案 → 现场验证 → 现状地图 → 营销地图 → 知识沉淀
- **AI 驱动**：基于 Claude Agent SDK 的 7 个 Skill 覆盖核心工作流，LLM 负责推理、生成、结构化输出
- **人机协同**：AI 产出候选 → 用户确认/驳回/调整 → 正式数据入库，人始终在决策环中
- **知识沉淀**：拜访证据、角色卡、话术、偏差案例自动归档，形成团队可复用资产

### 1.3 第一版范围

| 范围 | 说明 |
|------|------|
| **包含** | Customer/Project/BusinessMapObject/StakeholderCard/VisitRecord/EvidenceSource/TalkScript 数据模型；7 个 Skill（WF02/WF03/WF06/WF07/WF09/WF10/WF12）；2 个 Plugin（router/defense）+ 智谱 MCP 搜索（平台内置）；业务地图/营销地图/拜访记录/个人空间/团队空间前端页面；三层权限模型；SSE 流式对话；文件自动归档 |
| **不包含** | Plugin marketplace；复杂商业化租户体系；完整事件回放；DAG 工作流引擎；移动端 App；离线模式 |
| **存储** | 结构化数据使用 PostgreSQL；文件使用服务器本地文件系统（后续可迁移至对象存储） |

### 1.4 与现有系统的关系

本系统复用 `agent-platform-main` 的以下基础设施，不做破坏性修改：

| 复用项 | 复用方式 | 扩展内容 |
|--------|---------|---------|
| `User` 模型 + Session 认证 | 直接复用 | 无 |
| `Agent` 模型 + 工作目录隔离 | 扩展 | 项目创建时自动创建 Agent 实例，绑定 Skill/Plugin 集合 |
| `ChatSession` + SSE 流式对话 | 直接复用 | 注入项目上下文（客户名、行业、阶段） |
| `wrapper.py` LLM 调用封装 | 直接复用 | 无 |
| 智谱 Web Search MCP | 直接复用 | 内置 MCP Server（SSE 协议），Claude Agent 直接调用 `web_search` 工具 |
| Skills/Plugins 上传与管理 | 直接复用 | 新增 7 个 Skill + 2 个 Plugin 的 SKILL.md/配置 |
| 个人空间/团队空间文件系统 | 扩展 | 项目筛选 + 自动归档 + 公开资产区 |
| 数据库 + 迁移机制 | 直接复用 | 新增 8 张业务表 |

---

## 2. 总体架构

### 2.1 架构分层

```
┌──────────────────────────────────────────────────────────────┐
│                        前端 (React 18 + TypeScript + Vite)     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ 对话页    │ │ 业务地图  │ │ 营销地图  │ │ 拜访记录  │        │
│  │ Chat     │ │ BizMap   │ │ MktMap   │ │ VisitLog │        │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘        │
│       │             │            │            │               │
│  ┌────┴─────────────┴────────────┴────────────┴─────┐        │
│  │              API Client (SSE + REST)              │        │
│  └──────────────────────────────────────────────────┘        │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP/SSE
┌──────────────────────────┴───────────────────────────────────┐
│                     API 层 (FastAPI)                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ Auth     │ │ Customer │ │ Project  │ │ BizMap   │        │
│  │ 认证/鉴权 │ │ 客户 API  │ │ 项目 API  │ │ 地图 API  │        │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ MktMap   │ │ Visit    │ │ Session  │ │ Workspace│        │
│  │ 营销地图  │ │ 拜访 API  │ │ 对话 API  │ │ 文件空间  │        │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘        │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────┴───────────────────────────────────┐
│                    业务逻辑层 (modules/)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ Customer │ │ Project  │ │ BizMap   │ │ MktMap   │        │
│  │ Service  │ │ Service  │ │ Service  │ │ Service  │        │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ Visit    │ │ Evidence │ │ Skill    │ │ Archive  │        │
│  │ Service  │ │ Service  │ │ Router   │ │ Service  │        │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘        │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────┴───────────────────────────────────┐
│                    AI 运行层 (integrations/claude/)            │
│  ┌──────────────────────────────────────────────────────┐    │
│  │              Claude Agent SDK (runner.py)             │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐           │    │
│  │  │ Main     │  │ Subagent │  │ Subagent │           │    │
│  │  │ Agent    │─→│ A (研究)  │  │ B (审核)  │           │    │
│  │  └──────────┘  └──────────┘  └──────────┘           │    │
│  │       │              │              │                 │    │
│  │       └──────────────┴──────────────┘                 │    │
│  │                      │                                │    │
│  │  ┌───────────────────┴──────────────────┐            │    │
│  │  │ Skill 注入  │ Plugin Hook  │ Guard   │            │    │
│  │  └──────────────────────────────────────┘            │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────┴───────────────────────────────────┐
│                    存储层                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐        │
│  │PostgreSQL│  │  Redis   │  │  本地文件系统          │        │
│  │ 业务数据  │  │ 会话缓存  │  │  uploads/ workspaces/ │        │
│  └──────────┘  └──────────┘  └──────────────────────┘        │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈

| 层级 | 技术选型 | 版本 | 说明 |
|------|---------|------|------|
| **后端框架** | FastAPI | ≥0.115 | 异步 Web 框架 |
| **ORM** | SQLAlchemy 2.0 | 2.0+ | 异步 session + DeclarativeBase |
| **数据库** | PostgreSQL | 16+ | 主数据存储 |
| **缓存/队列** | Redis | 7+ | Session 缓存、Run 状态缓存 |
| **AI SDK** | claude-agent-sdk | — | 内部封装的 Claude Code 能力 SDK |
| **LLM** | DeepSeek V4 Pro / Flash | — | 双档路由：Pro 处理复杂任务，Flash 处理简单意图分类 |
| **文档转换** | MinerU API | — | Office/PDF → Markdown |
| **前端框架** | React 18 + TypeScript | 18.x | SPA 单页应用 |
| **构建工具** | Vite | 5.x | 快速 HMR + 生产构建 |
| **样式方案** | CSS Variables + CSS Modules | — | 羊皮纸色板主题，支持亮/暗切换 |
| **状态管理** | React Context + useReducer | — | 轻量级，无外部状态库依赖 |
| **HTTP 客户端** | Fetch API + SSE | — | 流式对话通过 EventSource |
| **文件处理** | xlsx / mammoth / pdf-parse | — | 前端上传预览 |

### 2.3 项目目录结构

```
agent-platform-main/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI 应用工厂
│   │   ├── api/
│   │   │   ├── router.py              # 路由聚合
│   │   │   ├── deps.py                # 依赖注入 (current_user, require_admin)
│   │   │   ├── auth_guard.py          # API 鉴权守卫
│   │   │   └── routes/
│   │   │       ├── auth.py            # 认证（企微登录/登出）
│   │   │       ├── sessions.py        # 对话 Session + SSE 流
│   │   │       ├── agents.py          # Agent CRUD
│   │   │       ├── customers.py       # 🆕 客户 CRUD
│   │   │       ├── projects.py        # 🆕 项目 CRUD + 成员管理
│   │   │       ├── business_maps.py   # 🆕 业务地图 CRUD
│   │   │       ├── marketing_maps.py  # 🆕 营销地图 CRUD
│   │   │       ├── visit_records.py   # 🆕 拜访记录 + 证据 CRUD
│   │   │       ├── talk_scripts.py    # 🆕 话术 CRUD
│   │   │       ├── workspace.py       # 个人/团队空间文件
│   │   │       └── admin_*.py         # 管理端
│   │   ├── models/
│   │   │   ├── customer.py            # 🆕 Customer
│   │   │   ├── project.py             # 🆕 Project + ProjectMember
│   │   │   ├── business_map.py        # 🆕 BusinessMapObject + PreAnalysis
│   │   │   ├── marketing_map.py       # 🆕 StakeholderCard
│   │   │   ├── visit_record.py        # 🆕 VisitRecord
│   │   │   ├── evidence.py            # 🆕 EvidenceSource
│   │   │   ├── talk_script.py         # 🆕 TalkScript
│   │   │   ├── intent_log.py          # 🆕 IntentRoutingLog
│   │   │   └── ...                    # 现有模型保持不变
│   │   ├── modules/
│   │   │   ├── customers/service.py   # 🆕 客户业务逻辑
│   │   │   ├── projects/service.py    # 🆕 项目业务逻辑
│   │   │   ├── business_maps/service.py  # 🆕 业务地图逻辑
│   │   │   ├── marketing_maps/service.py # 🆕 营销地图逻辑
│   │   │   ├── visits/service.py      # 🆕 拜访记录逻辑
│   │   │   ├── evidence/service.py    # 🆕 证据管理逻辑
│   │   │   ├── skill_router/service.py   # 🆕 意图路由逻辑
│   │   │   ├── defense/service.py     # 🆕 防线逻辑
│   │   │   ├── archive/service.py     # 🆕 自动归档逻辑
│   │   │   └── ...                    # 现有模块保持不变
│   │   ├── schemas/                   # Pydantic 请求/响应 Schema
│   │   ├── integrations/claude/       # Claude SDK 封装
│   │   ├── core/                      # 配置/安全/日志
│   │   └── db/                        # 数据库引擎/迁移
│   └── tests/                         # pytest 测试
├── frontend/
│   ├── src/
│   │   ├── App.tsx                    # 根组件：鉴权门 + 路由
│   │   ├── main.tsx                   # 应用入口
│   │   ├── api/
│   │   │   └── client.ts             # API 调用 + SSE 流解析
│   │   ├── pages/
│   │   │   ├── ChatWorkspace.tsx      # 对话页（含 WF chips）
│   │   │   ├── BusinessMapPage.tsx    # 🆕 业务地图页
│   │   │   ├── MarketingMapPage.tsx   # 🆕 营销地图页
│   │   │   ├── VisitRecordsPage.tsx   # 🆕 拜访记录页
│   │   │   ├── WorkspacePage.tsx      # 个人空间（扩展项目筛选）
│   │   │   ├── TeamSpacesPage.tsx     # 团队空间（扩展公开资产区）
│   │   │   └── ...
│   │   ├── components/
│   │   │   ├── Sidebar.tsx            # 侧栏导航（扩展示例页面入口）
│   │   │   ├── Topbar.tsx             # 顶栏
│   │   │   ├── ProjectSwitcher.tsx    # 🆕 项目选择器（公共组件）
│   │   │   ├── ToolCall.tsx           # 工具调用展示
│   │   │   └── ...
│   │   ├── types/index.ts            # 全局类型定义
│   │   └── lib/                       # 工具库
│   └── ...
└── design/
    └── zengwp/
        ├── 需求规格说明书V2.0.md
        ├── Agent平台技术说明书V2.0.md  ← 本文档
        └── ...
```

---

## 3. 核心数据模型

### 3.1 数据库 ER 图

```
┌──────────┐       ┌──────────────────┐       ┌──────────┐
│   User   │       │  ProjectMember   │       │ Project  │
│ (现有)    │──<    │ role: owner/dep  │    >──│ (扩展)    │
└──────────┘       └──────────────────┘       └────┬─────┘
                                                    │
                          ┌─────────────────────────┼──────────────────────┐
                          │                         │                      │
                    ┌─────┴──────┐          ┌──────┴──────┐       ┌──────┴──────┐
                    │  Customer  │          │    Agent    │       │   Session   │
                    │  (新增)     │          │  (复用扩展)  │       │  (复用扩展)  │
                    └────────────┘          └────────────┘       └────────────┘
                                                    │
        ┌───────────────────┬───────────────────────┼───────────────────┬────────────────┐
        │                   │                       │                   │                │
  ┌─────┴──────┐   ┌────────┴────────┐   ┌─────────┴────────┐  ┌──────┴──────┐  ┌─────┴──────┐
  │BizMapObject│   │StakeholderCard  │   │   VisitRecord    │  │ TalkScript  │  │  Material  │
  │  (新增)     │   │    (新增)        │   │     (新增)        │  │   (新增)     │  │ (复用扩展)  │
  └─────┬──────┘   └────────┬────────┘   └────────┬────────┘  └─────────────┘  └────────────┘
        │                   │                       │
  ┌─────┴──────┐            │                ┌──────┴──────┐
  │PreAnalysis │            │                │EvidenceSource│
  │  (新增)     │            │                │   (新增)      │
  └────────────┘            │                └──────┴──────┘
                      ┌─────┴──────┐               │
                      │StanceLog   │               │
                      │BehaviorLog │               │
                      │  (新增)     │               │
                      └────────────┘               │
                                            ┌──────┴──────┐
                                            │IntentLog    │
                                            │  (新增)      │
                                            └─────────────┘
```

### 3.2 新增表结构设计

#### 3.2.1 `customers` — 客户

```sql
CREATE TABLE customers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,                    -- 客户名称，如"中石油"
    industry        VARCHAR(100),                             -- 行业
    scale           VARCHAR(20) DEFAULT '中型',               -- 大型/中型/小型
    region          VARCHAR(255),                             -- 地区
    description     TEXT,                                     -- 描述
    org_structure   JSONB DEFAULT '{"departments": []}',     -- 组织架构 JSON
    created_by      INTEGER NOT NULL REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    visibility      VARCHAR(20) DEFAULT 'private',           -- private / team
    sensitivity     VARCHAR(20) DEFAULT 'internal'            -- 敏感级别
);

CREATE INDEX idx_customers_created_by ON customers(created_by);
CREATE INDEX idx_customers_name ON customers(name);
```

#### 3.2.2 `projects` — 项目

```sql
CREATE TABLE projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,                    -- 项目名称
    agent_id        UUID REFERENCES agents(id),              -- 关联 Agent（自动创建）
    project_type    VARCHAR(50) DEFAULT '诊断',               -- 诊断/试点/落地
    fde_stage       VARCHAR(50) DEFAULT 'lead_screening',    -- 当前阶段
    status          VARCHAR(20) DEFAULT 'active',             -- active/paused/completed/archived
    description     TEXT,
    objectives      TEXT,
    created_by      INTEGER NOT NULL REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    visibility      VARCHAR(20) DEFAULT 'private',
    sensitivity     VARCHAR(20) DEFAULT 'internal'
);

CREATE INDEX idx_projects_customer ON projects(customer_id);
CREATE INDEX idx_projects_agent ON projects(agent_id);
CREATE INDEX idx_projects_created_by ON projects(created_by);
```

#### 3.2.3 `project_members` — 项目成员

```sql
CREATE TABLE project_members (
    id              SERIAL PRIMARY KEY,
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL DEFAULT 'deputy',   -- owner / deputy
    joined_at       TIMESTAMP DEFAULT NOW(),
    UNIQUE (project_id, user_id)
);

CREATE INDEX idx_pm_project ON project_members(project_id);
CREATE INDEX idx_pm_user ON project_members(user_id);
```

#### 3.2.4 `business_map_objects` — 业务地图节点（L1-L4）

```sql
CREATE TABLE business_map_objects (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    level               VARCHAR(2) NOT NULL,                  -- L1/L2/L3/L4
    name                VARCHAR(500) NOT NULL,                -- 节点名称
    parent_id           UUID REFERENCES business_map_objects(id) ON DELETE SET NULL,
    map_type            VARCHAR(20) NOT NULL DEFAULT 'hypothesis',  -- hypothesis/current
    verification_status VARCHAR(20) DEFAULT '未验证',          -- 未验证/成立/部分成立/推翻/待补充
    linked_hypothesis_id UUID REFERENCES business_map_objects(id) ON DELETE SET NULL,
    payload             JSONB NOT NULL DEFAULT '{}',          -- 层级差异化字段（见 3.3）
    review_status       VARCHAR(20) DEFAULT 'draft',          -- draft/pending_review/reviewed/rejected
    reviewed_by         INTEGER REFERENCES users(id),
    reviewed_at         TIMESTAMP,
    generated_by_ai     BOOLEAN DEFAULT TRUE,
    created_by          INTEGER NOT NULL REFERENCES users(id),
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW(),
    is_public           BOOLEAN DEFAULT FALSE,
    shared_with         INTEGER[] DEFAULT '{}',               -- 共享用户 ID 数组
    sensitivity         VARCHAR(20) DEFAULT 'internal'
);

CREATE INDEX idx_bmo_project ON business_map_objects(project_id);
CREATE INDEX idx_bmo_level ON business_map_objects(level);
CREATE INDEX idx_bmo_parent ON business_map_objects(parent_id);
CREATE INDEX idx_bmo_map_type ON business_map_objects(map_type);
CREATE INDEX idx_bmo_review ON business_map_objects(review_status);
-- GIN 索引用于 JSONB 查询
CREATE INDEX idx_bmo_payload ON business_map_objects USING GIN (payload);
```

#### 3.2.5 `pre_analyses` — 前置分析（项目级，一项一份）

```sql
CREATE TABLE pre_analyses (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    industry_value_chain    TEXT,       -- 行业价值链分析
    customer_position       TEXT,       -- 客户行业地位
    industry_trends         TEXT,       -- 行业趋势与变化
    strategic_positioning   TEXT,       -- 客户战略定位
    digitalization_drivers  TEXT,       -- 数字化驱动力
    created_by              INTEGER NOT NULL REFERENCES users(id),
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW()
);
```

#### 3.2.6 `stakeholder_cards` — 角色卡

```sql
CREATE TABLE stakeholder_cards (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name                VARCHAR(255) NOT NULL,                -- 角色姓名
    position            VARCHAR(255),                         -- 职位
    department          VARCHAR(255),                         -- 所属部门
    reports_to          VARCHAR(255),                         -- 汇报对象
    contact_info        VARCHAR(500),                         -- 联系方式
    role_type           VARCHAR(50) NOT NULL,                 -- 五类角色之一
    decision_power      VARCHAR(50),                          -- 决策权类型
    objective_layer     JSONB NOT NULL DEFAULT '{}',          -- 客观信息层（见 3.3）
    subjective_layer    JSONB NOT NULL DEFAULT '{}',          -- 主观信息层
    behaviors           JSONB DEFAULT '[]',                   -- 行为分析数组
    stance_change_log   JSONB DEFAULT '[]',                   -- 态度变化日志
    review_status       VARCHAR(20) DEFAULT 'draft',
    reviewed_by         INTEGER REFERENCES users(id),
    reviewed_at         TIMESTAMP,
    created_by          INTEGER NOT NULL REFERENCES users(id),
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW(),
    is_public           BOOLEAN DEFAULT FALSE,
    shared_with         INTEGER[] DEFAULT '{}',
    sensitivity         VARCHAR(20) DEFAULT 'internal'
);

CREATE INDEX idx_sc_project ON stakeholder_cards(project_id);
CREATE INDEX idx_sc_role_type ON stakeholder_cards(role_type);
CREATE INDEX idx_sc_name ON stakeholder_cards(name);
```

#### 3.2.7 `visit_records` — 拜访记录

```sql
CREATE TABLE visit_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    visit_date          DATE NOT NULL,
    visit_type          VARCHAR(50) NOT NULL DEFAULT '现场访谈',  -- 现场访谈/电话沟通/视频会议/邮件/一句话记录
    participants_our    VARCHAR(500)[] DEFAULT '{}',            -- 我方参与人
    participants_client UUID[] DEFAULT '{}',                    -- 客户方 StakeholderCard ID
    location            VARCHAR(500),                           -- 地点
    duration            VARCHAR(50),                            -- 时长，如"2小时"
    summary             TEXT,                                   -- 拜访摘要
    next_steps          TEXT,                                   -- 下一步行动
    key_takeaways       TEXT[] DEFAULT '{}',                    -- 关键收获
    evidence_count      INTEGER DEFAULT 0,                      -- 证据数（冗余缓存）
    verified_hypotheses INTEGER DEFAULT 0,                      -- 验证假设数（冗余缓存）
    review_status       VARCHAR(20) DEFAULT 'draft',
    reviewed_by         INTEGER REFERENCES users(id),
    reviewed_at         TIMESTAMP,
    created_by          INTEGER NOT NULL REFERENCES users(id),
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW(),
    is_public           BOOLEAN DEFAULT FALSE,
    shared_with         INTEGER[] DEFAULT '{}',
    sensitivity         VARCHAR(20) DEFAULT 'internal'
);

CREATE INDEX idx_vr_project ON visit_records(project_id);
CREATE INDEX idx_vr_date ON visit_records(visit_date DESC);
```

#### 3.2.8 `evidence_sources` — 证据条目

```sql
CREATE TABLE evidence_sources (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    visit_record_id         UUID NOT NULL REFERENCES visit_records(id) ON DELETE CASCADE,
    project_id              UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    evidence_type           VARCHAR(50) NOT NULL,              -- 客户原话/行为观察/角色态度信号/业务术语
    strength                VARCHAR(10) NOT NULL DEFAULT '中', -- 强/中/弱
    strength_note           VARCHAR(255),                      -- 强度说明
    content                 TEXT NOT NULL,                     -- 原始内容（引号体）
    source_role_id          UUID REFERENCES stakeholder_cards(id) ON DELETE SET NULL,
    source_role_name        VARCHAR(255),                      -- 冗余，便于展示
    related_hypothesis_id   UUID REFERENCES business_map_objects(id) ON DELETE SET NULL,
    related_hypothesis_name VARCHAR(500),
    review_status           VARCHAR(20) DEFAULT 'draft',
    reviewed_by             INTEGER REFERENCES users(id),
    reviewed_at             TIMESTAMP,
    created_by              INTEGER NOT NULL REFERENCES users(id),
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_es_visit ON evidence_sources(visit_record_id);
CREATE INDEX idx_es_project ON evidence_sources(project_id);
CREATE INDEX idx_es_type ON evidence_sources(evidence_type);
CREATE INDEX idx_es_strength ON evidence_sources(strength);
```

#### 3.2.9 `talk_scripts` — 话术

```sql
CREATE TABLE talk_scripts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stakeholder_card_id     UUID REFERENCES stakeholder_cards(id) ON DELETE SET NULL,  -- 空=通用模板
    role_type               VARCHAR(50) NOT NULL,              -- 五类角色之一
    scenario                VARCHAR(100) NOT NULL,             -- 场景
    content                 TEXT NOT NULL,                     -- Markdown 话术内容
    source_customer_quote   TEXT,                              -- 原始客户语录来源
    is_template             BOOLEAN DEFAULT FALSE,             -- 是否为通用模板
    created_by              INTEGER NOT NULL REFERENCES users(id),
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_ts_card ON talk_scripts(stakeholder_card_id);
CREATE INDEX idx_ts_role_type ON talk_scripts(role_type);
CREATE INDEX idx_ts_template ON talk_scripts(is_template);
```

#### 3.2.10 `intent_routing_logs` — 意图路由日志

```sql
CREATE TABLE intent_routing_logs (
    id                  SERIAL PRIMARY KEY,
    session_id          UUID NOT NULL,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    user_input          TEXT NOT NULL,                         -- 用户原始输入
    llm_classification  JSONB,                                 -- LLM 分类结果 {intent, confidence}
    keyword_hit         VARCHAR(50),                           -- 关键词命中
    user_confirmation   VARCHAR(50),                           -- 用户确认选择
    final_intent        VARCHAR(50) NOT NULL,                  -- 最终意图
    routed_to_skill     VARCHAR(100),                          -- 路由目标 Skill
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_irl_session ON intent_routing_logs(session_id);
CREATE INDEX idx_irl_created ON intent_routing_logs(created_at DESC);
```

### 3.3 JSONB 字段结构规范

#### BusinessMapObject.payload — 按层级差异化

**L1 节点 payload**：
```json
{
  "confidenceLevel": "高",
  "sourceType": "搜索采集",
  "sourceRef": ["uuid-material-1"],
  "evidenceIds": ["uuid-evidence-1"],
  "generatedByAI": true,
  "coreActivities": ["盆地评价", "圈闭评价", "井位部署"],
  "capabilityChain": ["地质研究", "地球物理勘探", "钻井评价"],
  "itSystems": [{"name": "GeoEast", "function": "地震解释系统"}],
  "organizations": [{"name": "勘探开发研究院", "role": "技术研究"}],
  "fiveDimHealth": {
    "L5_数字意识": {"score": 3, "desc": "战略分解与IT投资匹配度"},
    "L4_数字神经": {"score": 2, "desc": "跨环节流程效率"},
    "L3_数字器官": {"score": 4, "desc": "IT系统覆盖度"},
    "L2_数字血液": {"score": 3, "desc": "数据质量与共享"},
    "L1_数字骨架": {"score": 4, "desc": "基础设施弹性"}
  }
}
```

**L2 节点 payload**：
```json
{
  "confidenceLevel": "中",
  "sourceType": "行业模板",
  "sourceRef": [],
  "evidenceIds": [],
  "generatedByAI": true,
  "domainType": "业务域",
  "domainGoal": ["勘探成功率年度提升5%", "井位部署周期缩短20%"],
  "valueStream": "地质数据采集→综合研究→井位部署→钻探验证",
  "subScenarios": ["地质数据采集场景", "综合研究场景", "井位部署场景"],
  "coreCapabilities": [
    {"name": "盆地模拟能力", "detail": "独有性：自研盆地模拟算法"},
    {"name": "地震资料处理能力", "detail": "优势性：处理效率行业领先"}
  ],
  "supportITSystems": [
    {"name": "GeoEast", "modules": ["地震解释", "速度建模"]},
    {"name": "PetroMod", "modules": ["盆地模拟", "资源量估算"]}
  ],
  "keyOrganizations": [
    {"dept": "勘探开发研究院", "roles": ["高级地质师", "地球物理师"]}
  ],
  "keyDataEntities": [
    {"name": "地震数据体", "source": "野外采集", "usage": "构造解释"},
    {"name": "钻井数据", "source": "钻井系统", "usage": "井位论证"}
  ],
  "disconnectionPoints": [
    {"dimension": "业务×能力", "issue": "勘探成功率预测模型未接入实时数据"},
    {"dimension": "IT×组织", "issue": "GeoEast与PetroMod之间依赖人工导出数据"}
  ],
  "fiveDimHealth": {
    "L5_数字意识": {"score": 3, "desc": "域目标已分解但未到岗位级"},
    "L4_数字神经": {"score": 2, "desc": "跨系统数据流转靠人工"},
    "L3_数字器官": {"score": 4, "desc": "核心系统功能覆盖较全"},
    "L2_数字血液": {"score": 3, "desc": "部分数据实体存在多源不一致"},
    "L1_数字骨架": {"score": 4, "desc": "基础设施满足需求"}
  }
}
```

**L3 节点 payload**：
```json
{
  "confidenceLevel": "中",
  "sourceType": "用户上传",
  "sourceRef": ["uuid-material-3"],
  "evidenceIds": ["uuid-evidence-5"],
  "generatedByAI": true,
  "businessObjective": ["故障定位时间从30分钟缩短至5分钟"],
  "businessProcess": "接收报警→打开地图→点击设备查看详情→判断故障→导航→扫码确认",
  "keyActivities": [
    {"step": "接收报警", "activities": ["查看报警列表", "确认故障区域"]}
  ],
  "capabilityUnits": [
    {"activity": "打开地图", "unit": "GIS空间数据查询能力", "detail": "能够通过点击地图或输入编号快速定位设备"}
  ],
  "dataFlow": "SCADA报警→GIS地图→设备台账→维修记录→导航→确认",
  "positions": ["输电运维工程师", "调度员"],
  "supportSystems": [
    {"name": "电网一张图", "modules": ["地图展示", "设备查询", "导航"]}
  ],
  "painPoints": [
    {"desc": "数据回传延迟2-3天", "metric": "延迟天数", "current": "2-3天", "target": "<4小时"}
  ],
  "ontologyExtraction": {
    "entities": ["地震测线", "气枪阵列", "电缆", "原始数据", "质控报告"],
    "relations": ["测线→产生→原始数据", "质控员→审核→质控报告"],
    "rules": ["若信噪比<阈值，则标记为异常", "若异常连续3次，则触发告警"],
    "actions": ["踏勘设计", "参数调试", "激发采集", "异常标记"]
  },
  "aiOpportunity": {
    "name": "AI故障辅助研判",
    "function": "基于设备历史维修记录+实时报警，自动推荐故障原因Top3",
    "input": "设备ID+报警类型+最近7天维修记录",
    "output": "故障原因排序列表+置信度",
    "expectedEffect": "故障定位时间从30分钟缩短至5分钟",
    "technicalPath": "基于设备知识图谱+深度学习故障分类模型+LLM推理"
  },
  "fiveDimHealth": {
    "L5_数字意识": {"score": 2, "desc": "场景目标与域目标脱节"},
    "L4_数字神经": {"score": 2, "desc": "步骤间靠人工流转"},
    "L3_数字器官": {"score": 3, "desc": "系统功能基本可用但体验差"},
    "L2_数字血液": {"score": 2, "desc": "数据回传延迟严重"},
    "L1_数字骨架": {"score": 4, "desc": "资源充足"}
  }
}
```

**L4 节点 payload**：
```json
{
  "confidenceLevel": "高",
  "sourceType": "用户上传",
  "sourceRef": ["uuid-material-5"],
  "evidenceIds": [],
  "generatedByAI": false,
  "l3KeyActivity": "断层自动识别CNN推理",
  "capabilityUnitName": "深度学习断层识别模型训练能力",
  "capabilityType": "硬技能+工具操作",
  "capabilityDetail": "能够利用CNN/UNet架构训练地震断层自动识别模型，包括数据预处理、超参数调优、模型评估",
  "masteryLevel": "高级",
  "associatedPosition": "AI算法工程师（物探方向）",
  "currentRate": 35,
  "talentGap": "高级能力普遍不足。建议：①选拔10人参加'故障案例研讨工作坊'（2天）[培训]；②外部招聘1-2名电力数据分析师[招聘]"
}
```

#### StakeholderCard.subjective_layer — 主观层

```json
{
  "stance": "支持",
  "explicitKPI": "集团信息化考核达标；年度数字化项目预算执行率≥95%",
  "personalMotivation": "希望通过AI中台树立行业标杆，为晋升CIO积累政绩",
  "attitudeToUs": "认可技术路线，担心ROI难以量化",
  "attitudeToCompetitor": "认为华为云偏标准化产品，不够贴合油气场景",
  "engagement": 9,
  "influence": 9,
  "support": 8,
  "compositeScore": 8,
  "gradeLevel": "Champion",
  "confidence": "高",
  "coreConcerns": "数据安全合规、ROI量化、团队AI能力不足",
  "leverage": "引用国资委87号文、联合科技部张主任双线推动"
}
```

---

## 4. 多智能体协作机制

### 4.1 总体设计

本系统使用 Claude Agent SDK 的 subagent 功能实现多智能体协作。每个项目自动创建一个 Agent 实例，Main Agent 负责理解用户请求、规划执行、调用 subagent、审核结果、生成最终回复。

```
                        ┌──────────────────┐
                        │   用户消息输入     │
                        └────────┬─────────┘
                                 │
                        ┌────────┴─────────┐
                        │ consultant-router │  ← Plugin: 意图路由
                        │   (WF01 Hook)     │
                        └────────┬─────────┘
                                 │ 确定意图 → 路由到对应 Skill
                        ┌────────┴─────────┐
                        │   Main Agent      │
                        │ (Claude SDK)      │
                        │ 可用工具:          │
                        │  · Read/Write/... │
                        │  · web_search(MCP)│
                        └────────┬─────────┘
                                 │ Agent tool 调用
              ┌──────────────────┼──────────────────┐
              │                  │                  │
     ┌────────┴────────┐ ┌──────┴──────┐ ┌────────┴────────┐
     │ Subagent: 搜索   │ │Subagent:生成│ │Subagent: 审核   │
     │ (WF07 Step 1)   │ │(WF07 Step 2)│ │(WF10 验证)      │
     │ 工具: web_search│ │Skill: hypo  │ │Skill: verify    │
     │ (智谱 MCP)      │ │             │ │                 │
     └────────┬────────┘ └──────┬──────┘ └────────┬────────┘
              │                  │                  │
              └──────────────────┼──────────────────┘
                                 │
                        ┌────────┴─────────┐
                        │  PostOutputFilter │  ← Plugin: 防线2
                        │  (consultant-     │
                        │   defense Hook)   │
                        └────────┬─────────┘
                                 │
                        ┌────────┴─────────┐
                        │  SSE 事件流 →     │
                        │  前端 ChatStream  │
                        └──────────────────┘
```

### 4.2 角色与约束

| 角色 | 职责 | 约束 |
|------|------|------|
| **Main Agent** | 理解用户请求，规划执行步骤，调用 subagent，审核结果，生成最终回复 | 可使用 Agent tool 调用 subagent；需遵循道层 System Prompt |
| **Subagent (搜索)** | 调用智谱 MCP `web_search` 工具搜集公开信息 | 不能使用 Agent tool；不能调用其他 subagent |
| **Subagent (生成)** | 基于 Skill 的字段契约和搜索结果，生成结构化输出 | 不能使用 Agent tool；输出需符合 JSON Schema |
| **Subagent (审核)** | 对比假设 vs 证据，逐条验证，判定成立/推翻/部分成立 | 不能使用 Agent tool；需引用具体证据 ID |
| **Run Service** | 创建 Run，维护状态机 (pending→running→completed/failed/cancelled)，处理超时和重试 | 不直接执行模型推理 |
| **Agent Runtime Worker** | 加载会话/项目/Agent/Skill/权限配置，构造 Claude SDK options，注入 Skill 和文件清单，启动 SDK | 必须完成权限校验后才启动 SDK |

### 4.3 执行流程

```
1. 用户在 Conversation 中发送消息（自由文本或 WF chip 触发）
2. consultant-router Plugin Hook 拦截输入 → LLM 意图分类
   ├─ 路径 A（WF chip）：直接路由到对应 Skill
   └─ 路径 B（自然语言）：意图分类 → 关键词兜底 → 用户确认 → 路由
3. Run Service 创建 Run（状态: pending），投递到队列
4. Agent Runtime Worker 加载上下文：
   ├─ 项目信息（客户名、行业、阶段）
   ├─ Agent 配置（Skills、Plugins）
   ├─ 会话历史（最近 N 轮消息）
   ├─ 文件清单（conversation workspace inputs/）
   └─ 权限校验（用户是否有权使用该 Skill）
5. Worker 设置 Claude SDK cwd = conversation workspace
6. 注入道层 System Prompt（consultant-defense Hook）
7. Main Agent 根据用户消息推理，必要时调用 subagent
8. Worker 持续监听 streamed messages → SSE 推送到前端
9. 产出经 PostOutputFilter 过滤（consultant-defense Hook）
10. Main Agent 生成最终回复；产物写入 artifacts/
11. Run Service 将 Run 标记为 completed / failed / cancelled / timeout
12. 用户采纳 → 结构化数据写入正式表 → 对应数据页面可见
```

### 4.4 会话与项目的关系

```
User ──< Project ──< Session (Chat)
```

- 每个 Session 归属于一个 Project
- Session 创建时自动注入项目上下文（客户名、行业、阶段、已有资料摘要）
- 同一 Project 可以有多个 Session（按时间线排列）
- Session 中 AI 产出确认后写入 Project 级数据表
- 数据页面（业务地图/营销地图/拜访记录）展示的是 Project 下所有已确认数据的并集

---

## 5. Skill 与 Plugin 技术设计

### 5.1 Skill 目录结构

每个 Skill 遵循 Claude Code Skill 规范，存储为独立目录：

```
/data/agent-platform/skills/registry/
├── consultant-upload/              # WF02
│   ├── SKILL.md                    # Skill 定义（含 Prompt + Schema）
│   └── references/
│       └── material_types.json     # 7 种资料类型枚举
├── consultant-gap-check/           # WF03
│   └── SKILL.md
├── consultant-visit-plan/          # WF06
│   └── SKILL.md
├── consultant-hypothesis-map/      # WF07
│   ├── SKILL.md
│   └── references/
│       ├── l1_schema.json          # L1 字段契约
│       ├── l2_schema.json          # L2 字段契约
│       ├── l3_schema.json          # L3 字段契约
│       ├── l4_schema.json          # L4 字段契约
│       └── five_dim_health.json    # 五维健康评分标准
├── consultant-interview/           # WF09
│   └── SKILL.md
├── consultant-verify/              # WF10
│   └── SKILL.md
└── consultant-stakeholder/         # WF12
    ├── SKILL.md
    └── references/
        ├── role_types.json         # 五类角色定义
        └── scoring_formula.json    # 综合评分公式
```

### 5.2 SKILL.md 文件结构

每个 `SKILL.md` 包含以下章节：

```markdown
---
name: consultant-hypothesis-map
description: 假设地图分步生成（L1→L2→L3→L4），基于公开信息搜索+方法论模板
---

# 假设地图生成

## 道层引用
遵循 `dao_layer.md` 中的轻咨询伦理、保密义务、诚实汇报原则。

## 法层引用
- L1 字段契约：`references/l1_schema.json`
- L2 字段契约：`references/l2_schema.json`
- L3 字段契约：`references/l3_schema.json`
- L4 字段契约：`references/l4_schema.json`
- 五维健康评分标准：`references/five_dim_health.json`

## 执行流程（5 步强制）
### Step 1：搜索公开信息
调用智谱 MCP `web_search` 工具（`mcp__zhipu-web-search-sse__web_search`），搜索目标公司的公开信息。

### Step 2：生成 L1 价值链地图
基于搜索结果+行业模板，生成 L1 节点（5-7 个价值链环节）。

### Step 3：生成 L2 业务域地图
基于 L1 结果，向下拆解 L2 业务域/职能域/共性技术域。

### Step 4：生成 L3 细分场景 + 本体抽取
基于 L2 结果，识别关键场景，先抽取业务本体，再识别 AI 机会。

### Step 5：生成 L4 人才地图
基于 L3 关键活动，拆解能力单元，评估当前达标率，给出人才差距建议。

## 跨层一致性校验
- L2 子场景必须严格对应 L1 价值链环节
- L3 关键活动必须严格对应 L2 价值流步骤
- L4 能力单元必须严格对应 L3 关键活动
- L3 本体抽取的实体必须在 L2 关键数据实体中出现

## 结构化输出 Schema
```json
{
  "l1_nodes": [...],
  "l2_nodes": [...],
  "l3_nodes": [...],
  "l4_nodes": [...]
}
```
```

### 5.3 7 个 Skill 详细设计

| 编码 | 名称 | 类型 | 触发方式 | 输入 | 输出 | 依赖工具 |
|------|------|------|---------|------|------|---------|
| **WF02** | `consultant-upload` | 独立 Skill | 拖入/上传文件 | 文件路径 + 文件内容 | 分类结果 + 归档路径 | 无 |
| **WF03** | `consultant-gap-check` | 辅助 Skill | WF06/WF07 前置自动触发 | 项目已有资料摘要 | 覆盖度评分 + 缺口维度 + 建议搜索关键词 | 无 |
| **WF06** | `consultant-visit-plan` | 独立 Skill | WF chip / 自然语言 | 项目上下文 + 目标角色 | 拜访目标 + 沟通要点 + 访谈问题清单 + 资料清单 | 智谱 web_search(可选) |
| **WF07** | `consultant-hypothesis-map` | 独立 Skill | WF chip / 自然语言 | 项目上下文 + 客户名 | L1-L4 结构化地图数据（候选） | 智谱 web_search |
| **WF09** | `consultant-interview` | 独立 Skill | WF chip / 自然语言 | 纪要文本/文件 + 项目上下文 | VisitRecord + EvidenceSource 数组 | 无 |
| **WF10** | `consultant-verify` | 独立 Skill | WF chip / 自然语言 | 假设节点 + 证据列表 | 逐条验证结果 + 现状节点数据（候选） | 无 |
| **WF12** | `consultant-stakeholder` | 独立 Skill | WF chip / 自然语言 | 项目上下文 + 已有角色信息 | StakeholderCard 数组 + TalkScript 数组 | 智谱 web_search(可选) |

### 5.4 Plugin 详细设计

> **设计变更说明**：V2.0 初稿设计了 3 个 Plugin（router/search/defense），经代码审查确认，搜索能力实际上由智谱 MCP 作为**平台内置 MCP Server** 提供（`runner.py::_builtin_mcp_servers()`），不需要单独的 Plugin。因此最终为 **2 个 Plugin** + **1 个平台内置 MCP**。

#### Plugin 1：`consultant-router` — 意图路由

**目录结构**：
```
/data/agent-platform/plugins/registry/consultant-router/
├── plugin.json              # Plugin 元数据
├── hooks/
│   └── on_user_message.py   # Hook 脚本：拦截用户输入
├── prompts/
│   └── intent_classifier.md # 意图分类 Prompt
└── config/
    └── intents.json          # 7 类意图定义 + 关键词映射
```

**执行流程**：
```
用户输入到达 API
    ↓
Hook: on_user_message 拦截
    ↓
判断：是否为 WF chip 触发？
    ├─ 是 → 直接路由到对应 Skill，跳过分类
    └─ 否 → LLM 意图分类（使用 Flash 模型，cost 最低）
            ↓
        判断：置信度 ≥ 0.7？
            ├─ 是 → 直接路由
            └─ 否 → 关键词匹配
                    ↓
                判断：命中唯一意图？
                    ├─ 是 → 路由
                    └─ 否 → 返回意图选项给用户确认
                            ↓
                        用户选择 → 路由
    ↓
记录 IntentRoutingLog（每次必入）
    ↓
启动对应 Skill 执行
```

**intents.json 配置**：
```json
{
  "intents": [
    {
      "label": "hypothesis_map",
      "skill": "consultant-hypothesis-map",
      "keywords": ["假设地图", "业务地图", "L1", "L2", "L3", "L4", "业务拆解", "价值链"],
      "wf_chip": "生成假设地图"
    },
    {
      "label": "stakeholder_card",
      "skill": "consultant-stakeholder",
      "keywords": ["角色卡", "营销地图", "决策人", "组织架构", "权力地图"],
      "wf_chip": "营销地图（角色卡）"
    },
    {
      "label": "interview_summary",
      "skill": "consultant-interview",
      "keywords": ["会议纪要", "访谈整理", "拜访记录", "录音整理"],
      "wf_chip": "整理拜访纪要"
    },
    {
      "label": "visit_plan",
      "skill": "consultant-visit-plan",
      "keywords": ["拜访方案", "访谈提纲", "拜访准备", "沟通策略"],
      "wf_chip": "生成拜访前方案"
    },
    {
      "label": "current_map_verify",
      "skill": "consultant-verify",
      "keywords": ["验证假设", "是否成立", "现状流程", "证据验证"],
      "wf_chip": "验证假设 & 更新现状"
    },
    {
      "label": "file_upload",
      "skill": "consultant-upload",
      "keywords": [],
      "wf_chip": null,
      "trigger": "file_upload_event"
    },
    {
      "label": "chat",
      "skill": null,
      "keywords": [],
      "wf_chip": null,
      "mode": "chat"
    }
  ]
}
```

#### Plugin 2：`consultant-search` — 智谱 Web Search MCP

**实现方式**：本系统**不自行开发搜索工具**，而是直接复用智谱 AI 开放平台提供的 **Web Search MCP Server**（SSE 协议）。在 Agent Runtime Worker 启动时，由 `runner.py` 的 `_builtin_mcp_servers()` 将智谱 MCP 作为内置服务器注入 Claude Agent SDK。

**代码位置**：[`backend/app/integrations/claude/runner.py`](../backend/app/integrations/claude/runner.py)

**配置入口**（`.env`）：

```bash
# 智谱联网搜索 API Key（从 https://open.bigmodel.cn 获取）
ZHIPU_WEB_SEARCH_API_KEY=your-api-key-here
```

**内置 MCP Server 注册**（`runner.py:123-137`）：

```python
_ZHIPU_WEB_SEARCH_MCP_NAME = "zhipu-web-search-sse"

def _builtin_mcp_servers() -> dict[str, dict[str, str]]:
    """返回所有内置 MCP；未配置凭据时不启用，避免启动失败。"""
    api_key = core_config.get_settings().zhipu_web_search_api_key.strip()
    if not api_key:
        return {}  # 未配置 Key 则静默禁用，不影响其他功能
    encoded_key = quote(api_key, safe="")
    return {
        _ZHIPU_WEB_SEARCH_MCP_NAME: {
            "type": "sse",
            "url": (
                "https://open.bigmodel.cn/api/mcp/web_search/sse"
                f"?Authorization={encoded_key}"
            ),
        }
    }
```

**工具注册**（`runner.py:232-236`）：

```python
allowed_tools = [
    "Workflow", "Skill", "Read", "Write", "Edit",
    "MultiEdit", "Glob", "Grep", "Bash", "WebFetch"
]
if _ZHIPU_WEB_SEARCH_MCP_NAME in builtin_mcp_servers:
    # Claude MCP 工具名格式为 mcp__<server>__<tool>
    allowed_tools.append(f"mcp__{_ZHIPU_WEB_SEARCH_MCP_NAME}__web_search")
```

**架构图**：

```
.env (ZHIPU_WEB_SEARCH_API_KEY)
    ↓
config.py (Settings.zhipu_web_search_api_key)
    ↓
runner.py::_builtin_mcp_servers()
    ↓ 未配置 Key → 返回 {}（静默禁用）
    ↓ 已配置 Key → 返回 MCP Server 配置
    {
      "zhipu-web-search-sse": {
        "type": "sse",
        "url": "https://open.bigmodel.cn/api/mcp/web_search/sse?Authorization=xxx"
      }
    }
    ↓ 注入 ClaudeAgentOptions.mcp_servers
Claude Agent SDK
    ↓ 自动发现并注册工具
Claude Agent 可用工具列表:
    ├── Read, Write, Edit, Glob, Grep, Bash, WebFetch  （平台内置）
    └── mcp__zhipu-web-search-sse__web_search           （智谱 MCP）
    ↓ LLM 在需要搜索时自主调用
智谱开放平台 Web Search API
    ↓ 返回网页片段
Claude Agent 将搜索结果用于 Skill 执行
```

**搜索结果处理**：
1. 搜索结果由 Claude Agent 在 Skill 执行过程中直接消费（生成假设地图、角色卡等）
2. 有价值的搜索结果由 WF07/WF12 Skill 指导 Agent 存入 `materials` 表（materialType = `public_info`）
3. 同步归档到个人空间：`个人空间/<用户名>/<项目名>/资料/公开信息/`
4. 同一（公司名 + 关键词）组合去重，已搜过的不重复搜（增量搜索）

**设计优势**：

| 维度 | 自建搜索工具 | 智谱 MCP（✅ 采用） |
|------|------------|-------------------|
| 开发工作量 | 需对接多个搜索 API、处理限流、解析结果 | 零开发，配置 API Key 即用 |
| 维护成本 | 需持续跟进各 API 变更 | 智谱维护，平台只做集成 |
| 搜索质量 | 取决于自建管线质量 | 智谱自研搜索引擎，覆盖广 |
| 国内合规 | 需自行处理 | 智谱已通过合规审查 |
| Claude SDK 集成 | 需自行适配 MCP 协议 | 原生 SSE MCP，SDK 直接支持 |
| 容错 | 单点故障影响全局 | 未配置 Key 时静默禁用，不影响其他功能 |

**搜索范围**：智谱 web_search 覆盖全网公开网页，适合以下场景：
- WF07 生成假设地图：搜索目标公司的公开信息（官网、新闻报道、年报、行业分析）
- WF06 生成拜访方案：搜索目标行业的最新动态、政策变化
- WF12 生成角色卡：搜索 LinkedIn/脉脉等职业社交平台的公开信息

**暂不覆盖的能力**（通过其他方式补充）：
- 企业工商信息查询 → 用户在对话中手动上传企查查/天眼查导出文件，WF02 分类归档
- 网页全文抓取转 Markdown → 使用 SDK 内置的 `WebFetch` 工具（已在 allowed_tools 中）

#### Plugin 2：`consultant-defense` — 防线系统

**目录结构**：
```
/data/agent-platform/plugins/registry/consultant-defense/
├── plugin.json
├── hooks/
│   ├── inject_system_prompt.py  # 防线 1：Hook 注入道层 System Prompt
│   └── post_output_filter.py    # 防线 2：Hook 产出后过滤
├── rules/
│   ├── dao_layer.md             # 道层 System Prompt 全文
│   └── never_visible.json       # 确定性指纹匹配规则
```

**防线 1：道层 System Prompt 注入**

```python
# inject_system_prompt.py (伪代码)
async def on_session_init(session_context):
    dao_layer = load_file("rules/dao_layer.md")
    # 注入到 System Prompt 最前面，不可被 RAG 覆盖
    session_context.system_prompt = dao_layer + "\n\n" + session_context.system_prompt
    return session_context
```

**防线 2：PostOutputFilter**

```python
# post_output_filter.py (伪代码)
async def on_output_generated(output_text):
    fingerprints = load_json("rules/never_visible.json")
    for fp in fingerprints:
        # 确定性匹配，不依赖 LLM
        if fp["pattern"] in output_text:
            output_text = output_text.replace(fp["pattern"], fp["replacement"])
    return output_text
```

`never_visible.json` 示例：
```json
{
  "fingerprints": [
    {
      "pattern": "<internal_pricing>",
      "replacement": "[已移除内部信息]",
      "description": "内部定价信息"
    }
  ]
}
```

### 5.5 Agent 自动创建机制

用户创建项目时，系统自动：

```python
# projects/service.py (伪代码)
async def create_project_with_agent(db, project_data, user_id):
    # 1. 创建项目
    project = Project(**project_data, created_by=user_id)
    db.add(project)
    await db.flush()

    # 2. 自动创建 Agent 实例
    agent = Agent(
        name=f"{project.name} Agent",
        code=f"consultant_{project.id.hex[:8]}",
        system_prompt=generate_system_prompt(project),
        created_by=user_id
    )
    db.add(agent)
    await db.flush()

    # 3. 绑定 Skill 集合
    skill_codes = [
        "consultant-upload",
        "consultant-gap-check",
        "consultant-visit-plan",
        "consultant-hypothesis-map",
        "consultant-interview",
        "consultant-verify",
        "consultant-stakeholder"
    ]
    for code in skill_codes:
        db.add(SkillBinding(agent_id=agent.id, skill_code=code))

    # 4. 绑定 Plugin 集合（2 个 Plugin + 1 个平台内置 MCP）
    plugin_codes = ["consultant-router", "consultant-defense"]
    for code in plugin_codes:
        db.add(PluginBinding(agent_id=agent.id, plugin_code=code))
    # 注：搜索能力由平台内置智谱 MCP 提供（runner.py::_builtin_mcp_servers），
    # 非 Plugin 形式，配置 ZHIPU_WEB_SEARCH_API_KEY 即自动启用

    # 5. 关联 Agent 到项目
    project.agent_id = agent.id
    await db.commit()
    return project
```

---

## 6. 前端架构

### 6.1 组件树

```
<App>
├── <AuthGate>                          # 鉴权门：未登录 → LoginPage
│   ├── <Topbar>                        # 顶栏：项目选择器 + 用户信息
│   ├── <Sidebar>                       # 侧栏导航
│   │   ├── NavItem: 💬 对话
│   │   ├── NavItem: 🗺️ 业务地图
│   │   ├── NavItem: 🎯 营销地图
│   │   ├── NavItem: 📝 拜访记录
│   │   ├── Separator
│   │   ├── NavItem: 📁 个人空间
│   │   ├── NavItem: 👥 团队空间
│   │   ├── NavItem: 🤖 智能体管理
│   │   └── NavItem: ⚙️ 设置 (admin only)
│   └── <PageRouter>
│       ├── <ChatWorkspace>             # 对话页
│       │   ├── <SessionList>           #   左侧会话列表
│       │   ├── <ChatStream>            #   中间消息流
│       │   │   ├── <MessageBubble>     #     消息气泡
│       │   │   ├── <ThinkingPanel>     #     可折叠思考过程
│       │   │   ├── <CandidateCard>     #     AI 产出候选卡片
│       │   │   ├── <DiffView>          #     Chat 调整 diff 对比
│       │   │   └── <SourceEvidence>    #     来源证据
│       │   ├── <WFChips>               #   底部 WF chips
│       │   └── <ChatInput>             #   底部输入区
│       │
│       ├── <BusinessMapPage>           # 业务地图页
│       │   ├── <ProjectSwitcher>       #   顶部项目选择器
│       │   ├── <MapStats>              #   统计数据行
│       │   ├── <SubViewTabs>           #   假设/现状/偏差池/前置分析/五维健康
│       │   ├── <L1ValueChain>          #   L1 价值链横向展示
│       │   ├── <L2DomainTree>          #   L2 业务域树（含横向支撑域）
│       │   ├── <L3ScenarioTree>        #   L3 场景树
│       │   ├── <L4TalentTree>          #   L4 人才树
│       │   ├── <NodeDetailPanel>       #   右侧节点详情（按层级差异化）
│       │   │   ├── <OntologyCard>      #     L3 本体抽取卡片
│       │   │   ├── <FiveDimRadar>      #     五维健康雷达图
│       │   │   └── <EvidenceLinkList>  #     关联证据列表
│       │   └── <PreAnalysisView>       #   前置分析内容视图
│       │
│       ├── <MarketingMapPage>          # 营销地图页
│       │   ├── <ProjectSwitcher>
│       │   ├── <ViewTabs>              #   六视图切换
│       │   │   ├── <OrgChartView>      #     组织架构图
│       │   │   ├── <DecisionChainView> #     决策链角色表
│       │   │   ├── <StanceMatrixView>  #     角色-立场矩阵
│       │   │   ├── <TimelineView>      #     采购时间线
│       │   │   ├── <RoleCardView>      #     角色卡牌
│       │   │   └── <KnowledgeBaseView> #     知识库
│       │   ├── <StakeholderList>       #   左侧角色列表
│       │   ├── <RoleCardDetail>        #   中间角色卡详情
│       │   │   ├── <ObjectiveTab>      #     客观信息 Tab
│       │   │   ├── <SubjectiveTab>     #     主观分析 Tab
│       │   │   ├── <BehaviorTab>       #     行为分析 Tab
│       │   │   ├── <StanceHistoryTab>  #     态度历史 Tab
│       │   │   └── <TalkScriptTab>     #     话术库 Tab
│       │   └── <RelatedInfo>           #   右侧关联信息
│       │
│       ├── <VisitRecordsPage>          # 拜访记录页
│       │   ├── <ProjectSwitcher>
│       │   ├── <VisitTimeline>         #   拜访记录时间线
│       │   │   └── <VisitCard>         #     拜访记录卡片
│       │   └── <EvidenceFilterPanel>   #   证据筛选面板
│       │       └── <EvidenceItem>      #     证据条目
│       │
│       ├── <WorkspacePage>             # 个人空间（扩展）
│       │   ├── <ProjectFilter>         #   项目筛选下拉框
│       │   └── <FileTree>              #   按项目分组的文件树
│       │
│       └── <TeamSpacesPage>            # 团队空间（扩展）
│           ├── <PublicAssetsArea>      #   公开资产区
│           └── <MethodologyLibrary>    #   方法论库（只读）
```

### 6.2 路由设计

```typescript
// App.tsx 路由配置
const routes = [
  { path: "/",             element: <ChatWorkspace />,      label: "💬 对话" },
  { path: "/business-map", element: <BusinessMapPage />,    label: "🗺️ 业务地图" },
  { path: "/marketing-map",element: <MarketingMapPage />,   label: "🎯 营销地图" },
  { path: "/visit-records",element: <VisitRecordsPage />,   label: "📝 拜访记录" },
  { path: "/workspace",    element: <WorkspacePage />,      label: "📁 个人空间" },
  { path: "/team-spaces",  element: <TeamSpacesPage />,     label: "👥 团队空间" },
  { path: "/agents",       element: <AgentsPage />,         label: "🤖 智能体管理" },
  { path: "/admin/*",      element: <AdminRoutes />,        label: "⚙️ 设置" },
  { path: "/login",        element: <LoginPage />,          label: null },
];
```

### 6.3 状态管理

采用轻量级的 React Context + useReducer 方案：

```typescript
// 项目上下文（全局）
interface ProjectContext {
  currentProject: Project | null;
  projects: Project[];
  setCurrentProject: (project: Project) => void;
}

// 业务地图页面状态
interface BusinessMapState {
  projectId: string;
  activeSubView: 'hypothesis' | 'current' | 'deviation' | 'pre_analysis' | 'five_dim_health';
  selectedNode: BusinessMapObject | null;
  expandedNodes: Set<string>;       // 树节点展开状态
  editMode: boolean;
}

// 营销地图页面状态
interface MarketingMapState {
  projectId: string;
  activeView: 'org_chart' | 'decision_chain' | 'stance_matrix' | 'timeline' | 'role_card' | 'knowledge_base';
  selectedStakeholder: StakeholderCard | null;
  activeRoleTab: 'objective' | 'subjective' | 'behavior' | 'stance_history' | 'talk_script';
}

// 拜访记录页面状态
interface VisitRecordsState {
  projectId: string;
  filters: {
    evidenceType: string | null;
    strength: string | null;
    roleId: string | null;
  };
  expandedVisitId: string | null;
}
```

### 6.4 API 客户端

```typescript
// api/client.ts — 扩展

// === 客户 ===
getCustomers(): Promise<Customer[]>
createCustomer(data: CustomerInput): Promise<Customer>

// === 项目 ===
getProjects(customerId?: string): Promise<Project[]>
createProject(data: ProjectInput): Promise<Project>
getProjectMembers(projectId: string): Promise<ProjectMember[]>
inviteMember(projectId: string, userId: number, role: string): Promise<void>
removeMember(projectId: string, userId: number): Promise<void>

// === 业务地图 ===
getBusinessMapObjects(projectId: string, params: {
  level?: string;
  mapType?: string;
  parentId?: string;
}): Promise<BusinessMapObject[]>
createBusinessMapObject(data: BusinessMapObjectInput): Promise<BusinessMapObject>
updateBusinessMapObject(id: string, data: Partial<BusinessMapObjectInput>): Promise<BusinessMapObject>
deleteBusinessMapObject(id: string): Promise<void>
getPreAnalysis(projectId: string): Promise<PreAnalysis>

// === 营销地图 ===
getStakeholderCards(projectId: string): Promise<StakeholderCard[]>
createStakeholderCard(data: StakeholderCardInput): Promise<StakeholderCard>
updateStakeholderCard(id: string, data: Partial<StakeholderCardInput>): Promise<StakeholderCard>
deleteStakeholderCard(id: string): Promise<void>
getTalkScripts(params: { stakeholderCardId?: string; roleType?: string }): Promise<TalkScript[]>

// === 拜访记录 ===
getVisitRecords(projectId: string): Promise<VisitRecord[]>
createVisitRecord(data: VisitRecordInput): Promise<VisitRecord>
getEvidenceSources(projectId: string, filters: EvidenceFilter): Promise<EvidenceSource[]>

// === 公开/共享 ===
setObjectPublic(objectType: string, objectId: string, isPublic: boolean): Promise<void>
shareObject(objectType: string, objectId: string, userIds: number[]): Promise<void>
```

---

## 7. API 设计

### 7.1 RESTful 端点清单

所有新增 API 挂载在 `/api/` 前缀下，沿用现有 Session 认证中间件。

#### 7.1.1 客户 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| `GET` | `/api/customers` | 列表（支持搜索） | 登录用户 |
| `POST` | `/api/customers` | 创建客户 | 登录用户 |
| `GET` | `/api/customers/{id}` | 客户详情 | 登录用户 |
| `PUT` | `/api/customers/{id}` | 更新客户 | 创建者 / admin |
| `DELETE` | `/api/customers/{id}` | 删除客户 | 创建者 / admin |

#### 7.1.2 项目 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| `GET` | `/api/projects` | 列表（支持 customerId 筛选） | 登录用户（仅返回参与的项目） |
| `POST` | `/api/projects` | 创建项目（自动创建 Agent） | 登录用户 |
| `GET` | `/api/projects/{id}` | 项目详情 | 项目成员 |
| `PUT` | `/api/projects/{id}` | 更新项目 | Owner |
| `DELETE` | `/api/projects/{id}` | 删除项目 | Owner / admin |
| `GET` | `/api/projects/{id}/members` | 成员列表 | 项目成员 |
| `POST` | `/api/projects/{id}/members` | 邀请成员 | Owner |
| `DELETE` | `/api/projects/{id}/members/{userId}` | 移除成员 | Owner |

#### 7.1.3 业务地图 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| `GET` | `/api/projects/{id}/business-map` | 节点列表（支持 level/mapType/parentId 筛选） | 项目成员 |
| `POST` | `/api/projects/{id}/business-map` | 创建节点（手动新增） | 项目成员 |
| `GET` | `/api/projects/{id}/business-map/{nodeId}` | 节点详情 | 项目成员 |
| `PUT` | `/api/projects/{id}/business-map/{nodeId}` | 更新节点 | 项目成员 |
| `DELETE` | `/api/projects/{id}/business-map/{nodeId}` | 删除节点 | 项目成员 |
| `POST` | `/api/projects/{id}/business-map/batch` | 批量写入（AI 产出确认后） | 项目成员 |
| `GET` | `/api/projects/{id}/pre-analysis` | 获取前置分析 | 项目成员 |
| `PUT` | `/api/projects/{id}/pre-analysis` | 更新前置分析 | 项目成员 |

#### 7.1.4 营销地图 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| `GET` | `/api/projects/{id}/stakeholder-cards` | 角色卡列表 | 项目成员 |
| `POST` | `/api/projects/{id}/stakeholder-cards` | 创建角色卡 | 项目成员 |
| `GET` | `/api/projects/{id}/stakeholder-cards/{cardId}` | 角色卡详情 | 项目成员 |
| `PUT` | `/api/projects/{id}/stakeholder-cards/{cardId}` | 更新角色卡 | 项目成员 |
| `DELETE` | `/api/projects/{id}/stakeholder-cards/{cardId}` | 删除角色卡 | 项目成员 |
| `POST` | `/api/projects/{id}/stakeholder-cards/batch` | 批量写入（AI 产出确认后） | 项目成员 |
| `GET` | `/api/talk-scripts` | 话术列表（支持 cardId/roleType 筛选） | 登录用户 |
| `POST` | `/api/talk-scripts` | 创建话术 | 登录用户 |
| `PUT` | `/api/talk-scripts/{id}` | 更新话术 | 创建者 |
| `DELETE` | `/api/talk-scripts/{id}` | 删除话术 | 创建者 |

#### 7.1.5 拜访记录 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| `GET` | `/api/projects/{id}/visit-records` | 拜访记录列表（时间倒序） | 项目成员 |
| `POST` | `/api/projects/{id}/visit-records` | 创建拜访记录 | 项目成员 |
| `GET` | `/api/projects/{id}/visit-records/{recordId}` | 拜访记录详情（含证据列表） | 项目成员 |
| `PUT` | `/api/projects/{id}/visit-records/{recordId}` | 更新拜访记录 | 创建者 |
| `DELETE` | `/api/projects/{id}/visit-records/{recordId}` | 删除拜访记录 | 创建者 |
| `GET` | `/api/projects/{id}/evidence` | 证据列表（支持筛选） | 项目成员 |
| `POST` | `/api/projects/{id}/evidence` | 创建证据 | 项目成员 |
| `PUT` | `/api/projects/{id}/evidence/{evidenceId}` | 更新证据 | 创建者 |

#### 7.1.6 公开/共享 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| `PUT` | `/api/public/{objectType}/{objectId}` | 设置公开状态 | 对象拥有者 |
| `PUT` | `/api/share/{objectType}/{objectId}` | 设置共享用户 | 对象拥有者 |
| `GET` | `/api/team-space/public-assets` | 公开资产列表 | 登录用户 |

### 7.2 SSE 流式对话

复用现有 `/api/sessions/{id}/chat` SSE 端点，扩展事件类型：

```typescript
// SSE 事件类型
type SSEEvent =
  | { type: "message_start"; messageId: string }
  | { type: "content_block_delta"; delta: string }         // 流式文本
  | { type: "thinking_delta"; delta: string }               // 思考过程（折叠面板）
  | { type: "tool_call"; toolName: string; args: object }   // 工具调用开始
  | { type: "tool_result"; toolName: string; result: any }  // 工具调用结果
  | { type: "subagent_invoked"; agentName: string }         // Subagent 调用
  | { type: "subagent_completed"; agentName: string }       // Subagent 完成
  | { type: "candidate_ready"; candidate: CandidateResult } // 候选结果就绪
  | { type: "intent_routed"; intent: string; skill: string }// 意图路由结果
  | { type: "message_stop" }
  | { type: "error"; message: string }
  | { type: "run_status"; status: string }                  // Run 状态更新
```

### 7.3 WebSocket（预留）

后续版本可考虑 WebSocket 替代 SSE 以支持双向通信（如用户中途中断 AI 执行）。第一版使用 SSE + HTTP POST 组合（前端通过 POST 发送取消请求）。

---

## 8. 文件与 Workspace 规范

### 8.1 文件目录结构

沿用现有 V1.0 的目录结构设计，扩展项目级归档：

```
/data/agent-platform/
├── uploads/                         # 用户上传文件库（全局）
│   └── {user_id}/
│       └── {file_id}/
│           ├── original.ext
│           ├── metadata.json
│           └── extracted/           # MinerU 提取的 Markdown
│
├── workspaces/                      # 会话执行现场
│   └── {user_id}/
│       └── conversations/
│           └── {conversation_id}/
│               ├── .claude/skills/  # 当前会话授权 Skill
│               ├── inputs/          # 授权输入文件（只读）
│               ├── working/         # Agent 工作目录（读写）
│               ├── artifacts/       # 产物输出
│               └── logs/events.jsonl
│
└── personal_space/                  # 🆕 个人空间（项目归档）
    └── {user_id}/
        └── projects/
            └── {project_id}/
                ├── 资料/
                │   ├── 财报/
                │   ├── 访谈纪要/
                │   ├── 系统清单/
                │   ├── 公开信息/
                │   └── 待分类/
                ├── 方案/
                ├── 知识片段/
                └── 其他/
```

### 8.2 文件自动归档流程

```
对话中上传文件
    ↓
WF02 Skill 执行
    ├─ 解析文件（PDF/DOCX/Excel/Text → Markdown）
    ├─ 文本切片 + LLM 分类（7 种 materialType）
    └─ 评估覆盖度贡献（已有资料 vs 新资料）
    ↓
返回分类建议给用户
    ├─ 用户确认分类
    └─ 用户修改分类
    ↓
系统执行归档
    ├─ 原始文件 → uploads/{user_id}/{file_id}/
    ├─ 归档副本 → personal_space/{user_id}/projects/{project_id}/资料/{分类}/
    └─ Material 记录写入数据库
```

### 8.3 安全约束

- Agent cwd = `workspaces/{user_id}/conversations/{conversation_id}`
- Agent 只能访问 cwd 下的 inputs/、working/、artifacts/ 目录
- 禁止路径逃逸（`../`）、软链接逃逸、绝对路径越权
- 文件访问拦截在 `integrations/claude/guard.py` 中实现
- 所有文件操作记录 `file.accessed` 事件

---

## 9. 事件流与审计规范

### 9.1 事件类型

在 V1.0 事件类型基础上，新增业务事件：

| 事件类型 | 说明 | 新增/复用 |
|---------|------|----------|
| `run.created` / `run.started` / `run.completed` | Run 生命周期 | 复用 |
| `plan.created` | 主 Agent 生成计划 | 复用 |
| `subagent.invoked` / `subagent.completed` / `subagent.failed` | Subagent 调用 | 复用 |
| `tool.called` / `tool.completed` | 工具调用 | 复用 |
| `skill.injected` | Skill 注入版本和校验信息 | 复用 |
| `file.accessed` | 文件访问路径、操作、是否允许 | 复用 |
| `artifact.created` | 产物生成 | 复用 |
| `final.generated` | 最终回复生成 | 复用 |
| **`intent.routed`** | 意图路由结果（含分类依据） | 🆕 |
| **`candidate.generated`** | AI 候选结果生成 | 🆕 |
| **`candidate.adopted`** | 用户采纳候选结果 | 🆕 |
| **`candidate.rejected`** | 用户驳回候选结果 | 🆕 |
| **`object.created`** | 业务对象创建（BusinessMapObject 等） | 🆕 |
| **`object.updated`** | 业务对象更新 | 🆕 |
| **`object.deleted`** | 业务对象删除 | 🆕 |
| **`object.published`** | 业务对象公开/共享 | 🆕 |
| **`wf07.submitted`** | WF07 副手提交待审核 | 🆕 |
| **`wf07.approved`** | WF07 Owner 审核通过 | 🆕 |
| **`wf07.rejected`** | WF07 Owner 驳回 | 🆕 |

### 9.2 事件存储

- 事件主数据写入数据库 `agent_events` 表（PostgreSQL）
- 文件日志作为补充：`workspaces/{user_id}/conversations/{conversation_id}/logs/events.jsonl`
- 事件查询通过 API：`GET /api/sessions/{id}/events?type=&from=&to=`

### 9.3 审计日志

管理员操作必须写入审计日志（`audit_logs` 表）：

| 操作 | 记录内容 |
|------|---------|
| 管理用户账号 | 操作人、目标用户、操作类型（创建/禁用/删除）、时间 |
| 修改触发词配置 | 操作人、修改前后内容、时间 |
| 管理种子数据 | 操作人、文件路径、操作类型、时间 |
| 查看系统使用统计 | 访问人、访问时间、查询参数 |

---

## 10. 安全与权限边界

### 10.1 认证体系

- 复用现有企业微信扫码/SSO 登录
- Session 基于 Cookie（`SessionMiddleware`）
- `current_user` 从 `request.session["user_id"]` 读取

### 10.2 三层权限实现

```python
# deps.py (扩展)

async def get_project_member(project_id: UUID, user: User = Depends(current_user), db = Depends(get_db)):
    """验证用户是否为项目成员，返回 ProjectMember 记录"""
    member = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id
        )
    )
    member = member.scalar_one_or_none()
    if not member and user.role != "admin":
        raise HTTPException(status_code=403, detail="非项目成员无权访问")
    return member

async def require_project_owner(project_id: UUID, user: User = Depends(current_user), db = Depends(get_db)):
    """验证用户是否为项目 Owner"""
    member = await get_project_member(project_id, user, db)
    if member and member.role != "owner" and user.role != "admin":
        raise HTTPException(status_code=403, detail="仅项目 Owner 可执行此操作")
    return member

async def require_admin(user: User = Depends(current_user)):
    """验证用户是否为系统管理员"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可执行此操作")
    return user
```

### 10.3 数据隔离规则

| 数据 | 读取权限 | 写入权限 |
|------|---------|---------|
| Customer 基本信息 | 项目成员（同一客户下的项目共享） | 创建者 / admin |
| Project 数据 | 项目成员（Owner + Deputy） | Owner（设置）/ 项目成员（业务数据） |
| BusinessMapObject | 项目成员 | 项目成员 |
| StakeholderCard | 项目成员 | 项目成员 |
| VisitRecord | 项目成员 | 创建者 / Owner |
| EvidenceSource | 项目成员 | 创建者 |
| TalkScript | 项目成员（关联角色卡的）/ 全部用户（isTemplate=true） | 创建者 |
| 个人空间文件 | 用户本人 | 用户本人 |
| 团队空间公开资产 | 所有登录用户 | 对象拥有者（设置公开） |
| 团队空间方法论库 | 所有登录用户（只读） | admin |

### 10.4 WF07 审核流程

```python
# WF07 审核状态机
# draft → pending_review → reviewed (published)
#                        → rejected → draft (修改后重新提交)

async def submit_wf07_for_review(node_ids: list[UUID], user: User, db):
    """副手提交 WF07 产出审核"""
    for node_id in node_ids:
        node = await db.get(BusinessMapObject, node_id)
        if node.review_status == "reviewed":
            continue  # 已发布的不重复提交
        node.review_status = "pending_review"
    # 通知 Owner（Banner 提醒）
    await notify_owner(node.project_id, "WF07 待审核")

async def approve_wf07(node_ids: list[UUID], user: User, db):
    """Owner 审核通过"""
    member = await require_project_owner(project_id, user, db)
    for node_id in node_ids:
        node = await db.get(BusinessMapObject, node_id)
        node.review_status = "reviewed"
        node.reviewed_by = user.id
        node.reviewed_at = utcnow()
    # 记录 wf07.approved 事件

async def reject_wf07(node_ids: list[UUID], reason: str, user: User, db):
    """Owner 驳回"""
    member = await require_project_owner(project_id, user, db)
    for node_id in node_ids:
        node = await db.get(BusinessMapObject, node_id)
        node.review_status = "rejected"
        # 保留快照版本
    # 记录 wf07.rejected 事件
```

### 10.5 运行时安全约束

- Agent Runtime Worker 启动前必须校验：
  - 用户是否有权访问该 Session
  - 用户是否有权使用该 Agent
  - 用户是否有权使用本次请求涉及的 Skill
  - 用户是否有权读取本次请求涉及的文件
- Claude SDK cwd 严格限定为当前 conversation workspace
- `guard.py` 拦截所有文件路径访问，校验是否在 cwd 内
- Subagent 不能使用 Agent tool（SDK 配置限制）
- Plugin Hook 执行在沙箱环境中（受限的 Python 执行环境）

---

## 11. LLM 技术能力

### 11.1 模型路由

| 场景 | 模型 | 原因 |
|------|------|------|
| 意图分类（WF01） | `deepseek-v4-flash` | 简单分类任务，低延迟，低成本 |
| 核心 Skill 执行（WF06/07/09/10/12） | `deepseek-v4-pro` + thinking | 复杂推理 + 结构化输出，需要深度思考 |
| 文件分类（WF02） | `deepseek-v4-flash` | 文本分类，不复杂 |
| 缺口识别（WF03） | `deepseek-v4-pro` | 需要推理覆盖度 |
| Chat Mode（自由对话） | `deepseek-v4-pro` | 通用对话需要质量 |
| 工具调用（智谱 web_search 等） | 跟随主任务模型 | 保持一致性 |

### 11.2 深度思考 (Thinking)

- DeepSeek `enable_thinking` 参数已就绪
- `reasoning_content` 在 SSE 事件中以 `thinking_delta` 类型推送
- 前端渲染为灰色背景折叠面板（左侧竖线标记，默认折叠，点击展开 Markdown 渲染）
- 思维链不走 PostOutputFilter（防线 2）

### 11.3 公开信息搜索（智谱 Web Search MCP）

**架构**：系统的搜索能力由智谱 AI 开放平台的 **Web Search MCP Server** 提供，作为平台内置 MCP 在 Agent Runtime Worker 启动时注入 Claude Agent SDK。

**代码位置**：[`backend/app/integrations/claude/runner.py`](../backend/app/integrations/claude/runner.py)

**配置**：`.env` 中设置 `ZHIPU_WEB_SEARCH_API_KEY`（从 [open.bigmodel.cn](https://open.bigmodel.cn) 获取）

**启用逻辑**：
- ✅ 已配置 Key → MCP Server 自动注入 → Claude Agent 可用 `mcp__zhipu-web-search-sse__web_search` 工具
- ✅ 未配置 Key → 静默禁用（返回空 `{}`），不影响其他功能

**Skill 调用**：
- WF07 生成假设地图：Agent 自主调用 `web_search` 搜索目标公司公开信息（官网、年报、新闻报道、行业分析）
- WF06 生成拜访方案：可选搜索目标行业最新动态、政策变化
- WF12 生成角色卡：可选搜索公开的职业背景信息
- `WebFetch` 工具（SDK 内置）：用于抓取特定网页全文并转 Markdown

**搜索结果处理**：
1. 搜索结果由 Agent 在 Skill 执行过程中直接消费
2. 有价值的搜索结果由 Skill 指导 Agent 存入 `materials` 表（materialType = `public_info`）
3. 同步归档到个人空间：`个人空间/<用户名>/<项目名>/资料/公开信息/`
4. 同一（公司名 + 关键词）组合去重（增量搜索）

**容错设计**：未配置 Key 时静默降级，不影响其他功能正常使用

### 11.4 结构化输出

所有 Skill 使用 JSON Schema 约束 LLM 输出格式，确保解析可靠性：

```python
# wrapper.py (扩展)
async def structured_completion(
    messages: list[dict],
    output_schema: dict,      # JSON Schema
    enable_thinking: bool = True,
    model: str = "deepseek-v4-pro"
) -> dict:
    """结构化输出：LLM 输出必须符合 JSON Schema"""
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object", "schema": output_schema},
        extra_body={"enable_thinking": enable_thinking}
    )
    return json.loads(response.choices[0].message.content)
```

---

## 12. 实施阶段

### 12.1 Phase 1：地基（2-3 周）

**目标**：建立业务数据模型 + 导航骨架 + 权限中间件

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 数据库迁移 | 创建 8 张新表（Customer/Project/ProjectMember/BusinessMapObject/PreAnalysis/StakeholderCard/VisitRecord/EvidenceSource/TalkScript/IntentRoutingLog） | P0 |
| Customer CRUD | API + 前端页面（管理客户基本信息） | P0 |
| Project CRUD | API + 创建项目自动生成 Agent | P0 |
| ProjectMember 管理 | 邀请/移除成员 API | P0 |
| 权限中间件 | `get_project_member`、`require_project_owner`、数据隔离 | P0 |
| 导航重构 | Sidebar 扩展（对话/业务地图/营销地图/拜访记录/个人空间/团队空间） | P0 |
| 前端路由 | React Router 添加新页面路由 | P0 |
| 项目选择器 | `<ProjectSwitcher>` 公共组件 | P0 |

**交付物**：
- 用户可以创建客户 → 创建项目
- 项目自动创建 Agent 实例
- 导航可切换到各页面（页面内容为空壳）
- 权限中间件正常工作

### 12.2 Phase 2：核心 Skill（2-3 周）

**目标**：7 个 Skill 可用，2 个 Plugin 就绪 + 智谱 MCP 搜索集成，对话页核心流程跑通

| 任务 | 说明 | 优先级 |
|------|------|--------|
| SKILL.md 编写 | 7 个 Skill 的 Prompt 模板 + JSON Schema + 字段契约引用 | P0 |
| consultant-router | 意图路由 Hook + LLM 分类 + 关键词兜底 + IntentRoutingLog | P0 |
| 智谱 MCP 搜索集成 | `.env` 配置 `ZHIPU_WEB_SEARCH_API_KEY` → 验证 `_builtin_mcp_servers()` 注入 → 确认 Claude Agent 可调用 `web_search` 工具 | P0 |
| consultant-defense | 道层 System Prompt 注入 Hook + PostOutputFilter | P1 |
| 深度思考前端 | `thinking_delta` SSE 事件 → 折叠面板渲染 | P0 |
| WF07 Web Search 联调 | WF07 Skill 中指导 Agent 调用 `web_search` → 验证搜索结果格式 → 搜索结果归档 | P0 |
| Chat 页 WF chips | 5 个 WF chip 按钮 + 文件拖入区 | P0 |
| 候选区机制 | AI 产出 → 候选卡片 → 采纳/驳回/Chat 调整 → 正式入库 | P0 |

**交付物**：
- 用户可以在对话中通过 WF chip 触发任意 Skill
- AI 产出以候选卡片展示
- 用户可采纳/驳回/Chat 调整候选结果
- 意图路由日志完整记录
- 深度思考面板可展开

### 12.3 Phase 3：数据页面（2-3 周）

**目标**：业务地图/营销地图/拜访记录页面完整可用

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 业务地图页面 | L1-L4 树形展示 + 假设/现状子视图 + 偏差池子视图 + 前置分析 + 五维健康 → 基于现有原型代码重构 | P0 |
| 营销地图页面 | 六视图 + 角色卡详情（5 Tab）+ 知识库视图 → 基于现有原型代码重构 | P0 |
| 拜访记录页面 | 时间线 + 证据筛选面板 + 拜访卡片展开 | P0 |
| 业务地图 CRUD API | 节点增删改查 + 批量写入 | P0 |
| 营销地图 CRUD API | 角色卡 + 话术增删改查 | P0 |
| 拜访记录 CRUD API | 拜访记录 + 证据增删改查 | P0 |
| 节点详情面板 | 按 L1-L4 层级差异化展示字段 + 本体抽取卡片 + 五维健康雷达图 | P0 |

**交付物**：
- 三个数据页面完整可用
- AI 在对话中产出的数据确认后可在对应页面看到
- 用户可手动新增/编辑/删除数据

### 12.4 Phase 4：知识归档（1-2 周）

**目标**：个人空间项目筛选 + 自动归档 + 团队空间公开资产区

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 个人空间项目筛选 | 顶部下拉框切换项目过滤文件 | P0 |
| 自动归档机制 | WF02 文件分类 → 确认 → 归档到个人空间 | P0 |
| 对象公开/共享 | `isPublic` + `sharedWith` API + 前端操作 | P1 |
| 团队空间公开资产区 | 按类型聚合展示公开对象 | P1 |
| "标记为有价值" | Chat Mode 消息 → 存为知识片段 | P2 |
| 方法论库展示 | 管理员维护的方法论文档只读展示 | P2 |

**交付物**：
- 上传文件自动归档到个人空间对应项目目录
- 公开对象可在团队空间看到
- 知识片段可沉淀

### 12.5 Phase 5：打磨（1-2 周）

**目标**：审核流程 + 角色去重 + 态度追踪 + 统计

| 任务 | 说明 | 优先级 |
|------|------|--------|
| WF07 审核流程 | 副手提交 → Owner 审核 → 发布/驳回 + 版本快照 | P1 |
| 角色去重 | `person_disambiguation`：AI 检测重名/相似角色 → 用户确认 | P1 |
| 态度变化追踪 | StakeholderCard stanceChangeLog 可视化时间线 | P2 |
| 使用统计 | admin 可查看 Skill 使用次数/Run 成功率/用户活跃度 | P2 |
| 错误处理完善 | Run 超时/取消/失败的重试和恢复机制 | P1 |
| 性能优化 | 大数据量下的分页/虚拟滚动/索引优化 | P2 |

**交付物**：
- WF07 审核流程完整
- 角色去重机制可用
- 系统稳定可内部使用

---

## 13. 验收标准

### 13.1 地基验收（Phase 1）

- [ ] 用户可以创建 Customer 和 Project
- [ ] 创建 Project 时自动生成 Agent 实例（绑定 7 Skills + 2 Plugins，搜索由平台内置智谱 MCP 提供）
- [ ] 用户可以邀请其他用户加入项目
- [ ] 非项目成员无法访问项目数据
- [ ] 导航栏显示所有一级页面入口
- [ ] 项目选择器可在各页面间切换项目上下文

### 13.2 核心 Skill 验收（Phase 2）

- [ ] 用户点击 WF chip "生成假设地图" → AI 执行 WF07 → 生成 L1-L4 结构化数据
- [ ] 用户拖入文件 → 触发 WF02 → AI 分类 → 用户确认分类
- [ ] AI 产出以候选卡片展示，包含可展开的思考过程
- [ ] 用户可采纳候选（数据写入正式表）或驳回（进偏差池）
- [ ] 用户可通过 Chat 自然语言调整候选结果
- [ ] 意图路由准确率 ≥ 80%（WF chip 触发 100% 准确）
- [ ] 防线 2 PostOutputFilter 可过滤 `never_visible` 内容

### 13.3 数据页面验收（Phase 3）

- [ ] 业务地图页面展示 L1→L2→L3→L4 树形结构
- [ ] 节点详情面板按层级展示差异化字段
- [ ] L3 节点展示本体抽取卡片（实体/关系/规则/动作 四要素）
- [ ] 五维健康雷达图可正常渲染
- [ ] 假设地图/现状地图/偏差池三个子视图可切换
- [ ] 营销地图六视图完整可用
- [ ] 角色卡五 Tab（客观/主观/行为/态度历史/话术）内容完整
- [ ] 综合评分自动计算并展示等级标签
- [ ] 拜访记录时间线按时间倒序展示
- [ ] 证据筛选面板可按类型/强度/角色筛选
- [ ] 数据页面支持手动新增/编辑/删除（无需经过 AI）

### 13.4 知识归档验收（Phase 4）

- [ ] 个人空间可按项目筛选文件
- [ ] 上传文件经 AI 分类后自动归档到对应项目目录
- [ ] 用户可在各数据页面将对象标记为"完全公开"
- [ ] 公开对象自动出现在团队空间公开资产区
- [ ] Chat Mode 中可"标记为有价值" → 生成知识片段

### 13.5 打磨验收（Phase 5）

- [ ] WF07 副手提交 → Owner 审核 → 通过/驳回流程完整
- [ ] 驳回的节点保留历史版本快照
- [ ] AI 检测到重名/相似角色时生成消歧候选
- [ ] 角色卡态度变化日志以时间线可视化
- [ ] Run 失败时可定位失败位置（main agent / subagent / tool / file）
- [ ] 管理员可查看 Skill 使用统计

---

## 附录 A：与 V1.0 的关系

本 V2.0 技术说明书是在 [V1.0 技术说明书](../Agent平台技术说明书.md) 基础上的应用层扩展，两者关系如下：

| 维度 | V1.0（通用 Agent 平台） | V2.0（AI 顾问作战台） |
|------|------------------------|----------------------|
| **定位** | 平台基础设施 | 面向轻咨询业务的应用系统 |
| **用户** | 平台管理员 + Agent 开发者 | 轻咨询部顾问 |
| **Agent 粒度** | 用户手动创建 Agent/Team | 项目创建时自动生成 Agent 实例 |
| **Skill** | 通用 Skill 注册/授权机制 | 7 个咨询专用 Skill（含字段契约 + 方法论） |
| **Plugin** | 通用 Plugin 管理 | 2 个咨询专用 Plugin（路由/防线）+ 平台内置智谱 MCP 搜索 |
| **数据模型** | User/Agent/Session/Category | +Customer/Project/BusinessMapObject/StakeholderCard/VisitRecord/EvidenceSource/TalkScript |
| **前端页面** | 对话/个人空间/团队空间/Agent 管理 | +业务地图/营销地图/拜访记录 |
| **权限模型** | 系统级（admin/user） | +项目级（Owner/Deputy）+ 跨项目隔离 |
| **文件存储** | uploads/ + workspaces/ | +personal_space/ 项目归档 |

V1.0 中的以下设计在 V2.0 中**保持不变**：
- Claude Agent SDK 的 main agent + subagent 协作机制
- Skill 目录规范和运行时注入方式
- Conversation workspace 的文件隔离规则
- SSE 流式对话的主体架构
- Claude SDK 的 `runner.py` / `serializers.py` / `guard.py` 封装

V2.0 **新增**的是：
- 业务数据模型和 API
- 咨询专用 Skill/Plugin 的 Prompt 和配置
- 前端业务页面（业务地图/营销地图/拜访记录）
- 三层权限模型的项目级和对象级实现
- 文件自动归档机制
- 候选区（Pending Area）的采纳/驳回/Chat 调整工作流

---

> **本文档是 AI 顾问作战台的权威技术实施方案。** 所有开发活动以本文档为基准。如与需求规格说明书不一致，以需求规格说明书为准（需求 > 技术）。
>
> **本文档不替代**：V1.0 技术说明书（平台基础设施仍参考 V1.0），方法论文档（L1-L4 设计文档、营销地图设计文档、道/法/术/器层种子数据文件），这些独立文档保持不变。
>
> **文档版本**：V2.0
> **上一版本**：V1.0（通用 Agent 平台技术说明书）
> **编写日期**：2026-07-06
>
> ### V2.0 更新内容
>
> V2.0 是一次全面重写，相比 V1.0 的变更包括：
>
> | 章节 | V1.0 内容 | V2.0 变更 |
> |------|----------|----------|
> | 1. 文档概述 | 通用 Agent 平台建设目标 | 重写为 AI 顾问作战台定位，明确与现有系统的复用/扩展关系 |
> | 2. 总体架构 | 控制面 + Claude 运行时 | 扩展为五层架构（前端→API→业务逻辑→AI运行→存储），新增项目目录结构 |
> | 3. 核心数据模型 | 4 个通用对象 | 扩展为 10 张新增表的完整 SQL DDL + JSONB 字段规范 + ER 图 |
> | 4. 多智能体机制 | 通用 subagent 协作 | 新增咨询场景执行流程、会话与项目关系 |
> | 5. Skill/Plugin | 通用 Skill 注册规范 | 新增 7 个 Skill 详细设计 + 2 个 Plugin 完整方案 + 智谱 MCP 搜索集成（含代码骨架） |
> | 6. 前端架构 | 无 | **全新章节**：组件树 + 路由设计 + 状态管理 + API 客户端 |
> | 7. API 设计 | 无 | **全新章节**：50+ RESTful 端点 + SSE 事件扩展 |
> | 8. 文件规范 | 通用 workspace | 扩展 personal_space 项目归档目录 + 自动归档流程 |
> | 9. 事件流 | 8 种通用事件 | 新增 10 种业务事件 + 审计日志表 |
> | 10. 安全权限 | 通用安全约束 | 扩展三层权限实现代码 + 数据隔离规则表 + WF07 审核状态机 |
> | 11. LLM 能力 | 无 | **全新章节**：模型路由策略 + 深度思考 + 结构化输出 |
> | 12. 实施阶段 | 4 阶段通用平台 | 重写为 5 阶段应用实施计划（地基→Skill→数据页面→归档→打磨） |
> | 13. 验收标准 | 8 条通用标准 | 扩展为 5 阶段分层验收清单（30+ 条目） |
> | 附录 A | 无 | **全新**：V1.0 与 V2.0 关系对照表 |
