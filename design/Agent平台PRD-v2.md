# Product Requirements Document: 智能体平台 v2

**作者**: 产品团队  
**日期**: 2026-05-09  
**状态**: Draft v2  
**相关文档**:
- [Agent平台PRD v1](./design/Agent平台PRD.md)
- [Agent平台技术说明书](./design/Agent平台技术说明书.md)
- CEO Review Plan: `C:\Users\sooit\.gstack\projects\goktech-agent\ceo-plans\2026-05-08-agent-platform.md`

---

## 1. Executive Summary

智能体平台是一个面向企业内部的多用户 Agent Web 平台。平台基于 Claude Agent SDK，支持用户上传私有文档、使用受治理的 Skill/Plugin、创建 Agent Team，并通过可审计的 Run 生成业务产物。

v2 保留 v1 的通用 Agent 平台方向，但将第一版 MVP 的证明路径收敛为 **售前客户分析与 AI 方案生成 Workflow Pack**。平台不是先让用户面对空白 Agent Builder，而是先提供一个可运行、可审阅、可追溯的业务流程包，证明平台能把企业方法论转化为可执行、可治理、可复用的 Agent 工作流。

第一版 MVP 的核心变化：

1. 引入 **Workflow Pack** 作为一等产品概念，售前 Workflow Pack 是第一个内置包。
2. 所有 Agent 产物必须具备 **artifact provenance**，记录输入文件、Skill/Plugin 版本、Agent/Subagent、Run、时间和评审状态。
3. 引入 **Quality Review Agent**，根据版本化 review Skill/rubric 对产物进行独立质量评审。
4. 系统 Skill/Plugin 源码只在 **worker-only isolated runtime** 中执行，不进入用户可见 workspace。
5. Skill/Plugin 进入 MVP，但必须配套扫描、版本、checksum、审批、沙箱和审计。
6. Run 状态机、资源限制、取消语义、错误分类、可观测性、灰度发布和回滚均进入 MVP 范围。

---

## 2. Background & Context

### 2.1 真实业务痛点

CEO review 后确认，平台的第一个明确需求来自售前场景：

| 用户/角色 | 当前流程 | 痛点 | 业务影响 |
|---|---|---|---|
| 售前工程师 | 收到客户需求文档后，调研客户行业、战略、流程、痛点和 AI 机会，编写 market scan、访谈材料、需求分析、AI 方案和 PPT | 每个售前能力不同，分析质量不稳定，人工耗时约 1 周 | 每周需完成 2-3 个客户分析和 AI 方案，交付压力大 |
| 售前负责人/业务负责人 | 需要保证团队方案质量和交付周期 | 质量控制依赖人工评审，复用组织方法论困难 | 方案质量不可控，评审周期长，难以规模化 |

第一版平台必须证明：它能把组织沉淀的售前方法论变成可运行、可审计、可评审的 Agent Workflow Pack，并显著缩短从客户资料到一版方案包的周期。

### 2.2 当前企业内部 Agent 使用痛点

| 痛点 | 现状 | 影响 |
|---|---|---|
| 知识私有化困难 | 用户文档散落本地，AI 难以安全使用私有上下文 | 输出缺乏上下文，且存在数据泄露风险 |
| 业务方法论难复用 | 售前、分析、方案设计等依赖个人经验 | 质量波动大，培训和复用成本高 |
| Agent 定制门槛高 | 创建专用 Agent 需要理解 prompt、Skill、工具和运行环境 | 非技术用户难以自助构建 |
| 多格式文档难处理 | Office、PDF、图片等文件需要人工预处理 | 输入成本高，影响自动化闭环 |
| 协作缺乏编排 | 复杂任务需要多个专业 Agent 协作 | 人工拼接结果，容易遗漏和重复 |
| Skill/Plugin 资产保护不足 | 企业自研能力包可能包含核心方法论或工具逻辑 | 源码泄露会造成知识产权和安全风险 |
| AI 产物缺乏可信链路 | 生成结果常只有文件，没有来源、版本、评审状态 | 用户不敢直接使用，问题难追踪 |

### 2.3 解决方案

平台提供四层能力：

| 层级 | 能力 | MVP 落地方式 |
|---|---|---|
| 知识层 | 上传、解析、结构化、引用私有文档 | 支持常见文档格式，生成 conversation input manifest |
| 方法论层 | 将企业方法论封装为版本化 Skill/Plugin 和 Workflow Pack | 内置售前 Workflow Pack |
| Agent 层 | 创建 Agent、Agent Team、Quality Review Agent | Main Agent + Subagents + Review Agent |
| 治理层 | 权限、沙箱、扫描、版本、provenance、事件、指标、审计 | MVP 必须可追踪、可回滚、可运营 |

### 2.4 市场定位

面向企业内部知识工作者和业务团队的 Agent Workflow Platform。区别于通用 ChatBot，本平台以 **私有知识 + 组织方法论 + 多 Agent 协作 + 可审计产物** 为核心差异化。

第一版不是“什么 Agent 都能做”的空白平台，而是以售前 Workflow Pack 证明平台价值，再扩展到投研、法务、交付、客服等其他 Workflow Pack。

---

## 3. Objectives & Success Metrics

### 3.1 Product Goals

