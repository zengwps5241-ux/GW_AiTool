# goktech-agent 工具管理平台（Tools Platform）产品需求文档（PRD）

> 模块版本：v2.0
> 日期：2026-06-09
> 定位：goktech-agent 平台"工具"主线的子 PRD
> 父文档：《goktech-agent 产品需求文档（PRD）》（同目录 `goktech-agents-prd.md`）
> 关联技术方案：《tools-platform-tech-design.md》（同目录）
> 关联模块：多智能体团队系统、数据工作台、知识工作台、技能插件中心、权限与成员管理

---

## 1. Executive Summary

工具管理平台是 goktech-agent 平台的"工具"主线模块，承载 Agent 可调用的**外部能力来源**（MCP Server、HTTP API、用户上传代码生成的托管工具）的统一注册、托管、授权、调用和治理。它不承载 Skills/Plugins/Commands 的注册与编排（由技能插件中心承载），也不承载数据/知识/文件等内部能力的业务实现（由对应工作台承载，以 `INTERNAL` 连接器方式接入本平台）。

v2.0 在 v1.0 的"统一注册→发现→授权→调用→治理"主干上完成三处关键升级：**收窄边界**（只管 MCP/API，避免与技能插件中心职责重叠）、**新增 Serverless 沙箱**（上传 Python/Java 代码包即生成可托管工具）、**用户身份贯通**（`user_id` 由平台注入并透传到后端，后端按 `user_id` 实施功能/数据权限）。

---

## 2. Background & Context

### 2.1 父 PRD 中的工具主线

父 PRD §7.2.4 明确要求平台承载"工具、技能与插件"，对应 6 个 Key Result 中与本模块相关的三条：

- **KR4** — 首版支持技能、插件和 command 搜索（**消费端**由技能插件中心承载，本模块提供工具清单作为数据源）
- **KR6** — 首版支持基础权限治理（**工具级**权限由本模块与权限与成员管理联合承载）
- **KR13** — 首版支持外部连接器接入管理（**注册端**由本模块承载）

父 PRD 7.1.1 中对应的页面是"**工具接入管理**"——管理员入口，负责 MCP Server / HTTP API / 内部 API 的注册、连通性测试和访问授权。父 PRD §7.3.1 工具能力要求：

> "工具能力：支持 command、skills、plugins、工具权限和动态业务工具。"

父 PRD §7.3.2 非功能要求中与本模块强相关：

- **稳定性** — 大文件上传、JSON buffer、临时文件清理等已知问题必须纳入治理
- **可运营性** — 平台应统计用户、Agent、skills、plugins、token 和任务成功率
- **可扩展性** — 预留企微协同、GraphRAG、多 Agent 编排和动态业务工具扩展空间

### 2.2 当前痛点（来自父 PRD §3.1 与 7.1.1）

- 工具/技能/插件分散在个人手中，团队查找、复用和授权缺少统一入口。
- FDE 在客户现场需要快速接入新工具/新 API，但缺乏标准化的注册、连通性测试和授权流程。
- 客户资料进入平台前需要严格的权限边界，工具调用必须可审计、可降级、可熔断。
- "动态业务工具"在父 PRD §7.2.4 中被列为后续增强项，FDE 现场需要"上传代码包即生成可托管工具"的能力。

### 2.3 v1.0 → v2.0 范围变化

| 维度 | v1.0 | v2.0（本 PRD） |
| ---- | ---- | -------------- |
| 范围 | 工具+技能+插件 混合 | **只含 MCP Server + HTTP API**（含 `INTERNAL` 内部能力注册） |
| 部署 | 仅外部托管 MCP/API | **三类来源**：①外部托管 MCP/API ②用户上传代码 → Serverless 沙箱 ③平台内置内部 API |
| 身份 | 工具级权限 | **三维 ACL + user_id 细粒度授权**（user_id 透传到后端） |
| 动态工具 | 后续增强 | **v2.0 必含**：Python/Java 代码包 → sandbox/Docker → 自动注册为 MCP/HTTP |

### 2.4 价值定位

