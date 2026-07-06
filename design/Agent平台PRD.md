# Product Requirements Document: 智能体平台

**作者**: 产品团队
**日期**: 2026-05-08
**状态**: Draft
**相关文档**: [Agent平台技术说明书](./Agent平台技术说明书.md)

---

## 1. Executive Summary

智能体平台是一个基于 Claude Agent SDK 的多用户 Web 平台，允许用户上传私有文档、自定义 Skill/Plugin、创建个性化 Agent 并组建 Agent Team 协作完成任务。平台提供系统级 Skill 和 Plugin 市场供用户选用，同时保障知识产权——系统资产仅展示名称和描述，不可下载源码。第一版聚焦"个人 AI 工作台"场景，支撑从文档上传、Agent 配置、Team 协作到结果产出的完整闭环。

---

## 2. Background & Context

### 2.1 问题空间

当前企业内部使用 AI Agent 面临以下痛点：

| 痛点 | 现状 | 影响 |
|------|------|------|
| **知识私有化困难** | 用户文档散落本地，AI 无法有效利用个人知识库 | Agent 输出缺乏上下文，实用性低 |
| **Agent 定制门槛高** | 创建专用 Agent 需要编写代码、配置环境 | 非技术用户无法自助构建 Agent |
| **多格式文档难处理** | Office 文档、PDF、图片等非结构化数据 | AI 无法直接读取，需人工预处理 |
| **协作缺乏编排** | 复杂任务需要多个 Agent 配合，无统一调度 | 人工拼接结果，效率低、易出错 |
| **Skill 资产无保护** | 企业自研 Skill 涉及核心方法论，直接暴露源文件 | 知识产权泄露风险 |

### 2.2 解决方案

平台提供三层能力解决上述问题：

- **知识层**：用户上传文档（doc/docx/xls/xlsx/pdf/图片），系统自动转为 Markdown/CSV 等结构化文本，注入 Agent 上下文。
- **Agent 层**：用户通过可视化界面创建 Agent，配置 Soul/Identity，绑定 Tool 和 Skill，无需编写代码。
- **协作层**：用户组建 Agent Team，由 Main Agent 自动拆解任务并调度 Subagent 协作完成。

### 2.3 市场定位

面向企业内需要利用 AI 提升个人和团队生产力的知识工作者。区别于通用 ChatBot，本平台以"个人知识库 + 自定义 Agent + 多智能体协作"为核心差异化。

---

## 3. Objectives & Success Metrics

### 3.1 Goals

| # | Goal | Measurement |
|---|------|-------------|
| G1 | 用户可独立上传文档并转为可检索的结构化文本 | 支持 ≥6 种文件格式，单文件处理 ≤30s |
| G2 | 用户可零代码创建并配置个性化 Agent | 从创建到首次对话 ≤3 分钟 |
| G3 | 用户可组建 Agent Team 完成多步骤协作任务 | Team 支持 ≥1 Main + ≥2 Subagent |
| G4 | 系统 Skill/Plugin 资产受保护，仅可见元信息 | 0 次非授权源文件下载 |
| G5 | 多用户隔离，各自 workspace 互不可见 | 0 次跨用户数据泄露 |

### 3.2 Non-Goals

| # | Non-Goal | Rationale |
|---|----------|-----------|
| N1 | Plugin marketplace 公开交易 | 第一版聚焦企业内部使用，不涉及商业化 |
| N2 | 复杂 DAG 工作流引擎 | 使用 Claude Subagent 原生调度，不自研工作流 |
| N3 | 对象存储 / 分布式文件系统 | 第一版使用本地文件系统，后续迁移 |
| N4 | 多租户 SaaS 体系 | 第一版为单组织部署模式 |
| N5 | 实时协同编辑 | 同一 Conversation 内为串行消息模型 |
| N6 | 自定义 Skill 的市场发布与审核 | 用户私有 Skill 仅自己可见可用 |

### 3.3 Success Metrics