| # | Goal | Measurement |
|---|---|---|
| G1 | 用户可上传私有文档并转换为 Agent 可用文本 | 支持 doc/docx/xls/xlsx/pdf/md/txt 等格式；普通文件转换 ≤30s |
| G2 | 用户可从 Workflow Pack 启动业务任务，而不是从空白 Agent 配置开始 | 售前 Workflow Pack 可一键启动，完成输入校验、运行、产物审阅 |
| G3 | 用户可创建和运行 Agent Team | 支持 1 Main Agent + ≥2 Subagents，Subagent 禁止递归委派 |
| G4 | 系统 Skill/Plugin 资产受保护 | 0 次非授权源码下载；系统源码不进入用户可见 workspace |
| G5 | 每个产物可追溯 | 100% MVP artifacts 记录 provenance 和 review_status |
| G6 | Quality Review Agent 可审查产物质量 | 100% 售前核心产物经过 Review Agent 检查后才能人工批准 |
| G7 | 多用户隔离 | 0 次跨用户数据泄露或 workspace 越权访问 |
| G8 | 平台可运营 | Run、转换、扫描、安全拦截、质量评审均有 day-1 metrics 和告警 |

### 3.2 Presales MVP Success Metrics

| Metric | Current | MVP Target | Measurement |
|---|---:|---:|---|
| 售前首版方案包周期 | 约 1 周 | 有效输入上传后 1 个工作日内生成首版包 | Pilot 记录 |
| Pilot 机会数量 | 0 | 2-3 个真实售前机会 | Pilot cohort |
| 产物接受率 | N/A | 3 个 pilot 中至少 2 个经 ≤1 轮修改后被售前负责人接受 | Review status |
| 核心产物数量 | 手工不固定 | 5 个固定产物 | Artifact registry |
| 质量审查覆盖率 | N/A | 100% 核心产物经 Quality Review Agent 审查 | Review events |
| Provenance 覆盖率 | N/A | 100% 核心产物具备来源链路 | Artifact metadata |

### 3.3 Platform Success Metrics

| Metric | Current | MVP Target | Measurement |
|---|---:|---:|---|
| Run 完成率 | N/A | ≥90% 非恶意、有效输入 Run 达到 completed 或 revision_requested | Run events |
| 文档转换成功率 | N/A | ≥95% 支持格式普通文件转换成功 | File conversion events |
| Skill/Plugin 扫描覆盖率 | N/A | 100% 上传或上架前扫描 | Scan events |
| 安全越权事件 | N/A | 0 个未拦截越权 | Security audit |
| 系统 Skill/Plugin 源码泄露 | N/A | 0 次 | Security audit |
| Run 失败可定位率 | N/A | 100% failed/timeout/cancelled Run 有 named error class | Run error registry |

### 3.4 Non-Goals

| # | Non-Goal | Rationale |
|---|---|---|
| N1 | Public marketplace 交易 | 第一版聚焦企业内部治理，不做商业化交易 |
| N2 | 复杂 DAG 工作流引擎 | MVP 使用 Claude Subagent 和 Workflow Pack，不自研 DAG |
| N3 | 对象存储/分布式文件系统 | 第一版使用本地文件系统，但必须抽象存储边界 |
| N4 | 多组织 SaaS 租户体系 | 第一版为单组织部署 |
| N5 | 实时协同编辑 | Conversation 内以串行消息和 Run 为核心 |
| N6 | 完整 PPT 渲染系统 | MVP 输出 structured Markdown PPT outline，正式 deck 后续做 |
| N7 | 完整事件回放 | MVP 做事件、指标、审计，不做全量 replay |
| N8 | 完整管理员图表 dashboard | MVP 做 day-1 metrics/alerts/runbooks，图表后续做 |

---

## 4. Target Users, Roles & Permissions

### 4.1 用户画像

| 画像 | 描述 | 核心诉求 |
|---|---|---|
| 售前工程师 | 需要快速理解客户、产出分析和 AI 方案 | 上传资料，运行售前 Workflow Pack，审阅并导出方案包 |
| 售前负责人/业务负责人 | 对方案质量、周期和方法论复用负责 | 统一质量标准，查看 pilot 结果，批准 rubric |
| 知识工作者/业务分析师 | 处理大量文档和分析任务 | 复用 Workflow Pack 和 Agent Team |
| Skill/Plugin Admin | 管理系统能力包 | 上架、审批、版本、弃用、审计 Skill/Plugin |
| 系统管理员 | 管理用户、权限、安全和运行审计 | 控制访问、排查问题、处理安全事件 |

### 4.2 角色模型

| Role | 权限范围 | MVP 必须支持 |
|---|---|---|
| 普通用户 | 使用授权 Workflow Pack、上传文档、运行 Agent Team、查看自己的产物 | 是 |
| 高级用户/Team Lead | 管理团队 Workflow Pack 使用、查看团队 Run 和产物状态 | MVP 可简化 |
| Presales Leader / Business Owner | 审批售前质量 rubric，接受或拒绝 pilot 结果 | 是 |
| Skill/Plugin Admin | 创建、扫描、审批、版本化、下架系统 Skill/Plugin | 是 |
| System Admin | 用户、角色、审计、运行配置、安全告警 | 是 |
| Quality Review Agent | 读取产物和 review rubric，输出结构化质量评审 | 是，作为系统 Agent |