| 角色 | 价值 |
| ---- | ---- |
| **FDE** | 复用既有 MCP/API 不再"装本地跑";上传一段代码即生成可托管工具;在客户现场不再被工具可用性卡住 |
| **AI CoE** | 把 MCP/API 接入沉淀为平台资产;统一治理 user_id 鉴权契约;工具调用画像反哺平台运营 |
| **BU 交付** | 接收标准工具配置与权限策略;复用 MVP 期间的 Serverless 工具;降低跨项目工具迁移成本 |
| **业务用户** | 不直接使用本平台,但通过 Agent 间接使用托管工具时获得"可预期、可降级、可审计"的体验 |

---

## 3. Objectives & Success Metrics

### 3.1 模块目标（Goal）

为 goktech-agent 平台提供**统一、可治理、可扩展的外部能力底座**——既支撑 FDE 在客户现场快速接入并托管工具,也支撑 AI CoE 通过统一鉴权契约和调用画像实现平台级治理。模块成功与否的判定标准是:Agent 调用任何外部能力时,都能在 ACL、user_id、降级、统计这四个维度被一致地约束。

### 3.2 与父 PRD KRs 的映射

| 父 PRD KR | 本模块对应能力 | 本模块责任 |
| --------- | -------------- | ---------- |
| **KR4** 技能/插件/command 搜索 | 暴露 `ToolCatalogAPI.list_tools_for_user()` 供技能插件中心消费 | **提供数据源**,不实现搜索 UI |
| **KR6** 基础权限治理 | 工具级 ACL（团队/角色/空间）+ user_id 显式授权 | **核心责任** |
| **KR13** 外部连接器接入管理 | ConnectorRegistry、连通性测试、按团队/角色授权 | **核心责任** |
| 父 PRD §7.3.2 稳定性 | JSON buffer、临时文件、大文件上传在网关层统一拦截 | **核心责任** |
| 父 PRD §7.3.2 可运营性 | 调用次数/成功率/延迟/token/用户级画像统计 | **核心责任** |
| 父 PRD §7.2.4 动态业务工具 | Serverless 代码沙箱运行时 | **v2.0 新增,核心责任** |

### 3.3 成功指标（Metrics）

> 父 PRD 中"试点期支撑至少 1 个 AI 实训营和 1-2 个 FDE MVP"是平台级 KR;本表为**本模块级**指标。

| 指标 | 当前基线 | 目标 | 测量方式 |
| ---- | -------- | ---- | -------- |
| 接入外部 MCP/API 数 | 0 | 试点期 ≥ 5 个 | `connectors` 表按 `kind` 统计 |
| Serverless 工具上线数 | 0 | 试点期 ≥ 3 个 | `connectors` 表按 `kind=user_code` 统计 |
| Agent 工具调用成功率 | N/A | ≥ 95%（含降级） | `call_logs.success / call_logs.total` |
| 工具调用平均延迟（P95） | N/A | MCP ≤ 5s、HTTP API ≤ 3s | `call_logs.latency` |
| ACL 误拒率 | N/A | ≤ 1%（含 user_id 授权） | `call_logs.status=permission_denied / total` |
| 连通性测试覆盖率 | 0 | 100%（注册/巡检/调用前三级） | `health_checks` 表 |
| 调用画像完整度 | 0 | 100% 调用带 user_id + team_id + space_id | `call_logs` 字段非空率 |
| Sandbox 实例自动恢复率 | N/A | ≥ 99%（主从切换 + 重启） | `sandbox_instances.restart_count` |
| 工具配置可复用率（首版） | 0 | 至少 1 次跨团队 Fork 包含工具配置 | 项目资产库关联统计 |

### 3.4 Non-Goals（明确不做）

| 不做 | 原因 |
| ---- | ---- |
| Skills/Plugins/Commands 的注册、发现、编排 | 父 PRD §7.2.4 明确由技能插件中心承载;v2.0 收窄范围 |
| 工具市场/跨平台工具共享 | 首版聚焦"接入 + 治理",后续版本评估 |
| GPU 沙箱、自定义网络、Sidecar 注入 | Serverless MVP 暂不含,列入 v1.0 后续 |
| 工具级细粒度网络隔离（先做平台级白名单） | 降低 MVP 复杂度 |
| 工具级版本管理与回滚（首版仅记录版本号） | 首版用 `version` 字段,版本管理功能推迟 |
| 工具级细粒度 UI（仅暴露管理员入口） | 工具调用 UI 由 Agent 业务视图承载,本模块只提供管理端 |