| Metric | Current | Target (Phase 2 MVP) | Measurement |
|--------|---------|----------------------|-------------|
| 注册用户数 | 0 | ≥50 | 平台统计 |
| 用户文档上传量 | 0 | ≥200 份 | 平台统计 |
| 用户自建 Agent 数 | 0 | ≥100 | 平台统计 |
| Agent Team 完成率 | N/A | ≥90% Run 状态为 completed | Run 事件流 |
| 文档转换成功率 | N/A | ≥95% | 文件处理日志 |
| 跨用户数据隔离 | N/A | 0 违规事件 | 安全审计 |

---

## 4. Target Users & Segments

### 4.1 用户画像

| 画像 | 描述 | 核心诉求 |
|------|------|----------|
| **知识工作者** | 日常处理大量文档、需要快速提取信息和生成报告 | 上传文档 → Agent 理解 → 自动产出 |
| **业务分析师** | 需要跨多个数据源综合分析 | 多 Agent 协作完成研究 + 分析 + 报告 |
| **Team Lead** | 需要协调团队工作、整合输出 | 组建 Agent Team 自动分配子任务 |
| **系统管理员** | 管理用户、权限、Skill 资产 | 控制台管理、审计日志 |

### 4.2 用户分层

| 层级 | 角色 | 权限范围 |
|------|------|----------|
| 普通用户 | 知识工作者、业务分析师 | 上传文档、创建 Agent/Team、使用系统 Skill |
| 高级用户 | Team Lead | 普通用户权限 + 组建 Team、管理团队 Agent |
| 管理员 | 系统管理员 | 用户管理、Skill/Plugin 上架、审计 |

---

## 5. User Stories & Requirements

### P0 — Must Have

| # | User Story | Acceptance Criteria |
|---|-----------|-------------------|
| P0-1 | 作为用户，我可以注册/登录平台，拥有独立的 workspace | 注册后自动创建用户目录，登录后仅可见自己的资源 |
| P0-2 | 作为用户，我可以上传文档（doc/docx/xls/xlsx/pdf/png/jpg 等），系统自动转换为可检索文本 | 上传后文件进入 uploads/，系统异步转换为 Markdown 或 CSV；支持预览转换结果 |
| P0-3 | 作为用户，我可以在 Conversation 中引用已上传文档，Agent 基于文档内容回答 | 在会话中添加文件到 inputs/，Agent 可读取并引用 |
| P0-4 | 作为用户，我可以创建 Agent，设置名称、描述、Soul（soul.md）和 Identity（identity.md） | 创建表单包含必填项（名称）和选填项（描述、Soul、Identity），保存后即时可用 |
| P0-5 | 作为用户，我可以为自建 Agent 绑定 Tool 和 Skill | 从可用 Tool 列表和授权 Skill 列表中选择；绑定即时生效 |
| P0-6 | 作为用户，我可以创建 Agent Team，指定 Main Agent 和多个 Subagent | Team 配置包含 1 个 Main + ≥1 个 Subagent，每个 Subagent 可独立绑定 Skill |
| P0-7 | 作为用户，我向 Agent Team 发送消息后，Main Agent 自动调度 Subagent 协作完成任务 | Run 创建后可追踪 Main Agent 和 Subagent 的执行状态 |
| P0-8 | 作为用户，我可以查看每次会话的消息历史、Run 记录和事件流 | 会话详情页展示消息时间线、Run 列表和事件详情 |
| P0-9 | 作为用户，我可以下载 Agent 生成的产物（artifacts） | artifacts/ 目录中的文件提供下载链接 |
| P0-10 | 作为用户，我可以上传私有 Skill，仅供自己使用 | Skill 上传后存入用户私有空间，不出现在系统 Skill 列表中 |
| P0-11 | 作为普通用户，我只能看到系统 Skill/Plugin 的名称和描述，无法下载源文件 | API 仅返回 Skill 元信息（name、description），不暴露文件路径和内容 |

### P1 — Should Have