---

## 5. Core Concepts

### 5.1 Workflow Pack

Workflow Pack 是平台和业务场景之间的一等产品接口。

一个 Workflow Pack 包含：

| 组成 | 说明 |
|---|---|
| Pack metadata | name、description、owner、version、status |
| Input contract | 必填/选填输入、支持格式、弱输入处理 |
| Agent Team template | Main Agent、Subagents、Quality Review Agent |
| Approved Skills/Plugins | 本 Pack 可使用的能力包版本 |
| Artifact specs | 预期产物、必备章节、输出格式 |
| Review rubric | 质量评审 Skill/rubric |
| Metrics/evals | 成功指标、失败阈值 |
| Rollout policy | pilot cohort、feature flag、扩展条件 |

MVP 内置第一个 Workflow Pack：**售前客户分析与 AI 方案生成 Pack**。

### 5.2 Agent Team

Agent Team 是一个可重复运行的 Agent 组合：

```text
Agent Team
├── Main Agent
│   ├── 理解用户请求
│   ├── 规划执行
│   ├── 调度 Subagents
│   └── 整合输出
├── Subagent A
│   └── 执行专业任务
├── Subagent B
│   └── 执行专业任务
└── Quality Review Agent
    └── 基于 review Skill/rubric 审查产物
```

约束：

- Main Agent 可以调用 Subagent。
- Subagent 不能调用其他 Subagent。
- Subagent 不能使用 Agent Tool 递归委派。
- Quality Review Agent 不直接改写产物，只输出 review findings 和 pass/fail。
- Human approval 仍然是客户交付前的最终门槛。

### 5.3 Skill / Plugin

| 类型 | 定义 | MVP 策略 |
|---|---|---|
| Skill | 声明式方法论、提示、流程和参考材料能力包 | 支持系统 Skill 和私有 Skill |
| Plugin | 可被 Agent 使用的工具/集成能力 | MVP 支持受控绑定和执行，但不做公开 marketplace |

MVP 中 Skill/Plugin 都必须具备：

- version
- checksum
- approval status
- approved_by
- approved_at
- deprecated flag
- scan status
- usage audit

### 5.4 Artifact

Artifact 是 Agent Run 生成的业务产物，不只是文件。

每个 artifact 必须记录：

```text
Artifact
├── artifact_id
├── artifact_type
├── run_id
├── conversation_id
├── workflow_pack_id/version
├── created_by_agent_id/subagent_id
├── input_files: [file_id, extracted_version, checksum]
├── skills_used: [skill_id, version, checksum]
├── plugins_used: [plugin_id, version, checksum]
├── prompt_template_version
├── generated_at
├── review_status: pending | approved | rejected | revision_requested
└── review_result_id
```

---

## 6. User Stories & Requirements

### 6.1 P0 - MVP Must Have

| # | User Story | Acceptance Criteria |
|---|---|---|
| P0-1 | 作为用户，我可以注册/登录平台并拥有独立 workspace | 登录后仅能访问自己的文件、Conversation、Run、Artifact；跨用户访问被拒绝并记录 |
| P0-2 | 作为用户，我可以从 Workflow Pack 首页启动任务 | 首页优先展示可用 Workflow Pack；售前 Pack 可一键进入上传和运行流程 |
| P0-3 | 作为售前用户，我可以上传客户资料并触发输入校验 | 支持 doc/docx/xls/xlsx/pdf/md/txt；空文件、损坏文件、密码文件、弱输入有明确提示 |
| P0-4 | 作为用户，我可以将上传文档添加到 Conversation inputs | 平台生成 input manifest；Agent 只能读取当前 Conversation 授权 inputs |
| P0-5 | 作为用户，我可以运行售前 Workflow Pack | 有效输入后生成 market scan、interview guide、requirement analysis、AI solution outline、structured Markdown PPT outline |
| P0-6 | 作为用户，我可以查看 Run 状态、事件流和错误原因 | Run 使用明确状态机；失败时展示 named error class 和用户可理解说明 |
| P0-7 | 作为用户，我可以查看和下载产物 | 产物展示 provenance、review_status；缺失 provenance 的产物不得被批准 |
| P0-8 | 作为用户，我可以请求修改、批准或拒绝产物 | 支持 pending、approved、rejected、revision_requested |
| P0-9 | 作为平台用户，我可以创建 Agent 和 Agent Team | 支持 Main Agent + ≥1 Subagent；售前 Pack 提供模板优先体验 |
| P0-10 | 作为用户，我可以为 Agent/Team 绑定授权 Skill/Plugin | 只能绑定 approved 且未 deprecated 的版本 |
| P0-11 | 作为用户，我可以上传私有 Skill/Plugin | 默认仅允许 declarative-only；上传前必须扫描；危险能力进入 quarantine 或拒绝 |
| P0-12 | 作为普通用户，我只能看到系统 Skill/Plugin 安全元信息 | API 仅返回 id、name、description、version、status、owner/type；不返回源码、路径、脚本、references |
| P0-13 | 作为 Skill/Plugin Admin，我可以上架、审批、弃用系统 Skill/Plugin | 每个版本记录 checksum、approved_by、approved_at、scan result、deprecated |
| P0-14 | 作为系统，我可以在 worker-only runtime 执行系统 Skill/Plugin | 系统源码不复制到用户可见 workspace；运行路径不暴露给用户 API 或 artifact 下载 |
| P0-15 | 作为系统，我可以阻止 workspace 越权访问 | `..`、绝对路径、symlink、跨用户路径、取消后写 artifact 均被拒绝并记录 |
| P0-16 | 作为系统，我可以执行 Quality Review Agent | 每个售前核心产物生成结构化 review result；review 缺失或 malformed 时 fail closed |
| P0-17 | 作为管理员，我可以查看审计日志 | 包含 Run、Skill/Plugin 使用、文件访问、安全拒绝、扫描结果、质量评审 |
| P0-18 | 作为平台，我可以限制资源消耗 | 文件大小、Run 时长、token、并发、单用户 Run 数进入 MVP 限制 |
| P0-19 | 作为用户，我可以取消正在运行的 Run | 取消后状态进入 cancelling/cancelled，Worker 停止后续 artifact 写入 |
| P0-20 | 作为运维/管理员，我可以看到 day-1 metrics、alerts、runbooks | 至少覆盖 Run、转换、扫描、安全拦截、质量评审、成本/资源 |

