# AI 顾问作战台 · 技术框架与健壮性说明

> 面向技术团队的综合技术说明:在智能体平台底座之上,**AI 顾问作战台**(`consultant-war-room`)是怎么设计的、技术框架怎么搭、健壮性怎么考虑。
>
> **文档版本**:V1.0
> **编写日期**:2026-07-06
> **依据材料**:[需求文档 V1.0](需求文档V1.0) · [需求规格说明书 V2.0](需求规格说明书V2.0.md) · [Agent 平台技术说明书 V2.0](Agent平台技术说明书V2.0.md) · [开发计划表 V1.0](开发计划表V1.0.md)
> **技术栈**:Python 3.13 · FastAPI · SQLAlchemy 2.0(async) · PostgreSQL · Redis · claude-agent-sdk · React 18 · TypeScript · Vite

---

## 目录

- [1. 文档概述](#1-文档概述)
- [2. 产品与技术全景](#2-产品与技术全景)
- [3. 核心数据模型](#3-核心数据模型)
- [4. AI 运行时与多智能体协作](#4-ai-运行时与多智能体协作)
- [5. 前端架构](#5-前端架构)
- [6. API 与流式对话](#6-api-与流式对话)
- [7. 权限与安全边界](#7-权限与安全边界)
- [8. 健壮性设计(核心)](#8-健壮性设计核心)
- [9. 实施路线与风险防控](#9-实施路线与风险防控)
- [10. 总结:技术亮点速查](#10-总结技术亮点速查)

---

## 1. 文档概述

### 1.1 为什么有这份文档

设计目录下已有四份材料,各自承担不同职责:

```
需求文档 V1.0  ──┐
                 │  业务背景、用户故事(已退役为参考)
需求规格 V2.0  ──┼─▶ 定义"做什么"(开发真源)
                 │
技术说明书 V2.0 ──┼─▶ 定义"怎么做"(详尽技术落地:DDL / SKILL.md / 端点)
                 │
开发计划 V1.0  ──┘  定义"怎么干"(43 张 Claude Coding 任务卡 + 工期 + 风险)
```

技术说明书 V2.0 是一份**详尽的技术落地方案**(含完整 DDL、SKILL.md 骨架、50+ 端点),适合"照着写代码"。但当需要**向技术团队整体介绍"这套系统的技术框架是什么样、健壮性怎么考虑"**时,直接甩 V2.0 的 DDL 细节并不合适——缺一个高层综合视角,也缺一个把"健壮性"系统讲清楚的专章。

本文档填补这个空缺:以四份材料为依据,**综合提炼**技术框架,并**专章阐述健壮性设计**。读完这份,技术团队能建立全局认知;需要落地细节时,再回到 V2.0 技术说明书和开发计划表。

### 1.2 适用读者与用法

- **新加入的后端 / 前端 / 算法工程师**:先读本文档建立全局观,再按开发计划表领任务卡。
- **架构 / 技术评审**:重点读第 8 章(健壮性)和第 9 章(风险防控),作为评审清单。
- **对外技术介绍 / 立项汇报**:第 2、10 章可直接作为宣讲素材。

### 1.3 与其它技术文档的边界

| 文档 | 定位 | 本文与其关系 |
|------|------|------------|
| 技术说明书 V2.0 | 详尽落地(DDL/SKILL/端点) | 本文档是它的"高层综合 + 健壮性专章";DDL 细节以 V2.0 为准 |
| 开发计划表 V1.0 | 任务卡拆解 + 工期 + 风险 | 本文档第 9 章综合其风险登记册与里程碑 |
| 平台底座技术框架与健壮性说明 | 基于**实际代码**的底座自检 | 那份讲"已落地底座代码现状";本文档讲"作战台应用的整体设计与健壮性",两者互补 |

---

## 2. 产品与技术全景

### 2.1 产品定位

**AI 顾问作战台**是建在智能体平台底座(`agent-platform-main`)之上的轻咨询业务应用,让顾问在一个平台里完成"假设地图 → 拜访方案 → 现场验证 → 现状地图 → 营销地图 → 知识沉淀"的全流程闭环。

最小闭环(需求规格 1.5):

```
注册/登录 → 创建客户 → 创建项目 → 对话中上传资料
     ↓
WF07 生成假设地图 L1→L2→L3→L4(基于公开信息搜索)
     ↓
WF06 生成拜访前方案 → 去客户现场
     ↓
WF09 回填拜访纪要 → WF10 验证假设 & 更新现状
     ↓
WF12 生成/更新营销地图(角色卡)
     ↓
复盘 → 知识沉淀 → 下一轮
```

### 2.2 四条贯穿全系统的设计原则

需求规格 1.6 确立的原则,决定了后续所有技术决策:

1. **对话是唯一的 AI 交互入口** —— 所有工作流在对话中触发、产出、确认;数据页面只做展示与增删改查,不承担 AI 交互。
2. **业务地图 / 营销地图 / 拜访记录为独立一级页面** —— 各自带项目选择器,单一数据源。
3. **所有 AI 产出支持 Chat 调整** —— 产出 → 对话修改 → 再产出 → 直到采纳或驳回。
4. **假设地图永久存档** —— 现状地图独立新建并关联回假设,复盘期可对比。
5. **项目内全透明,项目外全隔离** —— 被邀请进项目即可见全部数据,跨项目默认不可见。

> 这五条原则是健壮性设计的"宪法":候选区机制、单一真源、版本快照、权限隔离,全部源于此。

### 2.3 技术栈总览

| 层级 | 选型 | 在本系统中的角色 |
|------|------|---------------|
| 后端框架 | FastAPI(async) | API 层 + 依赖注入 + 自动 OpenAPI |
| ORM | SQLAlchemy 2.0(async) | DeclarativeBase + 异步 session |
| 数据库 | PostgreSQL 16 | 主数据;**JSONB** 承载 L1-L4 分层 payload |
| 缓存/锁 | Redis 7 | 团队空间文件锁 |
| AI SDK | claude-agent-sdk | 封装 Claude Code 的对话/工具/Skill/Plugin 能力 |
| LLM | DeepSeek V4 Pro/Flash(双档) | Pro 跑复杂推理,Flash 跑意图分类/文件分类 |
| 文档转换 | MinerU | Office/PDF → Markdown |
| 搜索 | 智谱 Web Search MCP | 平台内置 MCP,WF07/WF12 公开信息搜索 |
| 前端 | React 18 + TypeScript | SPA |
| 构建 | Vite | HMR + 生产构建 |
| 状态 | React Context + useReducer | 轻量,无外部状态库 |
| HTTP/流 | Fetch + SSE(EventSource) | 流式对话 |
| 部署 | Docker Compose | postgres + redis + backend 三容器 |

**两个关键技术选型理由**:

- **claude-agent-sdk 而非裸 LLM 调用**:本系统的 7 个工作流本质是"带工具、带 Skill、带文件读写的 Agent 任务",Claude Code 形态的 SDK 天然适配(Read/Write/Edit/Bash/WebFetch + Skill + Plugin Hook + Subagent),不必自研 Agent 编排框架。
- **DeepSeek 双档路由 + 智谱 MCP 搜索**:意图分类、文件分类用 Flash(低成本低延迟);WF07/WF10/WF12 等复杂推理用 Pro + thinking。搜索复用智谱已合规的 MCP,零自研。

### 2.4 总体架构(五层)

```
┌─────────────────────────────────────────────────────────────┐
│        前端 (React 18 + TS + Vite)                            │
│   对话页 · 业务地图 · 营销地图 · 拜访记录 · 个人空间 · 团队空间  │
│                  API Client (REST + SSE)                      │
└──────────────────────────┬────────────────────────────────────┘
                           │ HTTP/SSE (Cookie Session)
┌──────────────────────────┴────────────────────────────────────┐
│   API 层 (FastAPI)  ── 薄路由 + auth_guard 全局守卫             │
│   customers / projects / business-map / marketing-map /        │
│   visit-records / sessions / workspace / public-share ...      │
└──────────────────────────┬────────────────────────────────────┘
                           │
┌──────────────────────────┴────────────────────────────────────┐
│   业务逻辑层 (modules/)                                        │
│   customers / projects / business_maps / marketing_maps /      │
│   visits / evidence / skill_router / defense / archive ...     │
└──────────────┬─────────────────────────┬──────────────────────┘
               │                         │
┌──────────────┴────────────┐  ┌─────────┴─────────────────────┐
│  AI 运行层                  │  │  存储层                        │
│  integrations/claude/       │  │  PostgreSQL(业务数据+JSONB)   │
│   runner / serializers      │  │  Redis(团队空间文件锁)         │
│   guard / tool_approval     │  │  本地文件系统                  │
│  + 7 Skill / 2 Plugin /     │  │   (uploads / workspaces /      │
│    智谱 MCP                 │  │    personal_space)             │
└────────────────────────────┘  └───────────────────────────────┘
```

依赖方向严格单向:`api → modules → models/db`,`integrations` 独立。路由层保持"薄",业务逻辑集中在 modules,可独立测试。

### 2.5 与平台底座的关系:复用而非重造

本应用**复用** `agent-platform-main` 已有基础设施,只做**扩展**,不做破坏性修改:

| 复用项 | 复用方式 | 扩展点 |
|--------|---------|--------|
| User + Session 认证(企微扫码/SSO) | 直接复用 | 无 |
| Agent + 工作目录隔离 | 扩展 | **创建项目时自动生成 Agent 实例**,绑定 Skill/Plugin |
| ChatSession + SSE 流式对话 | 直接复用 | 注入项目上下文 + 扩展 SSE 事件类型 |
| Skills/Plugins 上传与管理 | 直接复用 | 新增 7 Skill + 2 Plugin |
| 智谱 Web Search MCP | 直接复用 | 平台内置,配 Key 即用 |
| 个人空间/团队空间文件系统 | 扩展 | 项目筛选 + 自动归档 + 公开资产区 |
| DB + 幂等迁移机制 | 直接复用 | 新增 10 张业务表 |

---

## 3. 核心数据模型

### 3.1 设计哲学:结构化 + JSONB 分层

本系统的数据模型有一条贯穿始终的设计哲学:

> **稳定的结构化字段用列,易变的多层结构用 JSONB。**

典型体现是 `business_map_objects`(业务地图节点)。L1-L4 四个层级的字段差异极大(L1 是 5 要素价值链,L3 是 11 要素含本体抽取),如果每个层级都建独立表,模型会爆炸。因此:

- **公共字段**(projectId / level / parentId / mapType / verificationStatus / reviewStatus 等)用列,便于 SQL 索引和筛选;
- **层级差异化字段**(L1 的 coreActivities、L3 的 ontologyExtraction、L4 的 talentGap 等)放进 `payload JSONB`,并建 **GIN 索引**支持 JSONB 查询。

这样一张表承载四层结构,新增层级或字段无需 DDL 变更,只改 Skill 的 Schema 引用。

### 3.2 ER 概要

```
User ──< ProjectMember(role) >── Project ──< Customer
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            │                          │                          │
         Agent                    BusinessMapObject          StakeholderCard
       (自动创建)                 (L1-L4 · hypothesis/current)     │
                                       │                          │
                                  PreAnalysis                TalkScript
                                  (项目级一份)                      │
                                       │
                                  EvidenceSource ──< VisitRecord
                                       │
                                  IntentRoutingLog
```

### 3.3 新增的 10 张表(对应开发计划 CC-02)

| 表 | 对应实体 | 关键设计 |
|----|---------|---------|
| `customers` | 客户 | orgStructure 用 JSONB;同一客户跨项目共享基本信息 |
| `projects` | 项目 | 关联自动创建的 agent_id;fde_stage 表征项目阶段 |
| `project_members` | 成员 | UNIQUE(project, user);role = owner/deputy |
| `business_map_objects` | 业务地图节点 | **核心表**,payload JSONB + GIN;review_status 审核状态机 |
| `pre_analyses` | 前置分析 | 项目级 UNIQUE,一份;5 维度战略分析 |
| `stakeholder_cards` | 角色卡 | objective_layer/subjective_layer 双 JSONB;behaviors + stance_change_log |
| `visit_records` | 拜访记录 | evidence_count/verified_hypotheses 冗余缓存 |
| `evidence_sources` | 证据 | evidence_type + strength;关联假设节点与角色卡 |
| `talk_scripts` | 话术 | stakeholder_card_id 可空(通用模板);role_type × scenario |
| `intent_routing_logs` | 意图路由日志 | 每次 WF01 决策必入,含 LLM 结果/关键词/确认/最终意图 |

> 完整 DDL 见技术说明书 V2.0 第 3.2 节。

### 3.4 JSONB 分层 payload(BusinessMapObject 的核心)

`payload` 按 level 差异化,严格对齐 L1-L4 设计文档:

| 层级 | 要素数 | 核心字段 |
|------|-------|---------|
| **L1** 公司级价值链 | 5 + 五维健康 | coreActivities / capabilityChain / itSystems / organization / fiveDimHealth |
| **L2** 业务域/职能域/共性技术域 | 8 + 五维健康 | domainType / domainGoal(SMART)/ valueStream / coreCapabilities / supportITSystems / keyOrganizations / keyDataEntities / disconnectionPoints |
| **L3** 细分场景 | 11 + 五维健康 | businessObjective / businessProcess / keyActivities / capabilityUnits / dataFlow / positions / supportSystems / painPoints / **ontologyExtraction(实体/关系/规则/动作)** / aiOpportunity |
| **L4** 人才地图 | 9 | l3KeyActivity / capabilityUnitName / capabilityType / capabilityDetail / masteryLevel / associatedPosition / currentRate / talentGap |

> **L3 的"先本体后 AI"** 是方法论的关键:必须先抽取业务本体(实体/关系/规则/动作),再基于本体设计 AI Agent 机会,使 AI 推理可解释而非黑盒。这一步是开发计划里最难压缩的卡(CC-16 WF07,预留 6 人时含迭代)。

**五维健康观测体系**(fiveDimHealth)贯穿 L1-L3:L5 数字意识 / L4 数字神经 / L3 数字器官 / L2 数字血液 / L1 数字骨架,每个维度在 L1/L2/L3 有不同含义,1-5 分评分 + 描述。

---

## 4. AI 运行时与多智能体协作

### 4.1 SDK 封装结构

`integrations/claude/` 把 claude-agent-sdk 封装为四个职责清晰的模块:

| 模块 | 职责 |
|------|------|
| `runner.py` | 构造 ClaudeAgentOptions、启动 SDK client、收消息、产出 ChatRunSummary(usage/cost/stop_reason) |
| `serializers.py` | SDK 各类消息 → 前端 SSE 事件 |
| `guard.py` | PreToolUse Hook:Bash 黑名单、写操作路径校验、团队空间文件锁联动 |
| `tool_approval.py` | can_use_tool 自动放行(交互式审批不可用,裁决交 guard) |

### 4.2 多智能体协作模型

每个项目自动创建一个 Agent 实例,采用 **Main Agent + Subagent** 协作:

```
                  用户消息
                     │
            ┌────────┴─────────┐
            │ consultant-router │  ← Plugin: WF01 意图路由
            └────────┬─────────┘
                     │  路由到对应 Skill
            ┌────────┴─────────┐
            │   Main Agent      │  Claude SDK,可用工具:
            │  (遵循道层 Prompt) │   Read/Write/Edit/Bash/WebFetch
            └────────┬─────────┘   + mcp__zhipu__web_search
                     │  Agent tool 调用
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
  Subagent:搜索  Subagent:生成  Subagent:审核
  (web_search)   (Skill 产出)   (WF10 逐条验证)
       │             │             │
       └─────────────┴─────────────┘
                     │
            ┌────────┴─────────┐
            │ PostOutputFilter  │  ← Plugin: 防线 2
            └────────┬─────────┘
                     │
                SSE → 前端 ChatStream
```

**角色约束**(技术说明书 4.2):

- **Main Agent**:规划、调用 subagent、审核、生成最终回复;可使用 Agent tool。
- **Subagent**:执行单一职责(搜索/生成/审核);**不能用 Agent tool**(SDK 配置硬限制,防递归失控);输出须符合 JSON Schema。
- **Run Service**:维护 Run 状态机(pending→running→completed/failed/cancelled),处理超时重试,不直接执行推理。
- **Agent Runtime Worker**:加载会话/项目/Agent/Skill/权限配置,构造 SDK options,**权限校验通过后才启动 SDK**。

### 4.3 7 个 Skill(对应开发计划 CC-13~19)

| 编码 | Skill | 类型 | 输出 |
|------|-------|------|------|
| WF02 | consultant-upload | 独立 | 文件分类(7 种 materialType)+ 归档路径 |
| WF03 | consultant-gap-check | **辅助** | 覆盖度评分 + 缺口维度 + 建议关键词(WF06/07 前置自动跑,不产生 WorkflowRun) |
| WF06 | consultant-visit-plan | 独立 | 拜访目标 + 沟通要点 + 访谈问题 + 资料清单 |
| WF07 | consultant-hypothesis-map | 独立(核心) | L1-L4 结构化地图 + 跨层一致性校验 + 本体抽取 |
| WF09 | consultant-interview | 独立 | VisitRecord + EvidenceSource 数组(四维度证据) |
| WF10 | consultant-verify | 独立 | 假设 vs 证据逐条判定 + 现状节点 |
| WF12 | consultant-stakeholder | 独立 | StakeholderCard(客观+主观+行为)+ 话术 |

每个 SKILL.md 含:YAML 元数据 / 道层引用 / 法层字段契约引用 / 结构化输出 JSON Schema。WF07 额外含 **5 步强制分步 + 跨层一致性校验**(L2↔L1 / L3↔L2 / L4↔L3)。

### 4.4 2 个 Plugin + 1 个平台内置 MCP

| 名称 | 职责 | 实现要点 |
|------|------|---------|
| consultant-router | WF01 意图路由 | Hook 拦截输入:WF chip 直跳;自然语言 LLM 分类(置信度≥0.7)→ 关键词兜底 → 用户确认;每次写 IntentRoutingLog |
| consultant-defense | 防线 1 + 防线 2 | 道层 System Prompt 注入 Hook + PostOutputFilter 确定性指纹过滤 |
| 智谱 Web Search MCP | 公开信息搜索 | 平台内置(`runner._builtin_mcp_servers`),配 Key 注入,未配静默禁用 |

> V2.0 初稿曾设计 3 个 Plugin(含 consultant-search),经审查确认搜索由平台内置 MCP 提供,**最终为 2 Plugin + 1 内置 MCP**,避免重复造轮子。

### 4.5 项目自动创建 Agent(技术说明书 5.5)

创建项目时,系统在一个事务内自动:

1. 建 Project(创建者默认 Owner);
2. 建 Agent(name=`{项目名} Agent`,code=`consultant_{projectId前8位}`,system_prompt 注入道层 + 项目上下文);
3. 写 7 条 skill_bindings + 2 条 plugin_bindings;
4. 关联 `project.agent_id`。

这一步是开发计划的关键路径核心(CC-06,⭐ 标记),打通"建项目即获得一个配置齐全的咨询 Agent"。

---

## 5. 前端架构

### 5.1 导航结构(需求规格 2.1)

业务地图/营销地图/拜访记录作为**独立一级页面**,与对话平级,各自顶部带项目选择器:

```
Sidebar
├── 💬 对话            ← 唯一 AI 交互入口
├── 🗺️ 业务地图        ← 独立页面(顶部选项目)
├── 🎯 营销地图        ← 独立页面(顶部选项目)
├── 📝 拜访记录        ← 独立页面(顶部选项目)
├── ─────────
├── 📁 个人空间        ← 项目筛选 + 自动归档
├── 👥 团队空间        ← 公开资产 + 方法论库
├── 🤖 智能体管理
└── ⚙️ 设置(admin)
```

> **为什么独立页面而非 Tab**:Tab 方案下不同 Session 产出"自动合并"到一个地图,合并规则不清;独立页面 + 顶部项目选择器 = 单一真源(该项目全部已确认数据),权限也更清晰。开发计划 CC-01 已锁定 Sidebar A 方案,清理 B/C 原型脚手架。

### 5.2 三个核心业务页面

| 页面 | 子视图/Tab | 数据来源 |
|------|-----------|---------|
| **业务地图** | 假设地图 / 现状地图 / 偏差池 / 前置分析 / 五维健康 | `WHERE projectId=X AND reviewStatus='reviewed'` |
| **营销地图** | 组织架构 / 决策链 / 立场矩阵 / 采购时间线 / 角色卡 / 知识库 | 角色 + 主观层评分 |
| **拜访记录** | 拜访时间线 + 证据筛选面板(类型/强度/角色) | VisitRecord + EvidenceSource |

业务地图节点详情面板**按层级差异化**:L1(5 要素+健康)/ L2(8 要素)/ L3(11 要素 + 本体抽取卡片 + AI 机会)/ L4(9 要素 + 达标率),L1/L2/L3 还含五维健康雷达图。

### 5.3 状态管理

采用轻量的 React Context + useReducer,**不引入外部状态库**:

- `ProjectContext`:全局当前项目 + 项目列表,跨页共享(由 `<ProjectSwitcher>` 触发)。
- 各页面局部状态:activeSubView / selectedNode / expandedNodes / filters 等。

### 5.4 API Client

`api/client.ts` 统一封装所有 REST 调用 + SSE 流解析(`streamChat` / `streamRunningSession`)。新增 customers/projects/business-map/marketing-map/visit-records/public-share 方法,与后端端点一一对应(开发计划 CC-10)。

---

## 6. API 与流式对话

### 6.1 REST 端点全景(技术说明书 7.1)

全部挂 `/api/`,沿用现有 Session 认证。按资源分组:

- **客户/项目**:`/api/customers`、`/api/projects` + 成员子资源
- **业务地图**:`/api/projects/{id}/business-map`(支持 level/mapType/parentId 筛选)+ `/pre-analysis` + `/batch`(AI 采纳后批量写入)
- **营销地图**:`/api/projects/{id}/stakeholder-cards` + `/api/talk-scripts`
- **拜访记录**:`/api/projects/{id}/visit-records` + `/evidence`(支持筛选)
- **公开/共享**:`/api/public/{type}/{id}`、`/api/share/{type}/{id}`、`/api/team-space/public-assets`

### 6.2 SSE 流式对话(技术说明书 7.2)

复用现有 `/api/sessions/{id}/chat`,**扩展事件类型**以支持作战台特性:

| 事件 | 用途 |
|------|------|
| `content_block_delta` | 流式文本 |
| `thinking_delta` | DeepSeek 思维链(灰色折叠面板,**不走 PostOutputFilter**) |
| `tool_call` / `tool_result` | 工具调用过程 |
| `subagent_invoked` / `subagent_completed` | Subagent 调用 |
| **`candidate_ready`** | AI 候选结果就绪(触发候选区交互) |
| **`intent_routed`** | 意图路由结果 |
| `run_status` | Run 状态机变更 |
| `error` | 错误事件 |

### 6.3 候选区闭环(需求规格 7.1)

对话页的核心交互闭环,贯穿所有 WF:

```
用户装填 WF chip / 输入
     ↓
AI 执行 Skill → 产出候选(candidate_ready)
     ↓
展示候选卡片(Markdown + 结构化预览 + 可展开思考)
     ↓
┌─ 采纳 → 结构化数据写正式表 → 对应数据页面可见 + 文件归档
├─ 驳回 → 进偏差池/驳回池(不删除)
└─ Chat 调整 → 自然语言修改 → AI 重新生成 → 展示 diff → 再次确认
                ↑__________________________↓
                (可多次循环,直到采纳或驳回)
```

---

## 7. 权限与安全边界

### 7.1 三层权限模型(需求规格第三章)

```
┌─────────────────────────────────────┐
│        系统级(User Role)            │
│   admin  │ 最高权限,所有项目可见,     │
│          │ 管理种子数据/触发词/用户    │
│   user   │ 权限由项目级角色决定        │
├─────────────────────────────────────┤
│      客户-项目级(Project Role)       │
│   Owner  │ 创建项目,拉人,审核副手 WF07 │
│   Deputy │ 跑所有 WF,WF07 需 Owner 审核│
├─────────────────────────────────────┤
│           跨项目隔离                  │
│   默认:项目内全透明,项目外全隔离      │
│   手动:对象级"完全公开"→团队空间      │
│        对象级"指定用户"→对方可见      │
└─────────────────────────────────────┘
```

### 7.2 数据隔离规则(技术说明书 10.3)

| 数据 | 读 | 写 |
|------|----|----|
| Customer 基本信息 | 项目成员(同客户下共享) | 创建者/admin |
| Project 数据 | 项目成员(Owner+Deputy) | Owner 设置 / 成员写业务数据 |
| BusinessMapObject / StakeholderCard | 项目成员 | 项目成员 |
| VisitRecord | 项目成员 | 创建者/Owner |
| EvidenceSource | 项目成员 | 创建者 |
| TalkScript | 项目成员(关联角色)/ 全员(isTemplate) | 创建者 |
| 个人空间文件 | 用户本人 | 用户本人 |
| 团队空间公开资产 | 所有登录用户 | 对象拥有者(设公开) |

### 7.3 运行时安全约束(技术说明书 10.5)

Agent Runtime Worker 启动 SDK 前必须校验:用户是否有权访问 Session / Agent / 本次 Skill / 本次文件。SDK 运行时:

- **cwd 严格限定**为当前 conversation workspace;
- **guard.py 拦截所有文件路径**,校验在 cwd 内;
- **Subagent 不能用 Agent tool**(防递归);
- **Plugin Hook 在沙箱环境执行**(受限 Python)。

### 7.4 WF07 审核流程(需求规格 3.4)

```
副手跑 WF07 → 副手自审确认 → pending_review
     ↓
Owner 对话 Banner 收到提醒 → 审核
     ├ 通过 → published(发布到业务地图)
     └ 驳回 + 修改意见 → 退回副手(保留历史版本快照)
```

Owner 自己的 WF07 产出,采纳后直接发布,无需审核。状态机:`draft → pending_review → reviewed(published) / rejected → draft`。

---

## 8. 健壮性设计(核心)

> 本章是文档重点。我们把四份材料里所有"可靠性 / 安全性 / 容错 / 一致性"的设计,按六个维度系统组织。每条都标明**解决的问题**、**机制**、**来源材料**。

### 8.1 健壮性设计总原则

整套系统的健壮性围绕五条总原则展开(它们是第 2.2 节产品原则的技术投射):

1. **人在环中(Human-in-the-loop)**:AI 产出永远先进候选区,用户确认才入正式库——AI 错了不会污染正式数据。
2. **单一真源**:每个数据页面只查一个条件(`projectId + reviewStatus`),不存在多源合并歧义。
3. **不可覆盖,只新建版本**:假设节点永久保留,现状节点新建关联回假设;WF07 每次提交留快照。
4. **纵深防御**:安全检查多层叠加(权限 → 路径 → 工具 guard → 防线),不押注单点。
5. **确定性优先于 LLM 判断**:涉及安全/合规的过滤(防线 2)用确定性指纹匹配,不交给 LLM。

### 8.2 维度一:人机协同的可靠性(候选区 + Chat 调整 + 单一真源)

这是本系统最有特色的健壮性设计——**用流程保证 AI 产出可控**。

**① 候选区(Pending Area)统一规则**(需求规格 7.1)

所有 WF 的 AI 产出**先进候选区**,绝不直接写正式表:

- 采纳 → 结构化数据迁移到正式区 → 数据页面可见 + 文件归档;
- 驳回 → 进偏差池/驳回池,**不删除**(可复盘);
- Chat 调整 → 循环直到采纳或驳回。

> **健壮性意义**:即便 LLM 产生幻觉或错误结构化,也不会污染业务数据——最坏情况是候选被驳回。这是"AI 不可靠"假设下的核心防线。

**② Chat 调整机制**(需求规格 7.2)

所有候选在采纳前支持自然语言多轮调整:产出 → 用户描述修改 → AI 基于原文 + 指令重新生成 → 展示 diff → 再确认。**循环次数不限**,直到满意或放弃。

> **健壮性意义**:用户不必因为 AI 一次产出的瑕疵而整体驳回,可以渐进修正,降低返工成本。

**③ 数据页面单一真源**(需求规格 7.3)

每个数据页面查询条件固定且唯一:

| 页面 | 查询条件 |
|------|---------|
| 业务地图 | `projectId=X AND reviewStatus='reviewed'` |
| 营销地图 | `projectId=X AND reviewStatus='reviewed'` |
| 拜访记录 | `projectId=X`(+ EvidenceSource 再加 reviewStatus) |

不同 Chat Session 的产出通过 `projectId` 关联,采纳后 `reviewStatus` 变 reviewed 即对页面可见。**不存在多 Session 数据冲突**:每个对象有唯一 ID,多次生成同类型节点创建**新版本**(保留旧快照),而非覆盖。

**④ WF07 版本管理与审核**(需求规格 7.4 / 技术说明书 10.4)

- 每次提交保留快照版本;
- 副手提交 → Owner 审核通过 → 发布(`published`);
- Owner 审核时可对比多个版本;
- 驳回保留历史,副手修改后重新提交。

> **健壮性意义**:关键产出(假设地图)有双签(副手自审 + Owner 审核)+ 版本可追溯,防止错误假设污染下游验证与营销。

**⑤ 候选→正式入库的事务一致性**(开发计划风险 R4)

候选采纳的批量写入走**单事务**,`reviewStatus` 原子更新,避免"采纳了但页面没出现"的半成品状态。

### 8.3 维度二:对话执行的可靠性(Run 状态机 + SSE + 隔离)

**① Run 状态机**(技术说明书 4.2)

每个对话轮次是一个 Run,状态机:`pending → running → completed / failed / cancelled / timeout`。Run Service 维护状态、处理超时和重试,不直接执行推理——**状态与执行解耦**。

**② SSE 流式 + 候选区事件**

SSE 事件流覆盖完整生命周期(message_start → content/thinking delta → tool_call/result → subagent → **candidate_ready** → run_status → message_stop / error),前端据此渲染进度与候选。`error` 事件保证失败可见。

**③ 智能体工作目录隔离**(技术说明书 10.5 / 开发计划 R7)

每个 Agent 有独立工作目录,运行时 SDK 的 cwd 严格限定为当前 conversation workspace。`guard.py` 拦截所有文件路径访问。项目自动创建的 Agent 复用平台 `workdir.py` 的 `CLAUDE_CONFIG_DIR` 注入机制,**避免并发会话互相串扰**。

**④ Subagent 能力约束**

Subagent 不能使用 Agent tool(SDK 配置硬限制),防止"AI 自行递归派生 Agent"导致失控或成本爆炸。

**⑤ Run 失败可定位**(开发计划 M5)

失败时可定位到具体层级:main agent / subagent / tool / file,便于排障而非"整体失败原因不明"。

### 8.4 维度三:安全防护的纵深(权限 + 路径 + 工具 + 防线)

**① 三层权限 + 数据隔离**(第 7 章)

系统级(admin/user)+ 项目级(owner/deputy)+ 对象级(isPublic/sharedWith),项目内透明、项目外隔离。非成员访问项目数据 → 403。

**② 路径安全**(技术说明书 8.3)

- Agent 只能访问 cwd 下 inputs/working/artifacts;
- 禁止路径逃逸(`../`)、软链接逃逸、绝对路径越权;
- 文件访问拦截在 guard.py,记录 `file.accessed` 事件。

**③ 工具调用防护(guard)**

PreToolUse Hook 拦截 Bash 危险命令、写操作路径校验、团队空间文件锁联动;`disallowed_tools` 显式禁用危险工具;`can_use_tool` 只做自动放行,真正裁决在 guard。

**④ 双重防线(consultant-defense)**(需求规格 7.6)

- **防线 1(道层 System Prompt 注入)**:每个 Session 初始化时注入 `dao_layer.md` 全文(轻咨询伦理、保密义务、诚实汇报),**不可被 RAG 覆盖**;
- **防线 2(PostOutputFilter)**:LLM 产出后做 **100% 确定性指纹匹配**,过滤 `never_visible` 内容(如内部定价),**不依赖 LLM 判断**。

> **健壮性意义**:防线 1 在"输入端"约束 AI 行为,防线 2 在"输出端"兜底——即便 LLM 被诱导,确定性过滤也能拦住敏感泄露。思维链内容**不走**防线 2(过滤会破坏推理连贯性)。

**⑤ 登录白名单 + OAuth state**

平台底座已有的企微登录白名单(用户名 + 部门双层,空名单全放行)+ SSO 的 `state` 参数防 CSRF,本应用直接复用。

### 8.5 维度四:AI 输出的可靠性(Schema + 方法论三层 + 结构化)

**① 结构化输出(JSON Schema)**(技术说明书 11.4)

所有 Skill 用 JSON Schema 约束 LLM 输出,确保解析可靠——不靠正则从自由文本里抠字段。WF07 输出 `{l1_nodes, l2_nodes, l3_nodes, l4_nodes}`,WF12 输出角色卡数组,均强 Schema。

**② 跨层一致性校验**(需求规格 4.2 WF07)

WF07 的 5 步强制分步,每步带校验:

- L2 子场景必须严格对应 L1 价值链环节;
- L3 关键活动必须严格对应 L2 价值流步骤;
- L4 能力单元必须严格对应 L3 关键活动;
- L3 本体抽取的实体必须在 L2 关键数据实体中出现。

> **健壮性意义**:防止 LLM 生成"层与层对不上"的地图——这是咨询场景下 AI 产出最常见的结构错误。

**③ 方法论三层使用模式**(需求规格 7.7)

| 模式 | 适用层 | 机制 | 健壮性意义 |
|------|--------|------|-----------|
| 注入(Inject) | 道层 | 永远在 System Prompt,不可 RAG | 伦理底线不可绕过 |
| 结构化读取 | 法层 | 全量读取,不走 RAG | **缺片段就错乱**,必须全量 |
| RAG 检索 | 器层 | Top-K 召回 | 参考资料性质,允许模糊 |

> 法层(字段契约)走全量结构化读取而非 RAG,是因为字段定义缺一片就会导致 LLM 产出结构错乱——这是"正确性 > 灵活性"的明确取舍。

**④ 来源标注 + 可溯源**(需求规格 5.2)

StakeholderCard 每个字段标注 sourceType(拜访纪要/资料/公开信息/用户手动/模型推断),关联 evidenceIds,无法确定的字段标"待验证"——AI 产出**可追溯到底层证据**,而非凭空生成。

### 8.6 维度五:外部依赖的容错(搜索 + 模型路由)

**① 智谱搜索容错降级**(技术说明书 5.4 / 开发计划 R3)

- 配了 Key → MCP 注入,Agent 可用 `web_search`;
- **未配 Key → 返回 `{}` 静默禁用**,不影响其它功能;
- 搜索失败静默降级,不阻断 WF07 主体(可基于模型知识生成,标注 sourceType=模型知识);
- 同一(公司名 + 关键词)组合**增量去重**,已搜过的不重复搜,省成本、降限流风险。

**② 双档模型路由**(技术说明书 11.1)

| 场景 | 模型 | 理由 |
|------|------|------|
| 意图分类(WF01)/ 文件分类(WF02) | Flash | 简单任务,低延迟低成本 |
| 核心 Skill(WF06/07/09/10/12)/ Chat Mode | Pro + thinking | 复杂推理需要深度思考 |

> **健壮性意义**:简单任务不浪费 Pro 的算力与成本;复杂任务有 thinking 保证质量。路由策略本身也是成本/可靠性的平衡。

**③ 深度思考可观测**(技术说明书 11.2)

Pro 模型的 `reasoning_content` 经 `thinking_delta` SSE 事件推给前端,渲染为折叠面板。用户能看到"AI 为什么这么推理",**增强可信度和可调试性**——这是对抗"AI 黑盒"的健壮性手段。

### 8.7 维度六:可观测与可追溯(事件 + 审计)

**① 事件流(技术说明书 9.1)**

在平台底座事件基础上,新增业务事件:`intent.routed` / `candidate.generated` / `candidate.adopted` / `candidate.rejected` / `object.created/updated/deleted/published` / `wf07.submitted/approved/rejected`。事件写 `agent_events` 表 + 文件日志 `events.jsonl`,可通过 API 查询。

**② IntentRoutingLog 每次必入**(需求规格 4.3)

WF01 每次决策都写日志:LLM 分类结果 / 关键词命中 / 用户确认选择 / 最终意图。意图路由准确率可统计(M2 验收要求自然语言 ≥80%,chip 100%)。

**③ 审计日志**(技术说明书 9.3)

管理员操作(管理用户/改触发词/管理种子数据/查统计)写 `audit_logs`,记录操作人、目标、类型、时间。

> **健壮性意义**:全链路可观测 + 可追溯,出问题能定位到"哪次路由、哪个候选、谁采纳、何时发布",满足企业内部审计需求。

### 8.8 健壮性设计速查表

| 维度 | 设计点 | 解决的问题 | 来源 |
|------|--------|-----------|------|
| 人机协同 | 候选区统一规则 | AI 错不污染正式数据 | 需求规格 7.1 |
| 人机协同 | Chat 调整 + diff | 渐进修正降返工 | 需求规格 7.2 |
| 人机协同 | 单一真源 + 新版本不覆盖 | 多 Session 无冲突 | 需求规格 7.3 |
| 人机协同 | WF07 双签 + 版本快照 | 关键产出防污染 | 需求规格 7.4 |
| 人机协同 | 候选→正式单事务 | 采纳半成品 | 开发计划 R4 |
| 对话执行 | Run 状态机 | 执行可追踪可超时 | 技术说明书 4.2 |
| 对话执行 | 工作目录隔离 | 并发串扰 | 技术说明书 10.5 |
| 对话执行 | Subagent 禁 Agent tool | 递归失控 | 技术说明书 4.2 |
| 安全防护 | 三层权限 + 隔离 | 越权访问 | 第 7 章 |
| 安全防护 | 路径安全 + guard | 路径逃逸 | 技术说明书 8.3 |
| 安全防护 | 双重防线 | 行为约束 + 敏感泄露 | 需求规格 7.6 |
| AI 输出 | JSON Schema 结构化 | 解析不可靠 | 技术说明书 11.4 |
| AI 输出 | 跨层一致性校验 | 层级对不上 | 需求规格 4.2 |
| AI 输出 | 方法论三层(法层全量) | 字段缺失错乱 | 需求规格 7.7 |
| AI 输出 | 来源标注可溯源 | 凭空生成 | 需求规格 5.2 |
| 外部依赖 | 智谱搜索静默降级 | 搜索故障阻断 | 技术说明书 5.4 |
| 外部依赖 | 双档模型路由 | 成本/质量平衡 | 技术说明书 11.1 |
| 可观测 | 业务事件 + IntentLog + 审计 | 不可追溯 | 技术说明书 9 |

---

## 9. 实施路线与风险防控

### 9.1 分阶段实施(开发计划 + 技术说明书 12)

开发计划表把建设拆成 **6 个 Phase / 43 张 Claude Coding 任务卡**,工期口径为"人工决策验收时间"(Claude 执行编码),约 **100 人时 ≈ 12-13 工作日**:

| Phase | 目标(里程碑) | 关键卡 | 人时 |
|-------|-------------|--------|------|
| P0 原型定稿 | M0:锁定 Sidebar A,清脚手架 | CC-01 | 1 |
| P1 地基 | M1:可建客户/项目,Agent 自动生成,权限生效 | CC-02 建表 / **CC-06 项目+Agent** ⭐ / CC-08 权限 | ~20 |
| P2 核心 Skill | M2:对话页 WF chip → 候选区闭环 | **CC-16 WF07** ⭐⭐ / CC-21 智谱验证 / **CC-24 候选区** ⭐ | ~33 |
| P3 数据页面 | M3:三大页面端到端 | CC-27 业务地图 / **CC-28 节点详情** ⭐ / CC-31 营销六视图 | ~25.5 |
| P4 知识归档 | M4:自动归档 + 公开资产 | CC-36 归档机制 / CC-37 公开共享 | ~9 |
| P5 打磨 | M5:审核/去重/统计/可上线 | CC-39 WF07 审核 / CC-42 错误处理+性能 | ~11 |

### 9.2 关键路径(开发计划 10.1)

```
CC-02 建表 → CC-03 ORM → CC-06 项目+自动Agent → CC-16 WF07
   → CC-24 候选区 → CC-27 业务地图页 → CC-28 节点详情 → M3
```

⭐ 标记(CC-06/16/24/27/28)是关键路径核心,须优先保障。其中 **CC-16(WF07)是最难压缩的卡**:跨层一致性 + L3 本体抽取质量,预留 6 人时含 1-2 轮迭代。

### 9.3 风险登记册(开发计划第十一章)

| # | 风险 | 影响 | 概率 | 缓解 |
|---|------|------|------|------|
| R1 | WF07 跨层一致性/本体抽取质量不达标 | M2 延期 | 高 | CC-16 预留迭代 + 种子案例库 + 优先跑通 |
| R2 | Claude 生成 JSONB payload 与原型字段不对齐 | P3 返工 | 中 | CC-09 先冻结类型;CC-27 重构前核对 |
| R3 | 智谱 MCP 限流/格式 | WF07/WF12 搜索失败 | 中 | 已验证集成;增量去重;失败静默降级 |
| R4 | 候选→正式入库事务一致性 | 采纳后页面未见 | 中 | 批量写走单事务;reviewed 原子更新 |
| R5 | 现有原型含 mock 鉴权,上线遗忘恢复 | 安全风险 | 中 | CC-01 加 TODO;M5 门禁检查 |
| R6 | 五维雷达/组织架构/立场矩阵渲染复杂 | P3 超期 | 中 | 轻量 SVG/Canvas;复杂视图先降级表格 |
| R7 | 项目自动 Agent 与现有 workdir 隔离冲突 | 并发串扰 | 低 | 复用 workdir.py;CLAUDE_CONFIG_DIR 注入 |

> 风险登记册本身也是健壮性的一部分:**风险被显式识别、评估、配有缓解措施**,而非被动应对。

### 9.4 验收门禁(开发计划第十二章)

每个 Phase 有明确门禁,达标才进下一阶段:

- **M1**:可建 Customer/Project,Project 自动生成 Agent(7 Skill + 2 Plugin 绑定),非成员 403,导航 8 入口可切换。
- **M2**:5 WF chip 触发对应 Skill;WF07 实跑(智谱搜索 → L1-L4 候选);候选可采纳/驳回/Chat 调整;思考面板可展开;**意图路由自然语言 ≥80%,chip 100%**。
- **M3**:业务地图 L1-L4 树 + 节点详情差异化 + 本体卡片 + 雷达 + 三子视图;营销六视图 + 角色 5 Tab + 评分自动算;拜访时间线 + 证据三维筛选;AI 产出采纳后各页可见 + 手动 CRUD。
- **M4**:上传自动归档;对象可公开;Chat 沉淀知识片段。
- **M5**:WF07 审核闭环 + 角色去重 + Run 失败可定位 + admin 统计;**恢复真实企微登录(移除 mock)**;1-2 个种子项目端到端跑通。

---

## 10. 总结:技术亮点速查

### 10.1 技术框架亮点

| # | 亮点 | 价值 |
|---|------|------|
| 1 | 复用平台底座,只做应用扩展 | 不重造轮子,聚焦业务 |
| 2 | claude-agent-sdk + Skill/Plugin 形态 | 天然适配"带工具的 Agent 任务",不自研编排框架 |
| 3 | JSONB 分层 payload(L1-L4 一张表) | 易变结构免 DDL 变更,GIN 索引保查询 |
| 4 | 项目自动创建 Agent | "建项目即获得配置齐全的咨询 Agent" |
| 5 | 智谱 MCP 平台内置 | 搜索能力零自研,配 Key 即用 |
| 6 | DeepSeek 双档路由 | 成本/质量平衡 |
| 7 | 独立页面 + 项目选择器(非 Tab) | 单一真源,权限清晰 |

### 10.2 健壮性亮点

| # | 亮点 | 价值 |
|---|------|------|
| 1 | 候选区 + Chat 调整 + 单一真源 | AI 不可靠假设下,产出可控、不污染 |
| 2 | WF07 双签 + 版本快照 | 关键产出防污染、可追溯 |
| 3 | Run 状态机 + 工作目录隔离 + Subagent 约束 | 执行可靠、并发安全、防失控 |
| 4 | 三层权限 + 路径安全 + 工具 guard + 双重防线 | 纵深防御,不押单点 |
| 5 | JSON Schema + 跨层一致性校验 | AI 输出结构可靠、层级自洽 |
| 6 | 方法论三层(法层全量结构化读取) | 字段契约不缺片,正确性优先 |
| 7 | 来源标注可溯源 | AI 产出可追到底层证据 |
| 8 | 智谱搜索静默降级 + 增量去重 | 外部依赖故障不阻断主体 |
| 9 | 业务事件 + IntentLog + 审计日志 | 全链路可观测可追溯 |
| 10 | 风险登记册 + 里程碑门禁 | 风险显式识别、分阶段达标 |

---

> **本文档是 AI 顾问作战台的"技术框架 + 健壮性"综合说明**,面向技术团队建立全局认知。落地时:
> - **写代码** → 照 [技术说明书 V2.0](Agent平台技术说明书V2.0.md) 的 DDL / SKILL.md 骨架 / 端点清单 + [开发计划表 V1.0](开发计划表V1.0.md) 的任务卡。
> - **核对需求** → 以 [需求规格说明书 V2.0](需求规格说明书V2.0.md) 为准(需求 > 技术)。
> - **看代码底座现状** → 参考《平台底座技术框架与健壮性说明》。
>
> 如本文档与上述基准文档不一致,以基准文档为准;本文档仅做综合与提炼。
>
> **文档版本**:V1.0 · **编写日期**:2026-07-06