| # | User Story | Acceptance Criteria |
|---|-----------|-------------------|
| P1-1 | 作为用户，我可以在上传文档时预览和确认转换结果 | 转换完成后展示原始文件和转换文本的对照视图 |
| P1-2 | 作为用户，我可以为 Agent 设置使用限额（最大 Run 数、单次最大 Token） | 超出限额后 Run 自动中止并提示 |
| P1-3 | 作为用户，我可以在会话中中途添加或移除文件 | 文件变更后 Agent 实时感知 |
| P1-4 | 作为用户，我可以查看 Run 的成本估算（Token 消耗） | Run 详情展示 Token 用量和估算费用 |
| P1-5 | 作为用户，我可以取消正在运行的 Run | 取消后 Worker 停止执行并标记状态为 cancelled |
| P1-6 | 作为管理员，我可以上架/下架系统 Skill 和 Plugin | 上架后所有用户可见元信息；下架后已绑定的不受影响 |
| P1-7 | 作为管理员，我可以查看用户的 Run 审计日志 | 审计日志包含用户、时间、Run 状态、Skill 使用、文件访问记录 |

### P2 — Nice to Have / Future

| # | User Story | Acceptance Criteria |
|---|-----------|-------------------|
| P2-1 | 作为用户，我可以克隆已有 Agent 作为模板快速创建 | 克隆后 Soul/Identity/Tool/Skill 配置一并复制 |
| P2-2 | 作为用户，我可以分享 Agent 配置给其他用户（只读链接） | 接收方可查看配置但不能修改 |
| P2-3 | 作为用户，我可以在多个 Conversation 间复用同一个 workspace | workspace 持久化直到用户手动清理 |
| P2-4 | 作为管理员，我可以查看平台使用统计仪表板 | 展示活跃用户、Run 数量、Token 消耗、Skill 使用排行 |
| P2-5 | 作为用户，我可以使用 OCR 识别图片中的文字 | 上传图片后额外提取 OCR 文本 |

---

## 6. Solution Overview

### 6.1 总体架构

```
┌─────────────────────────────────────────────────┐
│                 Web Layer                         │
│  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Admin Console │  │      User Client          │  │
│  └──────┬───────┘  └───────────┬──────────────┘  │
├─────────┼──────────────────────┼──────────────────┤
│         ▼                      ▼                  │
│  ┌──────────────────────────────────────────┐    │
│  │            API Server                     │    │
│  │  Auth / User / Agent / Team / File / Run  │    │
│  └──────────────────┬───────────────────────┘    │
├─────────────────────┼────────────────────────────┤
│                     ▼                             │
│  ┌──────────────────────────────────────────┐    │
│  │  Run Service  │  File Service             │    │
│  │  (状态机/队列) │  (上传/转换/注入)         │    │
│  └──────────────────┬───────────────────────┘    │
├─────────────────────┼────────────────────────────┤
│                     ▼                             │
│  ┌──────────────────────────────────────────┐    │
│  │       Agent Runtime Worker                │    │
│  │  (权限校验 / Skill注入 / 事件监听)         │    │
│  └──────────────────┬───────────────────────┘    │
├─────────────────────┼────────────────────────────┤
│                     ▼                             │
│  ┌──────────────────────────────────────────┐    │
│  │        Claude Agent SDK                   │    │
│  │  Main Agent ──▶ Subagent A / B / C        │    │
│  └──────────────────────────────────────────┘    │
├──────────────────────────────────────────────────┤
│                Storage Layer                      │
│  ┌─────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │   DB    │ │Uploads/  │ │  Workspaces/      │  │
│  │         │ │{user_id}/│ │  {user_id}/       │  │
│  │ agent_  │ │{file_id}/│ │  conversations/   │  │
│  │ events  │ │          │ │  {conv_id}/       │  │
│  └─────────┘ └──────────┘ └──────────────────┘  │
└──────────────────────────────────────────────────┘
```

### 6.2 核心功能模块

#### 6.2.1 用户与多租户隔离

| 维度 | 方案 |
|------|------|
| 用户认证 | 基于 JWT 的认证体系，支持用户名/密码登录 |
| 资源隔离 | 每个用户独立 uploads/ 和 workspaces/ 目录 |
| 权限模型 | 普通用户 / 管理员两级 RBAC（第一版） |
| Session 管理 | 登录态 TTL 可配置，支持主动登出 |