### 6.2 P1 - Should Have

| # | User Story | Acceptance Criteria |
|---|---|---|
| P1-1 | 用户可预览转换结果 | 转换完成后展示原始文件和 extracted text 对照 |
| P1-2 | 用户可中途添加/移除 Conversation 文件 | 文件变更生成新 input manifest version |
| P1-3 | 用户可查看 Run 成本估算 | Run 详情展示 token、模型、估算成本 |
| P1-4 | 高级用户可管理团队 Workflow Pack 配置 | 可分配团队可用 Pack 和模板 |
| P1-5 | 管理员可搜索事件和审计日志 | 支持按 user、run、artifact、skill/plugin、error class 查询 |

### 6.3 P2 - Future

| # | User Story | Acceptance Criteria |
|---|---|---|
| P2-1 | Finished PPT rendering | 将 structured Markdown PPT outline 转成可编辑品牌化 deck |
| P2-2 | Agent/Workflow Pack 克隆 | 复制配置并保留版本来源 |
| P2-3 | Agent 配置分享 | 支持只读分享和权限控制 |
| P2-4 | Admin analytics dashboard | 图表化展示使用量、成本、质量、失败率 |
| P2-5 | OCR 图片识别 | 图片上传后提取 OCR 文本 |
| P2-6 | Plugin marketplace expansion | 发布、审核、评分、兼容性、下架影响分析 |
| P2-7 | 对象存储适配 | 将本地文件系统迁移到对象存储 |

---

## 7. MVP Reference Workflow: 售前客户分析与 AI 方案生成 Pack

### 7.1 Workflow Goal

给定客户需求文档和可选补充资料，生成一套可追溯、可评审、可修改的售前首版方案包。

### 7.2 Valid Input Contract

售前 Run 必须至少包含一个有效客户需求文档。

| 输入类型 | 必填 | 支持格式 | 要求 |
|---|---|---|---|
| 客户需求文档 | 是 | doc/docx/pdf/md/txt | 至少包含客户名称、业务背景、需求或项目背景之一 |
| 客户现有材料 | 否 | ppt/pptx/pdf/doc/docx | 用于补充背景 |
| 访谈纪要 | 否 | md/txt/doc/docx | 用于需求分析 |
| 历史方案 | 否 | ppt/pptx/pdf/doc/docx | 用于风格和方案参考 |
| 行业研究资料 | 否 | pdf/md/txt/xlsx | 用于 market scan |
| 客户公开信息摘要 | 否 | md/txt/url metadata | 当互联网研究不可用时使用 |

Unsupported cases:

- 空文件。
- 损坏文件。
- 密码保护且无法解析的文件。
- 未启用 OCR 时的纯图片输入。
- 包含公司政策禁止上传的数据类型。

Weak input behavior:

- 如果输入不足以生成完整方案包，Run 只生成 clarification question list，不生成完整客户方案。
- Quality Review Agent 必须拒绝基于弱输入生成的完整方案包。

### 7.3 Required Artifacts

| Artifact | Required Sections | Review Target |
|---|---|---|
| Market Scan | 客户摘要、行业背景、竞争/替代、买方力量、AI 机会地图、关键假设 | 证据质量、具体性、输入引用 |
| Interview Guide | 访谈目标、干系人问题、发现路径、风险问题、预期信号 | 未知问题覆盖、问题质量 |
| Requirement Analysis | 痛点、业务流程、约束、干系人、成功指标、风险 | 从输入到需求的映射是否正确 |
| AI Solution Outline | AI 能力、流程匹配、数据需求、集成需求、风险、落地路径 | 业务匹配、可行性、安全边界 |
| Structured Markdown PPT Outline | slide title、slide purpose、key bullets、source artifact references | 高管叙事、逻辑流、来源引用 |

### 7.4 Workflow Flow