---

## 4. Target Users & Segments

### 4.1 用户角色矩阵

| 角色 | 主要任务 | 与本模块的接触面 |
| ---- | -------- | ---------------- |
| **平台管理员 / AI CoE** | 注册 MCP/API、配置 ACL、审批受限工具、监控调用画像 | 高频——使用"工具接入管理"和"调用监控" |
| **FDE Delta** | 上传代码包、调试工具调用、为客户配置工具白名单 | 中频——使用"Serverless 部署中心"和"工具权限面板" |
| **FDE Echo** | 在客户试用期间查看工具可用性和失败原因 | 低频——使用"调用监控"和降级提示 |
| **数据 / 知识角色** | 将工作台能力注册为 `INTERNAL` 连接器 | 中频——通过内部 API 注册 |
| **BU 交付** | Fork 团队快照时连带复用工具配置 | 低频——通过项目资产库消费 |
| **业务用户** | 不直接接触本平台 | 无——通过 Agent 业务视图间接使用 |

### 4.2 用户规模与频次假设

- **试点期**：1-2 个 AI 实训营 + 1-2 个 FDE MVP，预计 5-10 个管理员账号、20-30 个 FDE 账号。
- **运营期**：每个项目组 1 个管理员、N 个 FDE；Serverless 工具按项目组沉淀。
- **调用频次**：每个活跃 FDE 每天 50-200 次工具调用；Serverless 工具按 Agent 任务触发。

### 4.3 使用场景约束

- **客户现场交付**：必须重视 ACL、空间隔离、user_id 透传、审计日志。
- **快速验证**：首版不追求大而全，优先支持高频、刚需、可验收的能力。
- **可复用**：工具配置、ConnectorSpec 应能作为项目资产快照的一部分被 Fork。
- **非技术用户**：本模块管理端面向技术用户（管理员/FDE），业务用户只通过 Agent 间接受益。

---

## 5. User Stories & Requirements

### 5.1 P0 — Must Have（对齐父 PRD V0.1 + V0.2 MVP 必含）

| # | 用户故事 | 验收标准 |
| - | -------- | -------- |
| **P0-1** | 作为平台管理员,我希望在工具接入管理页注册一个外部 MCP Server（stdio 或 Streamable HTTP）,填写鉴权信息后立即完成连通性测试 | 注册时强制测试,失败可重试;测试通过后状态 `active`;连通性测试覆盖 MCP `initialize` 握手 |
| **P0-2** | 作为平台管理员,我希望注册一个外部 HTTP API,通过填写工具映射表(method/path/参数映射/响应转换)将其声明为 Agent 可调用的工具 | 映射表按 `HTTPToolMapping` 校验;HealthChecker 逐一测试可达性;失败时定位到具体端点 |
| **P0-3** | 作为平台管理员,我希望为每个工具配置三维 ACL(团队/角色/空间)和 user_id 显式授权(grant/deny),并能预览某 user_id 是否能调用某工具 | `deny` 优先于 `allow`;`space_scope=own_space` 时校验空间一致性;预览页返回 allow/deny 判定及原因 |
| **P0-4** | 作为 FDE Delta,我希望上传一个 Python(或 Java)zip 代码包,填写 manifest.yaml 后由平台自动构建并启动 sandbox/Docker 实例,把代码暴露为 MCP 或 HTTP 工具 | 上传限制 ≤200MB;构建超时 10min;启动超时 60s;启动后自动注册 `ConnectorSpec(kind=USER_CODE)`;1 主 N 从 + 心跳 |
| **P0-5** | 作为 Agent 运行时,我在调用任何工具前都经过 AuthGateway 鉴权,user_id 被注入到 ToolInvokeContext 并透传到后端 MCP/HTTP 请求(Header + metadata + payload 多通道) | 鉴权失败返回 `permission_denied`;后端按 user_id 实施数据隔离(通过 UserContext SDK) |
| **P0-6** | 作为平台管理员,我希望为每个工具配置降级策略(cache/alternative_tool/retry/error_message),调用失败时平台自动切换 | 降级策略在 `ConnectorSpec.fallback` 中声明;调用失败按策略顺序尝试 |
| **P0-7** | 作为平台管理员,我希望 ToolExecutor 在调用层统一拦截 JSON buffer 溢出(>256KB)、临时文件 TTL、大文件上传(>10MB),保障系统稳定 | 拦截器在 `StabilityInterceptor` 统一实现;超限返回 `file_ref` 而非内联 |
| **P0-8** | 作为平台管理员,我希望三级探活机制保证 Agent 不会因工具不可用而卡死:注册时强制测试 + 周期巡检(默认 5min) + 调用前快速探活(60s 缓存) | 健康状态机:registered → active → degraded → offline;连续 3 次失败降级为 offline |
| **P0-9** | 作为平台管理员,我希望调用监控页能查看每个工具的调用次数、成功率、延迟、用户级调用画像(token 消耗) | `MetricsCollector` 记录完整;支持按 tool/user/team/space 维度筛选 |
| **P0-10** | 作为技能插件中心(MATS 等消费端),我希望调用 `ToolCatalogAPI.list_tools_for_user(user_id, team_id, space_id)` 获取当前用户可调用的工具清单(含元数据、参数 schema、user_id 透传方式、降级路径) | 接口契约稳定;返回的 `ToolMeta` 含描述、参数、降级、权限元信息 |
| **P0-11** | 作为数据/知识/文件工作台,我希望将内部能力注册为 `INTERNAL` 连接器,Agent 通过统一工具调用访问 | InternalProvider 实现差异;鉴权遵循同一 AuthGateway |