#### 6.2.2 文档上传与转换

支持的输入格式和对应的转换目标：

| 输入格式 | 转换目标 | 转换方式 |
|----------|----------|----------|
| .doc / .docx | Markdown (.md) | 文档解析 → Markdown，保留标题/表格/列表结构 |
| .xls / .xlsx | CSV (.csv) 或 Markdown 表格 | 每个 Sheet → 独立 CSV 文件 |
| .pdf | Markdown (.md) | PDF 文本提取 → Markdown |
| .png / .jpg / .jpeg | Markdown (.md) | OCR 识别（P2）/ 图片描述嵌入 |

**文件生命周期**：
```
用户上传 → uploads/{user_id}/{file_id}/original.ext
         → 异步转换 → uploads/{user_id}/{file_id}/extracted/*.md|*.csv
         → 用户引用 → 复制到 conversations/{conv_id}/inputs/
         → Agent 读取 inputs/ 中的文本文件
```

#### 6.2.3 Agent 创建与配置

Agent 配置模型：

| 配置项 | 说明 | 必填 |
|--------|------|------|
| 名称 | Agent 展示名称 | 是 |
| 描述 | Agent 用途说明 | 否 |
| Soul（soul.md） | Agent 人格定义——语气、风格、行为准则 | 否 |
| Identity（identity.md） | Agent 身份定义——角色、专业领域、知识边界 | 否 |
| Tools | 可调用的工具列表 | 否 |
| Skills | 绑定的 Skill（从用户私有 + 系统授权中选择） | 否 |
| Model | 使用的模型及参数（temperature、max_tokens 等） | 否 |

**Soul.md 示例结构**：
```markdown
# Soul
- 语气：专业但不失亲和
- 风格：简洁直接，避免冗余
- 原则：不确定时主动说明，不编造信息
```

**Identity.md 示例结构**：
```markdown
# Identity
- 角色：财务分析助理
- 专业领域：财务报表分析、税务合规
- 知识边界：仅基于用户提供的文档和公开会计准则
```

#### 6.2.4 Skill 与 Plugin 管理

| 资产类型 | 来源 | 可见范围 | 用户权限 |
|----------|------|----------|----------|
| 系统 Skill | 管理员上架 | 所有用户可见名称+描述 | 浏览、绑定到 Agent |
| 系统 Plugin | 管理员上架 | 所有用户可见名称+描述 | 浏览、绑定到 Agent |
| 私有 Skill | 用户上传 | 仅上传者可见 | 完全控制（上传/编辑/删除/绑定） |
| 私有 Plugin | 用户上传 | 仅上传者可见 | 完全控制（上传/编辑/删除/绑定） |

**安全规则**：
- 系统 Skill/Plugin 的源文件存储在 Skill Registry（`/data/agent-platform/skills/registry/`），用户无权直接访问
- API 返回的系统 Skill/Plugin 仅包含：id、name、description、version
- 运行时注入时，Skill 内容复制到用户 workspace 的 `.claude/skills/` 目录，Run 结束后由 Worker 决定是否保留
- 所有 Skill 注入记录 `skill.injected` 事件

#### 6.2.5 Agent Team 协作

Team 模型：
```
Agent Team
├── Main Agent（必选，1 个）
│   - 理解用户请求
│   - 规划任务分解
│   - 调度 Subagent
│   - 整合输出
├── Subagent A
│   - 绑定 Skill X, Y
│   - 绑定 Tool P
├── Subagent B
│   - 绑定 Skill Z
│   - 绑定 Tool Q
└── Subagent C ...
```

**约束**：
- Subagent 不能调用其他 Subagent（禁止递归委派）
- Subagent 不能使用 Agent Tool
- Main Agent 通过 Claude Agent SDK 的 subagent 机制调度
- 所有 Subagent 共享当前 Conversation 的 workspace

#### 6.2.6 Workspace 与文件管理