```text
用户选择售前 Workflow Pack
  -> 上传客户资料
  -> 输入校验与转换
  -> 创建 Conversation + input manifest
  -> Main Agent 制定计划
  -> Subagents 生成 5 个核心产物
  -> Quality Review Agent 审查产物
  -> 用户查看 findings 并请求修订/批准
  -> 导出已批准方案包
```

### 7.5 Pilot Acceptance

| Gate | Criteria |
|---|---|
| Pilot scope | 2-3 个真实售前机会 |
| Cycle time | 有效输入上传后 1 个工作日内生成首版包 |
| Quality target | 3 个 pilot 中至少 2 个经 ≤1 轮修改后被售前负责人接受 |
| Failure threshold | 少于 2 个被接受则 MVP 未验证，必须修订 workflow/rubric |

---

## 8. Solution Overview

### 8.1 总体架构

```text
Web Layer
  ├── Admin Console
  └── User Client
        |
        v
API Server
  ├── Auth / RBAC
  ├── Workflow Pack API
  ├── Agent / Team API
  ├── Skill / Plugin Metadata API
  ├── File / Conversation API
  ├── Run / Artifact API
  └── Audit API
        |
        v
Run Service
  ├── state machine
  ├── idempotency
  ├── limits / cancellation
  ├── queue dispatch
  └── named error mapping
        |
        v
Worker Runtime Sandbox
  ├── worker-only Skill/Plugin execution area
  ├── file access guard
  ├── path/symlink escape prevention
  ├── source protection
  └── event/provenance writer
        |
        v
Claude Agent SDK
  ├── Main Agent
  ├── Subagents
  └── Quality Review Agent
        |
        v
Storage
  ├── Database: users, packs, agents, runs, events, artifacts, reviews
  ├── Filesystem: uploads, extracted files, workspace inputs, artifacts
  └── Registry: server-only Skill/Plugin source, versions, checksums
```

### 8.2 Source Protection Model

系统 Skill/Plugin 源码保护是 MVP 安全边界，不是 UI 细节。

规则：

1. 系统 Skill/Plugin 源码存储在 server-only Registry。
2. 普通用户只能看到安全元信息：id、name、description、version、status、owner/type。
3. 普通用户不能读取 Registry path、源码文件、examples、scripts、references、raw checksum。
4. 运行时如需复制源码，必须复制到 worker-only isolated execution area。
5. worker-only execution path 不能通过用户 API、artifact 下载、workspace 浏览暴露。
6. 如果 Claude Agent SDK 技术上必须在某路径放置 Skill 文件，该路径必须不属于用户可见 workspace，并在 Run 后清理和校验。
7. 清理失败时 Run 标记 operational warning，并向管理员告警。

### 8.3 Workspace Model

用户可见 conversation workspace 不保存系统 Skill/Plugin 源码。

```text
/data/agent-platform/
├── uploads/{user_id}/{file_id}/
│   ├── original.ext
│   ├── metadata.json
│   └── extracted/
├── workspaces/{user_id}/conversations/{conversation_id}/
│   ├── inputs/             # 只读，授权输入视图
│   ├── working/            # Agent 工作目录，受 guard 限制
│   ├── artifacts/          # 产物输出
│   └── logs/events.jsonl   # 辅助日志，DB events 为主
├── registry/
│   ├── skills/             # server-only
│   └── plugins/            # server-only
└── runtime/{run_id}/        # worker-only isolated execution area
```

---

## 9. Run Lifecycle & State Machine

### 9.1 Run States

```text
created
  -> queued
  -> running
      -> completed
      -> failed
      -> timeout
      -> cancelling
          -> cancelled
```

### 9.2 State Rules

| Rule | Requirement |
|---|---|
| Idempotency | 用户重复提交同一消息/同一 idempotency key 时，返回已有 Run，不创建重复 Run |
| Cancellation | running Run 被取消后进入 cancelling；Worker 收到 cancel signal 后停止新工具调用和新 artifact 写入 |
| Partial artifacts | timeout/failed/cancelled Run 中的 partial artifact 默认不可批准，需标记 partial/unsafe |
| Retry | Retry 创建新 Run，并关联 parent_run_id |
| Terminal states | completed/failed/timeout/cancelled 为终态，不可继续写入 artifact |
| Artifact write guard | cancelled 后写入 artifact 触发 `ArtifactWriteAfterCancelError` |

---

## 10. Error & Rescue Registry

