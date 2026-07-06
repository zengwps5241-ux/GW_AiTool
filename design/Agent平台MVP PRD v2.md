# Product Requirements Document: 智能体平台 MVP v2

**作者**: 产品团队
**日期**: 2026-05-10
**状态**: Draft
**基于**: [Agent平台MVP PRD v1](./Agent平台MVP%20PRD.md)
**版本历史**: v1→v2 补充技术选型、项目结构、测试策略、命令集、边界约束；v2.1 收敛 P0 范围、统一验收口径、补齐 Phase 1 默认决策

---

## 1. Executive Summary

智能体平台 MVP 是面向企业内部的多用户 Agent Web 平台，以**预配置的 Expert Agent**作为用户可见产品接口。

MVP 聚焦第一个 Expert Agent：**售前专家 Agent**，能完成客户调研、需求分析、AI 机会挖掘、AI 方案生成的全流程，产出可追溯、可审阅、可修改的方案包。

核心目标：将方案包周期从约 1 周缩短至 1 个工作日内，方案质量稳定可控。

---

## 2. Background & Context

### 2.1 核心痛点

| 角色 | 当前流程 | 痛点 |
|---|---|---|
| 售前工程师 | 收到客户需求后，手工调研、编写 market scan、访谈材料、需求分析、AI 方案和 PPT | 每个售前能力不同，质量不稳定，耗时约 1 周 |
| 售前负责人 | 保证团队方案质量和交付周期 | 质量控制依赖人工，复用方法论困难 |
| 销售负责人 | 了解客户痛点，挖掘AI机会 | 对客户缺乏整体的了解，不知道有哪些AI商机，Agent使用能力偏弱 |

### 2.2 MVP 验证目标

- 2-3 个真实售前机会 pilot
- 有效输入上传后 1 个工作日内生成首版包
- 3 个 pilot 中至少 2 个经 ≤1 轮修改后被接受
- 针对重点关注的行业、公司和场景，生成相关分析调研、AI机会矩阵文档，供销售负责人参考

### 2.3 MVP Scope Definition

MVP 的首要目标是验证“预配置 Expert Agent 能否安全、稳定地产生可审阅的售前方案包”，而不是一次性完成完整 Agent 平台。

| 层级 | 范围 |
|---|---|
| P0 必须交付 | 多用户登录与 workspace 隔离、客户资料上传与转换、售前专家 Agent 一键运行，根据skills，plugins生成售前核心交付物，并由人提供反馈，持续优化生成物。取消 Run、day-1 metrics |
| P1 延后交付 | 自定义 Agent/Agent Team 创建、用户绑定 Skill/Plugin、Skill/Plugin 审批/弃用完整生命周期、转换结果预览、成本估算、PPT/PPTX 转换 |
| 明确不做 | 插件市场、租户计费、多人实时协作、移动端、国际化、SSO/OIDC、K8s 生产化部署 |

---

## 3. Objectives & Success Metrics

### 3.1 Product Goals

| # | Goal | Measurement |
|---|---|---|
| G1 | 用户可上传私有文档并转换为 Agent 可用文本 | P0 支持 doc/docx/xls/xlsx/pdf/md/txt；P1 支持 ppt/pptx；普通文件转换 ≤30s |
| G2 | 用户可一键启动售前专家 Agent | 上传客户资料 → 自动完成调研分析 → 根据plugins/skills产出相关文档 |
| G3 | 用户在MVP阶段，不能创建自定义 Agent 和 Agent Team（P1） | 只能从系统创建的Agents中选着。系统会在后续支持预设的Agent Team |
| G4 | 系统 Skill/Plugin 资产受保护 | 0 次非授权源码下载 |
| G5 | 多用户隔离 | 0 次跨用户数据泄露 |

### 3.2 Platform Metrics

| Metric | Target |
|---|---:|
| Run 完成率 | ≥90% |
| 用户文档转换成功率 | ≥95% |
| 安全越权事件 | 0 |
| Run 失败可定位率 | 100% |

---

## 4. Target Users & Roles