每个 Conversation 的 workspace 结构：
```
conversations/{conversation_id}/
├── .claude/skills/     ← 授权 Skill 副本（只读）
├── inputs/             ← 会话文件视图（只读）
├── working/            ← Agent 工作目录（读写）
├── artifacts/          ← 产物输出（写入）
└── logs/events.jsonl   ← 运行日志
```

**跨用户隔离保证**：
```
/data/agent-platform/
├── uploads/{user_id}/           ← 用户 A 无法访问用户 B 的 uploads
├── workspaces/{user_id}/        ← 用户 A 无法访问用户 B 的 workspace
├── skills/registry/             ← 系统 Skill 仅管理员可读写
└── skills/user/{user_id}/       ← 用户私有 Skill
```

### 6.3 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Agent 运行时 | Claude Agent SDK | 原生支持 Main Agent + Subagent 协作，无需自研调度 |
| 文件存储 | 本地文件系统 | 第一版简化部署，后续可平滑迁移至对象存储 |
| 文档转换 | 异步任务 | 大文件转换不阻塞用户操作；转换结果缓存至 extracted/ |
| Skill 保护 | 元信息可见 + 运行时注入 | 既满足用户选型需求，又保护 Skill 源码 |
| 事件流 | 数据库为主 + JSONL 为辅 | 数据库保证查询性能，JSONL 保证日志完整性 |
| 安全隔离 | 文件系统路径隔离 + Runtime 拦截 | 双重保障，不依赖 Prompt 约束 |

---

## 7. Open Questions

| # | Question | Owner | Deadline |
|---|----------|-------|----------|
| Q1 | 文档转换服务是否使用现有开源方案（如 LibreOffice + Pandoc）还是自研？ | 技术负责人 | Phase 1 |
| Q2 | 单用户 workspace 存储配额如何设定？默认值和管理员调整策略？ | 产品 + 运维 | Phase 2 |
| Q3 | 上传文件大小上限？单个文件和总量限制？ | 产品 | Phase 2 |
| Q4 | 系统 Skill 的上架审核流程——需要哪些角色审批？ | 管理员 | Phase 2 |
| Q5 | 用户私有 Skill 是否允许分享给特定用户/团队？还是严格私有？ | 产品 | Phase 2 |
| Q6 | Agent Team 中 Main Agent 选择哪个模型？是否允许用户自定义？ | 技术 + 产品 | Phase 1 |
| Q7 | 是否需要支持 Agent 对话的分享/导出功能？ | 产品 | Phase 3 |

---

## 8. Timeline & Phasing

与[技术说明书](./Agent平台技术说明书.md)第 9 节实施阶段对齐：

| 阶段 | 目标 | PRD 范围 | 预计周期 |
|------|------|----------|----------|
| **Phase 1: Architecture Spike** | 技术验证 | P0-4~P0-7 核心链路（Agent创建→Team→Run）打通 | 2-3 周 |
| **Phase 2: Platform MVP** | 最小可用产品 | 全部 P0 需求 + P1-1~P1-4 | 6-8 周 |
| **Phase 3: Governance Hardening** | 治理加固 | P1-5~P1-7 管理功能 + 审计 | 4-6 周 |
| **Phase 4: Production Readiness** | 生产就绪 | P2 需求 + 性能优化 + 对象存储 | 4-6 周 |

**Phase 2 MVP 验收标准**（与技术说明书第 10 节对齐）：

- [ ] 支持多用户注册和登录
- [ ] 用户可上传 ≥6 种格式文档，系统自动转换为文本
- [ ] 用户可创建 Agent，配置 Soul/Identity，绑定 Tool/Skill
- [ ] 用户可创建 Agent Team（≥1 Main + ≥2 Subagent）
- [ ] Main Agent 可根据用户请求调度不同 Subagent
- [ ] Subagent 使用各自绑定的 Skill，且不能调用其他 Subagent
- [ ] 用户文档和 workspace 完全隔离
- [ ] 系统 Skill/Plugin 仅展示名称和描述，不可下载源文件
- [ ] 用户可查看 Run 事件流（Main Agent、Subagent、Tool 调用）
- [ ] Run 失败时能定位失败层级