| Codepath | Error Class | Trigger | Rescue Action | User Sees |
|---|---|---|---|---|
| File upload | `UnsupportedFileTypeError` | 不支持格式 | 拒绝上传，记录事件 | 文件格式暂不支持 |
| File upload | `FileTooLargeError` | 超过大小限制 | 拒绝上传 | 文件超过大小限制 |
| File conversion | `FileParseError` | 文件损坏/无法解析 | 转换失败，可重试或换文件 | 文件解析失败 |
| File conversion | `PasswordProtectedFileError` | 密码文件无法解析 | 请求用户解除保护后重传 | 文件受密码保护 |
| Input contract | `InsufficientInputError` | 信息不足 | 只生成澄清问题 | 输入信息不足，需要补充 |
| Skill/Plugin binding | `CapabilityNotAuthorizedError` | 未授权能力包 | 阻止绑定，记录审计 | 该能力未授权 |
| Skill/Plugin scan | `CapabilityScanFailedError` | 安全扫描失败 | 拒绝或 quarantine | Skill/Plugin 未通过安全扫描 |
| Skill/Plugin runtime | `CapabilitySourceProtectedError` | 用户尝试读系统源码 | 阻止访问，安全告警 | 系统能力源码不可查看 |
| Workspace guard | `WorkspaceAccessDeniedError` | 跨路径/跨用户/symlink | 拒绝访问，记录路径和 actor | 文件访问被拒绝 |
| Agent SDK | `ModelTimeoutError` | 模型响应超时 | 安全重试或 timeout | Agent 响应超时 |
| Agent SDK | `ModelRateLimitError` | 模型限流 | backoff retry 后失败 | 服务繁忙，请稍后重试 |
| Subagent | `MalformedAgentOutputError` | 输出结构不合法 | retry 或 revision_requested | 子任务输出异常 |
| Review Agent | `RubricMissingError` | 缺少评审规则 | fail closed | 缺少评审规则，无法批准产物 |
| Review Agent | `ReviewOutputMalformedError` | 评审输出不合法 | fail closed | 评审结果异常 |
| Artifact | `ArtifactProvenanceMissingError` | provenance 缺失 | 禁止批准 | 产物缺少来源信息 |
| Artifact | `ArtifactWriteAfterCancelError` | 取消后写入 | 阻止写入，审计 | Run 已取消，产物写入被阻止 |

所有 error event 必须包含：user_id、run_id、conversation_id、workflow_pack_id、error_class、safe_message、debug_context、timestamp。

---

## 11. Skill/Plugin Security & Governance

### 11.1 Upload and Approval Pipeline

```text
Upload Skill/Plugin
  -> schema validation
  -> static scan
  -> secret scan
  -> prompt/security scan
  -> policy check
  -> quarantine or approve
  -> version/checksum created
  -> available for binding
```

### 11.2 Security Controls

| Control | MVP Requirement |
|---|---|
| Declarative-only default | 普通用户上传的私有 Skill/Plugin 默认不允许 scripts/network/system commands |
| Admin approval | 需要脚本、网络或外部工具的能力包必须由管理员批准 |
| Scanning | 每次上传、版本变更、系统上架都必须扫描 |
| Sandbox | 运行时执行必须经过 worker sandbox 和 file access guard |
| Version pinning | Run 记录精确使用版本，不随最新版本漂移 |
| Deprecation | deprecated 版本不可新绑定，但历史 Run 可追溯 |
| Audit | 上传、扫描、审批、绑定、执行、拒绝都记录事件 |

### 11.3 Suggested Scanner Stack

PRD 不绑定单一供应商，但 MVP 应支持接入以下类型工具：

| Scanner Type | Purpose | Examples |
|---|---|---|
| Agent/Skill scanner | 检测 prompt injection、恶意 instruction、agent capability risk | Snyk Agent Scan、Cisco AI Skill Scanner、Alice AI Skill Security Scanner |
| Static code scanner | 检测危险函数、路径穿越、命令执行、网络访问 | Semgrep、CodeQL、Bandit、njsscan |
| Secret scanner | 检测 API key、token、credential | Gitleaks、TruffleHog |
| Runtime guardrail | 运行时策略拦截 | LLM Guard、NeMo Guardrails、Agent Governance Toolkit |

Scanner 是防线之一，不是安全边界。最终安全边界仍由权限、沙箱、source protection、文件访问 guard 和审计共同保证。

---

## 12. Data Flow & Interaction Edge Cases

### 12.1 Data Flow

```text
INPUT
  -> validation
  -> conversion
  -> extracted text
  -> input manifest
  -> Run
  -> Agent/Subagent outputs
  -> artifacts + provenance
  -> Quality Review Agent
  -> human review
  -> export
```

### 12.2 Edge Case Matrix

| Interaction | Edge Case | Required Behavior |
|---|---|---|
| Upload | Empty file | Reject with `InsufficientInputError` or file validation error |
| Upload | Unsupported format | Reject with `UnsupportedFileTypeError` |
| Upload | Corrupt/password file | Conversion failed with named error |
| Submit Run | Double-click | Idempotency key returns existing Run |
| Submit Run | Weak input | Generate clarification questions only |
| Run | User cancels | Stop new work, prevent new artifact writes |
| Run | Timeout | Mark partial artifacts unsafe |
| Run | Retry | Create new Run with parent_run_id |
| Artifact | Missing provenance | Cannot approve |
| Review | Missing rubric | Fail closed to revision_requested |
| Export | Artifact rejected | Export blocked or requires explicit warning |
| Skill/Plugin | Deprecated version | Existing Run traceable, new binding blocked |
| Workspace | Symlink escape | Deny and log security event |

---

## 13. Observability & Operations

### 13.1 Day-1 Metrics

| Metric | Purpose |
|---|---|
| Run success/fail/cancel/timeout rate | 平台运行健康 |
| File conversion success/fail by format | 文档处理健康 |
| Skill/Plugin scan pass/fail/reason | 能力包安全健康 |
| Workspace access denied events | 安全边界健康 |
| Token/time/cost per Run and per user | 资源与成本控制 |
| Subagent failure rate by Workflow Pack | Agent Team 质量 |
| Quality Review pass/fail/revision rate | 产物质量趋势 |
| Artifact approval/rejection rate | 用户接受度 |
| Sandbox cleanup warning count | 源码保护和运行环境健康 |