### 5.2 P1 — Should Have（对齐父 PRD V0.2 增强项）

| # | 用户故事 | 验收标准 |
| - | -------- | -------- |
| **P1-1** | 作为平台管理员,我希望为工具配置超时(默认 30s)和单工具并发上限(默认 10),超限排队或拒绝 | 超时和并发在 `ToolModelConfig` 中可配 |
| **P1-2** | 作为 FDE Delta,我希望 HPA Controller 基于 CPU/QPS/并发自动扩缩容(冷却 60s,缩容延迟 5min,上限 `max_replicas`) | 扩容命中阈值持续 60s 触发;缩容持续 5min 触发;故障熔断:1h 重启超 `max_restarts_per_hour` 标 `offline` |
| **P1-3** | 作为后端开发者,我希望通过 `UserContext SDK`(Python/Java)获取 user_id 及关联属性(团队、角色、部门、空间),避免每个工具重复解析 | SDK 5 行代码即可获取 user_id;与平台 `user_id` 透传契约一致 |
| **P1-4** | 作为平台管理员,我希望工具配置可作为项目资产快照的一部分被 Fork,跨团队复用 | 快照导出/导入 JSON 包含 `ConnectorSpec`(脱敏凭证) |
| **P1-5** | 作为平台管理员,我希望 Serverless 工具支持 mTLS 出向调用(满足客户内网部署要求) | manifest 中显式声明;网络策略仅放行白名单下游 |

### 5.3 P2 — Nice to Have / 后续版本

| # | 用户故事 | 验收标准 |
| - | -------- | -------- |
| **P2-1** | 工具市场 / 跨平台工具共享 | 后续版本评估 |
| **P2-2** | 工具级版本管理与回滚 | 首版仅记录 `version` 字段,后续完善 |
| **P2-3** | 工具级细粒度网络隔离 | 先做平台级白名单,后续工具级 |
| **P2-4** | Serverless GPU 沙箱、自定义网络、Sidecar 注入 | 列入 v1.0 后续 |
| **P2-5** | 工具语义搜索 / 智能推荐 | Agent 工具列表过长时,语义搜索排序 |

### 5.4 跨模块契约（必须与其他模块对齐）