| 角色 | 权限范围 |
|---|---|
| 普通用户 | 使用 Expert Agent、上传文档、通过对话运行 Agent、查看自己的产物 |
| Presales Leader / Business Owner | 线下审批生成的文档 |
| Skill/Plugin Admin | 可以在后台（无界面），创建、扫描、审批、版本化、下架系统 Skill/Plugin |
| System Admin | 可以在后台管理（可以无界面）用户、角色、审计、运行配置、安全告警 |

---

## 5. Core Concept: Expert Agent

Expert Agent 是一个预配置的领域专家 Agent，能完成特定业务场景的完整工作流。

**用户视角：** 用户只需要上传资料，Expert Agent 自动完成工作，产出可审阅的成果。

**内部实现：** Expert Agent 是一个封装好的 Agent，包含：
- Main Agent（理解任务、规划执行、整合输出）
- Subagents（执行专业子任务，根据skills等动态创建）
- Quality Review Agent（独立审查产物质量）
- 绑定的 Skills/Plugins（领域方法和工具）
- 输入/产物规范（标准化产出格式）

---

## 6. User Stories & Requirements

### P0 — MVP Must Have

| # | User Story | Acceptance Criteria |
|---|---|---|
| P0-1 | 作为用户，我可以通过企微账号登录平台并拥有独立 workspace | 登录后仅能访问自己的文件、对话历史；跨用户访问被拒绝 |
| P0-2 | 作为用户，我可以查看和启动可用的 Expert Agent | 首页展示 Expert Agent 列表；售前专家 Agent 可一键启动 |
| P0-3 | 作为售前用户，我可以上传客户资料到workspace | 支持 doc/docx/xls/xlsx/pdf/md/txt；空文件、损坏文件有明确提示 |
| P0-4 | 作为用户，我可以上传文档添加到 Conversation | 平台自动转换为AI可处理文档；Agent 只能读取当前 Conversation 授权文档和用户的workspace中的文档 |
| P0-5 | 作为用户，我可以运行售前专家 Agent | 生成 market scan、interview guide、requirement analysis、AI solution outline、PPT outline 等多个产物 |
| P0-6 | 作为用户，我可以在chat框查看 Run 状态、事件流和错误原因 | Run 使用明确状态机；失败时展示 named error class |
| P0-7 | 作为用户，我可以查看和下载产物。生成的文档都放在workspace文件夹里面 | 产物在线展示、下载等 |
| P0-8 | 作为系统，我可以保护内置系统 Skill/Plugin | 普通用户 API 仅返回 id、name、description、version、status、checksum；源码只进入 worker-only runtime，不进入用户 workspace |
| P0-9 | 作为系统，我可以阻止 workspace 越权访问 | `..`、绝对路径、symlink、跨用户路径均被拒绝并记录 |
| P0-10 | 作为用户，我可以取消正在运行的 Run | 取消后状态进入 cancelling/cancelled；worker 停止写入 artifact |

### P1 — Should Have

| # | User Story | Acceptance Criteria |
|---|---|---|
| P1-1 | 用户可预览转换结果 | 转换完成后展示原始文件和 extracted text 对照 |
| P1-2 | Skill/Plugin Admin 可管理系统 Skill/Plugin 生命周期 | 支持上架、版本化、弃用；可以无界面管理 |
| P1-3 | 用户可上传 PPT/PPTX 作为辅助材料 | 支持 ppt/pptx 转换为 Agent 可用文本或结构化大纲 |
| P0-4 | 作为管理员，我可以查看审计日志 | 包含 Run、内置 Skill/Plugin 使用、文件访问、安全拒绝 |
| P0-5 | 作为平台，我可以限制资源消耗 | 单文件 50MB、Conversation 输入总量 200MB、Run timeout 60min、每 Run token 预算 200k、每用户 1 个 active Run、全局 5 个 active Run |
| P0-6 | 作为运维/管理员，我可以看到 day-1 metrics、alerts | 覆盖 Run、安全拦截；P0 不要求完整成本看板 |

---

## 7. 售前专家 Agent 详细说明

### 7.1 Plugins 和 Skills
根据售前方法论，准备相关plugins和skills
参考superpowers等plugins的方式，支持subagents等。

**约束：**
- Main Agent 可调用 Subagent
- Subagent 不能递归调用其他 Subagent
- Quality Review Agent 不改写产出物，只输出评审意见