### 13.2 Alerts

| Alert | Trigger |
|---|---|
| Security boundary violation | 任意未预期 workspace/registry 访问 |
| Conversion failure spike | 某格式失败率异常升高 |
| Run timeout spike | timeout rate 超阈值 |
| Scan failure spike | Skill/Plugin 上传中高危失败异常 |
| Quality rejection spike | Review Agent rejection rate 异常升高 |
| Cost anomaly | 单用户/单 Run token 或耗时超阈值 |
| Cleanup failure | worker-only runtime 清理失败 |

### 13.3 Runbooks

MVP 必须提供以下 runbook：

1. Run failed/timeout 排查。
2. 文件转换失败排查。
3. Skill/Plugin scan failed 处理。
4. Workspace access denied 安全事件处理。
5. Quality Review Agent 大量拒绝处理。
6. Run 成本异常处理。
7. Worker runtime cleanup failed 处理。

---

## 14. Testing & Evaluation Matrix

### 14.1 Required Test Types

| Area | Unit | Integration | E2E | Abuse/Security | Eval |
|---|---|---|---|---|---|
| Auth/RBAC | Yes | Yes | Yes | Cross-user access | No |
| File upload/conversion | Yes | Yes | Yes | Corrupt/large/password files | No |
| Workflow Pack | Yes | Yes | Yes | Invalid input contract | Yes |
| Run state machine | Yes | Yes | Yes | duplicate/cancel/timeout | No |
| Agent Team | Yes | Yes | Yes | recursive subagent blocked | Yes |
| Skill/Plugin registry | Yes | Yes | Yes | source download attempts | No |
| Skill/Plugin scanning | Yes | Yes | No | malicious payloads/secrets | No |
| Worker sandbox | Yes | Yes | Yes | path/symlink/absolute escape | No |
| Artifact provenance | Yes | Yes | Yes | missing provenance approval blocked | No |
| Quality Review Agent | Yes | Yes | Yes | malformed review output | Yes |
| Observability | Yes | Yes | No | event omission detection | No |

### 14.2 Quality Review Agent Evals

Quality Review Agent 必须至少覆盖：

1. 好样本：高质量 market scan 应通过。
2. 弱输入样本：缺少客户背景时必须拒绝完整方案。
3. 幻觉样本：产物包含输入中不存在事实时必须指出。
4. 缺 provenance 样本：必须 fail closed。
5. 空泛方案样本：缺少具体客户痛点和方案匹配时必须 revision_requested。
6. 风险缺失样本：AI 方案未写数据、集成、安全风险时必须指出。

### 14.3 Security Abuse Cases

| Case | Expected |
|---|---|
| Skill prompt 要求读取 `/data/agent-platform/skills/registry` | 拒绝并记录 |
| Plugin 脚本尝试 `../` 路径逃逸 | 拒绝并记录 |
| Symlink 指向其他用户 workspace | 拒绝并记录 |
| Artifact 中包含系统 Skill 源码片段 | 阻断或标记安全事件 |
| 用户尝试通过 API 获取 system Skill source path | 返回 403/404 safe response |
| Run 取消后 Worker 继续写 artifact | 阻止并记录 `ArtifactWriteAfterCancelError` |

---

## 15. Deployment & Rollout

### 15.1 MVP Gate Sequence

| Gate | What It Proves | Exit Criteria |
|---|---|---|
| Sandbox gate | 平台可安全运行 Agent、文件和受保护能力包 | 路径逃逸、symlink、源码访问、取消写入全部被拦截 |
| Provenance/versioning gate | 平台能解释产物来源 | 100% artifacts 有 provenance，100% Skill/Plugin 有版本/checksum |
| Presales workflow gate | 平台能生成 5 个售前核心产物 | 售前 Pack E2E 通过 |
| Quality review gate | 系统能识别弱产物 | Review Agent eval 通过 |
| Pilot gate | 真实售前场景产生价值 | 2/3 pilot 被接受 |

### 15.2 Rollout Plan

```text
Phase 1: Architecture Spike
  -> fake/sample data only
  -> SDK, subagent, sandbox, provenance spike

Phase 2: Platform MVP
  -> seed system Skills/Plugins
  -> enable presales Workflow Pack behind feature flag
  -> pilot cohort: 2-3 presales users
  -> run 2-3 real opportunities
  -> evaluate cycle time, quality, safety events

Phase 3: Governance Hardening
  -> broaden team usage
  -> improve audit/search
  -> refine Skill/Plugin approval

Phase 4: Production Readiness
  -> object storage adapter
  -> dashboard
  -> scale/concurrency
  -> more Workflow Packs
```

### 15.3 Rollback Flow

```text
Incident detected
  -> disable new Runs via feature flag
  -> preserve uploads/artifacts/events
  -> hide unapproved or unsafe artifacts if needed
  -> rollback app
  -> keep provenance readable
  -> audit affected Runs
  -> re-enable only after gate passes
```

---

## 16. Timeline & Phasing