| 上游/下游 | 契约 |
| --------- | ---- |
| 技能插件中心(KR4) | 提供 `ToolCatalogAPI.list_tools_for_user()` + `get_tool_meta()`;技能描述中引用工具;`/command` 搜索时把工具作为候选项 |
| 多智能体团队(MATS) | 提供 `compile_tool_set()` 编译为 `ClaudeAgentOptions.mcp_servers` + `allowed_tools` |
| 权限与成员管理(KR6) | 复用平台 user/team/space 模型;`user_tool_grants` 由权限服务管理,AuthGateway 调用校验 |
| 运营统计后台 | 上报调用次数/成功率/延迟/用户级调用画像/扩容事件 |
| 项目资产库 | 工具配置/ConnectorSpec 可作为快照一部分;导出导入 JSON |
| 数据/知识/文件工作台 | 内部能力以 `INTERNAL` 连接器注册,Agent 通过统一工具调用访问 |

---

## 6. Solution Overview

### 6.1 高层方案（与 tech design §2 一致）

**范围**：本模块只承载 **MCP Server + HTTP API** 两类外部能力来源,以及 v2.0 新增的 **用户上传代码 → Serverless 沙箱** 托管。Skills/Plugins/Commands 由技能插件中心承载,数据/知识/文件能力以 `INTERNAL` 连接器方式接入本平台。

**三大设计决策**(摘自 tech design §1.2):

1. **MCP 为标准协议** — 与 Claude Agent SDK `mcp_servers` 原生对接,零适配成本。
2. **三类工具来源** — ①外部托管 MCP/API ②用户上传代码 → Serverless 沙箱 ③平台内置 `INTERNAL` API。
3. **user_id 贯通** — 平台调用网关层统一注入(Header + metadata + payload 多通道),后端按 user_id 实施功能/数据权限。

### 6.2 端到端流程（消费侧）

```
Agent 启动
  → 按 user_id 过滤 ACL
  → 编译工具集(ClaudeAgentOptions.mcp_servers + allowed_tools)
  → 详情查看(元数据/降级/权限)

Agent 调用工具(tools/call)
  → AuthGateway.check(user_id, team_id, role, space_id, tool_name)
     1) user_tool_grants.deny 命中? → 拒绝
     2) user_tool_grants.allow 命中? → 放行 + scope 限制
     3) tool_acl.denied_teams? → 拒绝
     4) tool_acl.allowed_teams? → 不匹配则拒绝
     5) tool_acl.allowed_roles? → 不匹配则拒绝
     6) space_scope=own_space? → 空间不一致则拒绝
     7) requires_approval? → 标记 pending
  → ConnectorManager.resolve(tool_name)
  → HealthChecker.quick_probe(缓存 60s 跳过)
  → ToolInvokeContext{user_id, team_id, role, space_id, request_id, trace_id}
  → ToolExecutor.execute(connector, tool, args, context)
     - MCPServerProvider → MCP metadata.user_id
     - HTTPAPIProvider  → Header/Query/Body
     - UserCodeProvider → sandbox/Docker
     - InternalProvider → 内部服务
  → StabilityInterceptor(JSON buffer / 临时文件 / 大文件 / 超时 / 并发)
  → MetricsCollector(tool, user_id, latency, success)
  → 返回结果给 Agent
```

### 6.3 管理端流程（注册 + 部署）

**外部连接器注册**:

```
填写 ConnectorSpec(name, kind, endpoint, auth, tools, ...)
  → HealthChecker 完整握手测试
  → 测试通过 → 持久化/ACL/索引 → ACTIVE
  → 周期巡检(5min) → 异常告警
```

**Serverless 工具部署**:

```
上传 zip + manifest.yaml
  → PackageReceiver 校验(≤200MB / 语言 / manifest)
  → ImageBuilder 选基础镜像 → 解压 → 装依赖 → 注入启动脚本 → 构建镜像
  → InstanceOrchestrator 拉起 base_replicas 实例
  → 实例上报 /__tools/list
  → 端点可达 + 握手校验
  → 写入 ConnectorSpec(kind=USER_CODE)
  → HPA Controller 监控 CPU/QPS/并发 → 扩缩容
  → MasterSlaveController 1 主 N 从 + 心跳 → 异常切换
```

### 6.4 关键能力清单(与验收对应)

| 能力 | 来源 | 对应 P0 |
| ---- | ---- | ------- |
| 外部 MCP Server 注册 | tech design §3 | P0-1 |
| 外部 HTTP API 注册 + 工具映射 | tech design §3.3 | P0-2 |
| 三维 ACL + user_id 授权 | tech design §6 | P0-3 |
| Serverless 工具部署 | tech design §4 | P0-4 |
| user_id 多通道透传 | tech design §5.2 | P0-5 |
| 降级策略 | tech design §5.3 | P0-6 |
| 稳定性拦截 | tech design §5.4 | P0-7 |
| 三级探活 | tech design §8 | P0-8 |
| 调用统计与画像 | tech design §10 / §11 | P0-9 |
| 工具清单 API | tech design §7.1 | P0-10 |
| INTERNAL 连接器 | tech design §3.2 / §7.3 | P0-11 |

### 6.5 与相邻模块的边界(摘自 tech design §11,作为产品边界)

| 模块 | 边界 |
| ---- | ---- |
| 技能插件中心 | 工具平台**提供**工具清单与元数据(消费用),技能插件**不**通过本平台注册 |
| 多智能体团队(MATS) | 工具平台**提供** `compile_tool_set()` 与 `ToolExecutor.invoke()`,MATS **消费** |
| 数据/知识/文件工作台 | 内部能力注册为 `INTERNAL` 连接器 |
| 权限与成员管理 | 工具平台**复用**平台用户/团队/空间模型;`user_tool_grants` 由权限服务管理 |
| 运营统计后台 | 工具平台上报调用画像 |
| 项目资产库 | 工具配置可作为快照一部分 |
| Serverless 部署中心 | 属于本平台的子模块 |

---

## 7. Open Questions

| # | 问题 | 负责人 | 截止时间 | 备注 |
| - | ---- | ------ | -------- | ---- |
| 1 | Serverless 沙箱默认上限:单实例 CPU/内存配额?最大 zip 大小 200MB 是否调整? | 平台架构师 | MVP 设计冻结前 | 影响成本与稳定性 |
| 2 | 工具配置 Fork 时凭证如何处理(明文/加密/重注入)? | 平台架构师 + 安全 | MVP 设计冻结前 | 跨团队复用安全边界 |
| 3 | `user_id` 透传到第三方 MCP/API 时,如何应对"被代理剥离"场景? | 平台架构师 | V0.2 上线前 | tech design §13 已列风险 |
| 4 | 调用前快速探活缓存 60s 是否需要按工具可配? | FDE 负责人 | V0.2 设计评审 | 影响可用性 vs 调用延迟 |
| 5 | Serverless 工具的 egress 网络白名单默认值? | 平台架构师 | V0.2 设计评审 | 客户现场网络限制差异大 |
| 6 | 内部 API(`INTERNAL` 连接器)是否需要单独的"内部注册"管理端 UI,还是复用同一表单? | 产品负责人 | V0.2 设计冻结前 | 内部能力的可见性边界 |
| 7 | 调用监控页是否需要"实时"通道(WebSocket)还是仅 T+1 统计? | FDE 负责人 | V0.2 设计评审 | tech design §10 选了 WebSocket |
| 8 | 工具配置接入项目资产快照后,Fork 时是否需要"工具可用性预检"? | 产品负责人 | V1.0 设计冻结前 | 影响复用体验 |

---

## 8. Timeline & Phasing

### 8.1 版本策略(与父 PRD 8.x 对齐)

本模块沿用父 PRD 三阶段策略,本表为**本模块**在每个阶段的具体范围。

### 8.2 V0.1 阶段(本模块范围)

- 范围:**连接器注册中心**(MCP Server + HTTP API + 内部 API)的元数据 CRUD、鉴权存储、连通性测试。
- 不包含:Serverless 沙箱、user_id 工具级显式授权(只保留三维 ACL)、HPA 高级特性。
- 验收对齐父 PRD 9 节相关项:工具接入(管理员能注册 MCP/API 并完成连通性测试)。

### 8.3 V0.2 阶段(本模块范围,MVP 主战场)

> 对应父 PRD §12.3 实施 lanes 中 A / B / C / D / E / F / G / H / I。