| 阶段 | 目标 | PRD 范围 |
|---|---|---|
| Phase 1: Architecture Spike | 验证核心安全和运行链路 | Claude SDK、Subagent、worker-only runtime、sandbox、source protection、provenance spike |
| Phase 2: Platform MVP | 售前 Workflow Pack 真实 pilot | P0 全部需求、售前 5 artifacts、Quality Review Agent、资源限制、day-1 ops |
| Phase 3: Governance Hardening | 内部真实使用治理 | 审计搜索、团队管理、Skill/Plugin 流程完善、更多错误处理和 eval |
| Phase 4: Production Readiness | 扩大用户和 Workflow Packs | 对象存储、dashboard、并发扩展、更多 Workflow Pack、P2 功能 |

---

## 17. MVP Acceptance Checklist

### Platform

- [ ] 支持多用户注册和登录。
- [ ] 用户文档和 workspace 完全隔离。
- [ ] 支持 Workflow Pack-first 首页。
- [ ] 用户可上传并转换支持格式文档。
- [ ] 用户可创建 Agent 和 Agent Team。
- [ ] Main Agent 可调度 Subagent，Subagent 不能递归委派。
- [ ] Skill/Plugin 均支持版本、checksum、审批、扫描、弃用。
- [ ] 系统 Skill/Plugin 仅展示安全元信息，不暴露源码或路径。
- [ ] 系统 Skill/Plugin 在 worker-only runtime 执行，不进入用户可见 workspace。
- [ ] Run 状态机、idempotency、取消、timeout、partial artifact 规则实现。
- [ ] Run 失败有 named error class。
- [ ] 资源限制进入 MVP：文件大小、Run 时长、token、并发。

### Presales Workflow Pack

- [ ] 售前 Workflow Pack 可用。
- [ ] 有效输入校验和弱输入处理可用。
- [ ] 生成 5 个核心 artifacts。
- [ ] 每个 artifact 有 provenance 和 review_status。
- [ ] Quality Review Agent 输出结构化 review result。
- [ ] Human approval required before customer export。
- [ ] Pilot 中 2/3 真实机会经 ≤1 轮修改被售前负责人接受。

### Security & Operations

- [ ] 路径逃逸、绝对路径、symlink、跨用户访问均被拦截。
- [ ] 取消后 artifact 写入被拦截。
- [ ] Skill/Plugin scan pipeline 可用。
- [ ] day-1 metrics、alerts、runbooks 可用。
- [ ] feature flag、pilot cohort、rollback flow 可用。

---

## 18. Open Questions

| # | Question | Owner | Deadline |
|---|---|---|---|
| Q1 | 文档转换服务使用 LibreOffice/Pandoc/其他开源方案还是自研？ | 技术负责人 | Phase 1 |
| Q2 | 单文件大小、总存储、Run token、Run 时长、并发默认限制是多少？ | 产品 + 运维 | Phase 1 |
| Q3 | 公司允许上传哪些客户数据类型？哪些必须禁止？ | 安全/法务/业务 | Phase 1 |
| Q4 | 售前 market scan 和 AI solution 的质量 rubric 由谁最终审批？ | Presales Leader | Phase 1 |
| Q5 | Skill/Plugin 脚本和网络访问的审批标准是什么？ | Skill Admin + Security | Phase 1 |
| Q6 | Agent Team 中 Main Agent 和 Review Agent 使用哪个模型？是否允许用户自定义？ | 技术 + 产品 | Phase 1 |
| Q7 | 是否允许 Agent 访问互联网进行行业研究？如果允许，走哪个受控工具？ | 产品 + 安全 | Phase 1 |
| Q8 | structured Markdown PPT outline 的具体模板格式是什么？ | 产品 + 售前 | Phase 2 |

---

## 19. Deferred TODOs

| TODO | Priority | Reason |
|---|---|---|
| Finished PPT rendering | P2 | 先验证内容质量，再做品牌化 deck 生成 |
| Plugin marketplace expansion | P3 | 先证明 Plugin 治理和运行安全 |
| Admin analytics dashboard | P2 | 先确保 metrics/events 可靠，再做图表 |
| Object storage migration | P2/P3 | 本地文件系统先跑通，保留适配边界 |
| More Workflow Packs | P2 | 售前 Pack 通过 pilot 后再复制模式 |

---

## 20. Revision Notes from v1

v2 相比 v1 的主要变化：

1. 从“个人 AI 工作台”调整为“企业内部 Agent Workflow Platform”。
2. 新增 Workflow Pack 概念，售前 Pack 成为 MVP 证明路径。
3. 新增 artifact provenance 和 review_status。
4. 新增 Quality Review Agent。
5. 修正系统 Skill/Plugin 源码保护架构，不再复制到用户可见 workspace。
6. 将 Skill/Plugin 扫描、版本、checksum、审批、弃用纳入 MVP。
7. 将 Run 状态机、资源限制、取消语义和错误分类纳入 MVP。
8. 将 day-1 metrics、alerts、runbooks、feature flags、rollback 纳入 MVP。
9. 增加安全 abuse tests 和 Quality Review Agent evals。
10. 明确 deferred scope，避免 MVP 做 finished PPT rendering、public marketplace、完整 dashboard。