| 实施 Lane | 内容 | 对应 P0 |
| --------- | ---- | ------- |
| **Lane A** | ConnectorRegistry + ConnectorSpec(USER_CODE、user_permission 字段) + Postgres 表 | P0-1 / P0-2 / P0-11 |
| **Lane B** | MCPServerProvider / HTTPAPIProvider / InternalProvider 扩展(含 user_id 透传) | P0-5 / P0-11 |
| **Lane C** | CodeSandbox Runtime(PackageReceiver + ImageBuilder + SandboxPool) + 镜像仓库 | P0-4 |
| **Lane D** | UserCodeProvider + ToolAutoRegistrar + 启动清单上报 | P0-4 |
| **Lane E** | AuthGateway 扩展(user_tool_grants + user_id 注入) | P0-3 / P0-5 |
| **Lane F** | ToolExecutor + StabilityInterceptor + 降级策略 | P0-6 / P0-7 |
| **Lane G** | HPA Controller + MasterSlaveController + 重启熔断 + 三级探活 | P0-4 / P0-8 |
| **Lane H** | 工具接入管理 UI + Serverless 部署中心 UI + 调用监控 UI(E2E 串联) | P0-1~P0-4 全部 |
| **Lane I** | UserContext SDK(Python/Java) + 后端接入指引 | P1-3 |

**V0.2 验收对齐**:
- 管理员能注册 MCP/API 并完成连通性测试(父 PRD 9.工具接入)
- 工具级权限 + user_id 显式授权(父 PRD 9.权限管理)
- Serverless 工具能上传→构建→启动→扩缩容→重启(本 P0-4)
- 调用统计 + 用户级画像(本 P0-9)

### 8.4 V1.0 阶段(本模块范围)

- Serverless 多语言高级特性(GPU 沙箱、自定义网络、Sidecar 注入)。
- 工具配置作为项目资产快照的一部分(Fork 复用,本 P1-4)。
- mTLS 出向调用(本 P1-5)。
- 工具语义搜索 / 智能推荐(本 P2-5)。

### 8.5 后续版本方向

- 工具市场 / 跨平台工具共享(本 P2-1)。
- 工具级版本管理与回滚(本 P2-2)。
- 工具级细粒度网络隔离(本 P2-3)。
- 更完善的工具级运营分析与成本分析。

---

## 附录 A:术语表

| 术语 | 含义 |
| ---- | ---- |
| **Tools** | 本模块范围,特指 MCP Server + HTTP API + Serverless 沙箱托管工具 + INTERNAL 内部能力 |
| **MCP** | Model Context Protocol,与 Claude Agent SDK 原生对接的工具协议 |
| **Skills / Plugins / Commands** | 不在本模块范围,由技能插件中心承载 |
| **ConnectorSpec** | 工具的统一元数据描述(name/kind/endpoint/auth/tools/fallback/user_permission 等) |
| **ConnectorKind** | mcp_server / http_api / user_code / internal |
| **user_id 贯通** | 平台调用网关层统一注入 user_id 并多通道透传到 MCP/HTTP 后端,后端按 user_id 实施功能/数据权限 |
| **三维 ACL** | 团队(allowed_teams / denied_teams) / 角色(allowed_roles) / 空间(space_scope) |
| **user_tool_grants** | user_id 维度的工具级显式授权,叠加在三维 ACL 之上(deny 优先于 allow) |
| **FallbackPolicy** | 工具降级策略:cache / alternative_tool / retry / error_message |
| **HPA** | Horizontal Pod Autoscaler,基于 CPU/QPS/并发的横向扩缩容 |
| **MasterSlave** | 1 主 N 从沙箱架构,主异常时从切主 |
| **StabilityInterceptor** | ToolExecutor 网关层的稳定性治理(JSON buffer / 临时文件 / 大文件 / 超时 / 并发) |
| **UserContext SDK** | 供后端开发者获取 user_id 及关联属性的 SDK(Python/Java) |

## 附录 B:与父 PRD 的关系

- **本 PRD 不重复父 PRD §1-§7.3.2 的内容**,仅在 §2 中引用必要上下文。
- **本 PRD 的 KR / 指标 / 验收均对齐父 PRD**,并细化到本模块级。
- **本 PRD 的 Non-Goals 必须与父 PRD Non-Goals 一致**(技能插件、数据/知识业务实现等不在本模块)。
- **本 PRD 的版本阶段(V0.1 / V0.2 / V1.0)与父 PRD §8 版本阶段一一对应**。
