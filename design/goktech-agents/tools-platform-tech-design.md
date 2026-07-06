# goktech-agents 工具与技能管理平台 技术方案

> 版本：v1.0
> 日期：2026-05-31
> 定位：售前/方案级技术方案
> 关联文档：《goktech-agent 产品需求文档（PRD）》（同目录 `goktech-agents-prd.md`）、多智能体团队系统技术方案（同目录 `multi-agent-team-tech-design.md`）
> 覆盖需求：KR4（技能/插件/command 搜索）、KR13（外部连接器接入管理）、7.1.1「技能/插件中心」「工具接入管理」页面、7.2.4「工具、技能与插件」、7.3.1 工具能力要求

---

## 1. 概述

工具与技能管理平台是 goktech-agent 平台「工具与技能」主线的承载模块，职责是**统一注册、发现、授权和治理 Agent 可调用的全部能力来源**——包括内部技能（Skills）、插件（Plugins）、快捷命令（Commands）以及外部连接器（MCP Server / HTTP API / 内部系统连接器）。它处在 Agent 运行时的能力供给层：

```text
能力来源                工具与技能管理平台               Agent 运行时
───────────            ──────────────────              ──────────
内部 Skills(SKILL.md)   注册中心 ── 索引 ── 匹配 ──►   Agent 绑定工具
Plugins(installed.json) 连接器管理 ── 连通性测试 ──►    MCP Server 调用
MCP Server(外部)        授权网关 ── 团队/角色鉴权 ──►   按权限过滤可用工具
HTTP API(外部)          /command 搜索 ── 快捷匹配 ──►  FDE 对话中快速调用
内部系统连接器           参数配置 ── 模型/降级/稳定性 ──► 工具执行与容错
```

### 1.1 核心职责（对齐 PRD 7.2.4）

| 能力 | PRD 要求 | 首版范围 |
| --- | --- | --- |
| `/command` 快捷匹配 | 快捷匹配、模糊搜索、显示修复、跨技能包检索 | 必须支持 |
| 技能分类与发现 | 按能力和业务场景管理技能 | 必须支持 |
| 插件搜索 | 插件搜索和使用说明查看 | 必须支持 |
| 个人 skills 目录 | 个人技能沉淀和引用 | 必须支持 |
| 工具权限 | WebSearch/WebFetch/browse 等工具权限、降级路径和错误提示 | 必须支持 |
| 工具接入管理（连接器注册中心） | MCP Server/HTTP API（含鉴权）/内部系统连接器注册、连通性测试、按团队/角色授权 | 必须支持基础注册和连通性测试 |
| 模型与参数 | 模型选择、temperature、思考等级等参数 | 必须支持基础配置 |
| 稳定性治理 | JSON buffer、临时文件清理和大文件上传问题 | 必须支持 |

### 1.2 设计取舍（关键决策）

| 决策点 | 选择 | 理由 |
| --- | --- | --- |
| 工具协议统一 | **MCP（Model Context Protocol）为工具标准协议** | 所有能力来源（内部 skill、外部 API、连接器）统一编译为 MCP Server 暴露给 Agent；与 Claude Agent SDK 的 `mcp_servers` 原生对接，零适配成本 |
| 连接器注册 | **声明式注册 + 抽象 ConnectorProvider** | MCP Server / HTTP API / 内部系统三类来源用统一 `ConnectorSpec` 描述，按 Provider 实现差异化接入与鉴权；新增来源类型只需实现 Provider |
| 技能索引 | **向量语义匹配 + 标签过滤**（复用多智能体团队的 SkillRegistry） | 与 MATS 组队时的技能匹配共用索引，避免重复建设；`/command` 快捷匹配走精确前缀匹配，语义搜索走向量召回 |
| 授权模型 | **团队/角色/空间三维 ACL** | 对齐 PRD「按团队或角色的访问授权」与权限治理要求；工具授权挂在团队与角色上，Agent 运行时按身份过滤可用工具集 |
| 连通性测试 | **注册时强制 + 周期巡检 + 调用前快速探活** | 外部连接器不稳定是现场交付常见痛点；三级探活策略保证 Agent 不会因工具不可用而卡死 |
| 降级策略 | **工具级降级声明 + 平台级 fallback** | 每个工具声明降级路径（如 WebFetch 不可用时降级为缓存结果）；平台在工具调用失败时按声明自动切换，Agent 不感知底层故障 |
| 稳定性治理 | **平台层统一拦截** | JSON buffer 溢出、临时文件泄漏、大文件上传等问题在工具调用网关层统一治理，不依赖各工具自行处理 |

---

## 2. 总体架构

### 2.1 架构分层

```text
交互层    工具与技能管理 Web UI
          ├─ 技能/插件中心（消费端）   /command 搜索、技能分类浏览、插件搜索、使用说明
          ├─ 工具接入管理（管理端）    连接器注册、配置编辑、鉴权填写、连通性测试、授权管理
          ├─ 个人 skills 目录          个人技能上传/编辑/引用
          └─ 工具权限面板              工具级权限配置、降级路径声明、模型参数配置
              │  REST / WebSocket（连通性测试结果、工具调用日志流）

服务层    Tools Platform Service（FastAPI）
          ├─ RegistryService          连接器/技能/插件注册 CRUD、版本管理
          ├─ ConnectorManager         连接器生命周期：注册→测试→上线→巡检→下线
          ├─ DiscoveryService         /command 精确匹配 + 语义搜索 + 分类过滤
          ├─ AuthGateway              工具调用鉴权：团队/角色/空间 ACL 校验
          ├─ ToolExecutor             统一工具调用网关：协议适配、超时、重试、降级、稳定性拦截
          ├─ HealthChecker            连通性测试：注册时强制 + 周期巡检 + 调用前探活
          └─ MetricsCollector         工具调用统计：次数、成功率、延迟、token 消耗

运行层    MCP Server 进程池（内部技能/连接器代理）
          HealthCheck Worker（周期巡检）
          索引 Worker（技能/插件 embedding 构建与更新）

存储层    Postgres（注册元数据）    connectors / skills / plugins / tool_acl / health_logs / call_logs
          向量库（pgvector/Chroma） 技能/插件 embedding 索引
          对象存储（MinIO/S3）      个人 skills 包、工具配置模板
          Redis                     工具调用缓存、降级结果缓存、连通性状态缓存
```

### 2.2 组件职责

| 组件 | 职责 | 长任务 |
| --- | --- | --- |
| `RegistryService` | 连接器/技能/插件的注册 CRUD、配置版本管理、元数据维护 | 否 |
| `ConnectorManager` | 连接器生命周期管理：注册→连通性测试→上线→周期巡检→下线；维护 ConnectorProvider 实例池 | 是（测试/巡检异步） |
| `DiscoveryService` | `/command` 前缀精确匹配、技能/插件语义搜索（向量召回）、分类标签过滤 | 否 |
| `AuthGateway` | 工具调用前的 ACL 校验：当前用户/团队/角色是否有权调用目标工具 | 否 |
| `ToolExecutor` | 统一调用网关：MCP 协议适配、HTTP 超时/重试、降级 fallback、稳定性拦截器（JSON buffer/大文件/临时文件） | 否（同步调用，异步可选） |
| `HealthChecker` | 三级探活：注册时强制测试、周期巡检（可配置间隔）、调用前快速探活（缓存 TTL） | 是（巡检异步） |
| `MetricsCollector` | 采集工具调用次数、成功率、平均延迟、token 消耗，写入统计库供运营后台消费 | 否 |

### 2.3 数据流（端到端）

```text
── 注册流程（管理端） ──
1) 注册      管理员在工具接入管理页填写 ConnectorSpec（类型/地址/鉴权/参数）
2) 测试      HealthChecker 执行连通性测试（MCP handshake / HTTP ping / 自定义探针）
3) 上线      测试通过 → RegistryService 持久化 → AuthGateway 配置 ACL → 索引更新
4) 巡检      HealthChecker 周期巡检，异常时标记 degraded 并通知管理员

── 发现流程（消费端） ──
1) 搜索      FDE 在技能/插件中心输入 /command 或关键词
2) 匹配      DiscoveryService：精确前缀匹配 → 语义向量召回 → 分类标签过滤 → 排序返回
3) 详情      查看工具说明、参数、权限要求、降级路径

── 调用流程（Agent 运行时） ──
1) 绑定      Agent 创建时，按团队/角色 ACL 过滤出可用工具集，编译为 MCP Server 列表
2) 调用      Agent 发起工具调用 → AuthGateway 校验 → ToolExecutor 适配执行
3) 容错      调用失败 → 按降级声明 fallback → 记录 call_logs → MetricsCollector 统计
4) 治理      ToolExecutor 拦截器：JSON buffer 限流、临时文件清理、大文件分片
```

---

## 3. 连接器注册中心（对齐 KR13 + 7.1.1 工具接入管理）

### 3.1 统一连接器模型

所有外部能力来源用统一的 `ConnectorSpec` 描述，按 `kind` 区分三类 Provider：

```python
from dataclasses import dataclass, field
from enum import Enum

class ConnectorKind(str, Enum):
    MCP_SERVER = "mcp_server"
    HTTP_API = "http_api"
    INTERNAL = "internal"

class ConnectorStatus(str, Enum):
    REGISTERED = "registered"
    ACTIVE = "active"
    DEGRADED = "degraded"
    OFFLINE = "offline"

@dataclass
class AuthConfig:
    kind: str                     # none | api_key | bearer | oauth2 | basic
    credentials_ref: str = ""     # 凭证引用（加密存储，不存明文）
    headers: dict = field(default_factory=dict)
    oauth_config: dict | None = None

@dataclass
class ConnectorSpec:
    connector_id: str
    name: str
    kind: ConnectorKind
    description: str = ""
    endpoint: str = ""            # MCP: stdio command / SSE URL; HTTP: base URL; Internal: module path
    auth: AuthConfig = field(default_factory=lambda: AuthConfig(kind="none"))
    tools: list[str] = field(default_factory=list)  # 该连接器暴露的工具名列表
    health_check: dict = field(default_factory=dict) # 探活配置：method/path/expected_status/interval
    fallback: dict | None = None  # 降级声明：fallback_tool / cache_ttl / error_message
    tags: list[str] = field(default_factory=list)
    team_id: str = ""
    space_id: str = ""
    status: ConnectorStatus = ConnectorStatus.REGISTERED
    version: str = "1.0"
    created_at: str = ""
    updated_at: str = ""
```

### 3.2 ConnectorProvider 抽象

三类连接器用统一接口抽象，按 Provider 实现差异化接入：

```python
from abc import ABC, abstractmethod

class ConnectorProvider(ABC):
    @abstractmethod
    async def connect(self, spec: ConnectorSpec) -> bool:
        """建立连接，返回是否成功。"""
        ...

    @abstractmethod
    async def health_check(self, spec: ConnectorSpec) -> dict:
        """执行连通性测试，返回 {ok, latency_ms, detail}。"""
        ...

    @abstractmethod
    async def invoke(self, spec: ConnectorSpec, tool_name: str, args: dict) -> dict:
        """调用连接器上的指定工具。"""
        ...

    @abstractmethod
    async def list_tools(self, spec: ConnectorSpec) -> list[dict]:
        """列出连接器暴露的工具清单（名称/描述/参数 schema）。"""
        ...

class MCPServerProvider(ConnectorProvider):
    """MCP Server 接入：支持 stdio 和 Streamable HTTP 两种传输。"""
    async def connect(self, spec):
        # stdio: 启动子进程，发送 initialize 握手
        # HTTP: 建立 SSE 连接，完成 MCP handshake
        ...
    async def invoke(self, spec, tool_name, args):
        # 发送 tools/call 请求，解析 MCP 响应
        ...

class HTTPAPIProvider(ConnectorProvider):
    """HTTP API 接入：RESTful 调用，支持鉴权头注入。"""
    async def connect(self, spec):
        # 按 health_check 配置发送探测请求
        ...
    async def invoke(self, spec, tool_name, args):
        # 按工具映射配置发送 HTTP 请求，注入鉴权头
        ...

class InternalProvider(ConnectorProvider):
    """内部系统连接器：直接调用平台内部模块（如 Supabase 查询、MinerU 解析）。"""
    async def connect(self, spec):
        # 验证内部模块可用性
        ...
    async def invoke(self, spec, tool_name, args):
        # 直接调用内部服务方法
        ...
```

> Provider 由 `ConnectorManager` 按 `spec.kind` 自动选择，业务代码不感知具体接入方式。新增连接器类型只需实现 Provider。

### 3.3 MCP Server 注册详解

MCP Server 是平台工具能力的标准协议来源，支持两种传输模式：

| 传输模式 | 适用 | 配置 |
| --- | --- | --- |
| **stdio** | 本地进程型工具（如代码分析、文件处理） | `endpoint` = 启动命令 + 参数；平台管理子进程生命周期 |
| **Streamable HTTP** | 远程服务型工具（如外部 SaaS API 代理） | `endpoint` = HTTP URL；平台管理连接池与重连 |

注册时自动发现工具清单：

```python
async def register_mcp_server(spec: ConnectorSpec) -> list[dict]:
    provider = MCPServerProvider()
    ok = await provider.connect(spec)
    if not ok:
        raise ConnectorError("MCP handshake failed")
    tools = await provider.list_tools(spec)
    spec.tools = [t["name"] for t in tools]
    spec.status = ConnectorStatus.ACTIVE
    registry.save(spec)
    return tools
```

### 3.4 HTTP API 注册详解

HTTP API 接入需要将 REST 端点映射为工具声明：

```python
@dataclass
class HTTPToolMapping:
    tool_name: str
    method: str                  # GET | POST | PUT | DELETE
    path_template: str           # 如 "/api/v1/search?q={query}"
    param_mapping: dict          # 工具参数 → HTTP 参数映射
    response_transform: str | None = None  # 可选的响应转换（JSONPath / jq 表达式）
```

注册时管理员配置 endpoint + 鉴权 + 工具映射表，HealthChecker 按映射逐一测试可达性。

---

## 4. 技能与插件管理（对齐 KR4 + 7.2.4）

### 4.1 技能模型

```python
@dataclass
class Skill:
    skill_id: str
    name: str
    description: str
    category: str                # 能力分类：data / knowledge / analysis / generation / ...
    business_tags: list[str]     # 业务场景标签
    source: str                  # "builtin" | "personal" | "team" | "platform"
    owner_id: str                # 所属用户/团队
    entry_point: str             # SKILL.md 路径 或 MCP Server 工具名
    parameters: dict = field(default_factory=dict)  # 参数 schema
    permissions: dict = field(default_factory=dict)  # 权限声明
    fallback: dict | None = None
    version: str = "1.0"
```

### 4.2 技能来源与层级

技能按来源分四层，优先级从高到低：

| 层级 | 来源 | 说明 |
| --- | --- | --- |
| 个人 skills | 用户上传到个人 skills 目录 | 个人沉淀的自定义技能，仅个人可用（可共享） |
| 团队 skills | 团队空间内共享的技能 | 团队成员共同维护，团队内可用 |
| 平台 skills | 平台内置 + AI CoE 沉淀 | 全局可用，如 `presales-req-analysis`、`competitor-analysis` |
| 外部连接器 | MCP Server / HTTP API 注册的工具 | 按 ACL 授权给团队/角色使用 |

### 4.3 插件模型

```python
@dataclass
class Plugin:
    plugin_id: str
    name: str
    description: str
    category: str
    installed: bool = False
    config: dict = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)  # 插件提供的工具列表
    source: str = ""               # 安装来源
    version: str = "1.0"
```

插件通过 `installed_plugins.json` 登记，平台启动时扫描并构建索引。

### 4.4 技能/插件索引与发现（DiscoveryService）

索引构建与多智能体团队的 `SkillRegistry` 共用（复用 MATS §3.3 技能匹配引擎）：

```python
class DiscoveryService:
    def __init__(self, vector_index, registry):
        self.vector_index = vector_index
        self.registry = registry

    async def search_command(self, query: str) -> list[dict]:
        """/command 快捷匹配：精确前缀 → 模糊子串 → 返回候选列表。"""
        exact = self.registry.match_prefix(query)
        fuzzy = self.registry.match_fuzzy(query) if len(exact) < 5 else []
        return ranked_merge(exact, fuzzy)

    async def search_semantic(self, query: str, filters: dict = None,
                               top_k: int = 10) -> list[dict]:
        """语义搜索：向量召回 + 分类/标签过滤。"""
        hits = self.vector_index.search(embed(query), top_k=top_k, filters=filters)
        return [h.to_dict() for h in hits]

    async def browse_by_category(self, category: str,
                                  business_tags: list[str] = None) -> list[dict]:
        """分类浏览：按能力分类 + 业务场景标签过滤。"""
        return self.registry.filter(category=category, tags=business_tags)
```

**索引更新**：技能/插件注册或更新时，索引 Worker 异步重建该条目的 embedding；平台启动时全量扫描构建初始索引。

---

## 5. 工具调用网关（ToolExecutor）

### 5.1 统一调用流水线

Agent 运行时的所有工具调用经 `ToolExecutor` 统一网关，执行流水线如下：

```text
Agent 发起 tools/call
    │
    ▼ AuthGateway.check(user, team, role, tool_name)   ← ACL 校验
    │  拒绝 → 返回权限错误 + 可用工具提示
    ▼ ConnectorManager.resolve(tool_name)               ← 定位连接器
    │  未找到 → 返回工具不存在
    ▼ HealthChecker.quick_probe(connector)              ← 快速探活（缓存 TTL 内跳过）
    │  不可用 → 走降级路径
    ▼ ToolExecutor.execute(connector, tool, args)       ← 协议适配 + 调用
    │  ├─ MCPServerProvider.invoke()
    │  ├─ HTTPAPIProvider.invoke()
    │  └─ InternalProvider.invoke()
    │
    ▼ StabilityInterceptor.post_process(result)         ← 稳定性拦截
    │  ├─ JSON buffer 大小检查（超限截断 + 警告）
    │  ├─ 临时文件引用登记（后续自动清理）
    │  └─ 大文件响应转引用（返回 file_ref 而非内联内容）
    │
    ▼ MetricsCollector.record(tool, latency, success)   ← 统计埋点
    │
    ▼ 返回结果给 Agent
```

### 5.2 降级策略

每个工具可在注册时声明降级路径，调用失败时平台自动切换：

```python
@dataclass
class FallbackPolicy:
    strategy: str                # "cache" | "alternative_tool" | "error_message" | "retry"
    cache_ttl: int = 300         # cache 策略：缓存有效期(秒)
    alternative_tool: str = ""   # alternative_tool 策略：降级工具名
    error_message: str = ""      # error_message 策略：友好错误提示
    max_retries: int = 2         # retry 策略：最大重试次数
```

降级执行逻辑：

```python
async def execute_with_fallback(spec, tool_name, args):
    try:
        result = await provider.invoke(spec, tool_name, args)
        cache.set(f"fallback:{tool_name}:{hash(args)}", result, ttl=spec.fallback.cache_ttl)
        return result
    except ToolCallError as e:
        policy = spec.fallback
        if policy.strategy == "cache":
            cached = cache.get(f"fallback:{tool_name}:{hash(args)}")
            if cached: return {"_fallback": True, **cached}
        elif policy.strategy == "alternative_tool":
            return await execute_with_fallback(resolve(policy.alternative_tool), tool_name, args)
        elif policy.strategy == "retry":
            for i in range(policy.max_retries):
                try: return await provider.invoke(spec, tool_name, args)
                except: await asyncio.sleep(2 ** i)
        return {"error": policy.error_message or str(e), "_fallback": True}
```

### 5.3 稳定性拦截器（StabilityInterceptor）

对齐 PRD 7.2.4 稳定性治理要求，在工具调用网关层统一拦截：

| 治理项 | 拦截策略 |
| --- | --- |
| JSON buffer 溢出 | 响应体超 256KB 时截断 + 写入对象存储返回引用；Agent 收到 `{"_truncated": true, "ref": "..."}` |
| 临时文件清理 | 工具调用产生的临时文件注册到 `temp_files` 表，TTL 到期后清理 Worker 自动删除 |
| 大文件上传 | 上传类工具自动切换分片上传（>10MB），进度上报；下载类工具返回引用而非内联内容 |
| 超时控制 | 每个工具可配置超时（默认 30s），超时自动取消并返回降级结果 |
| 并发限流 | 单工具并发上限（默认 10），超限排队或拒绝，防止外部 API 被打挂 |

---

## 6. 授权与权限（AuthGateway）

### 6.1 三维 ACL 模型

工具授权基于团队、角色和空间三个维度，对齐 PRD「按团队或角色的访问授权」：

```python
@dataclass
class ToolACL:
    tool_name: str               # 或 connector_id:* 表示连接器下全部工具
    allowed_teams: list[str]     # 允许的团队 ID（空 = 不限）
    allowed_roles: list[str]     # 允许的角色名（空 = 不限）
    denied_teams: list[str]      # 显式拒绝的团队
    space_scope: str = "any"     # "any" | "own_space" | "specific"
    requires_approval: bool = False  # 是否需要管理员审批
```

### 6.2 鉴权流程

```text
Agent 调用工具
    │
    ▼ AuthGateway.check(user_id, team_id, role, tool_name)
    │
    ├─ 1) 查 tool_acl 表，匹配 tool_name 或 connector_id:*
    ├─ 2) 检查 denied_teams → 命中则拒绝
    ├─ 3) 检查 allowed_teams → 非空且不在列表中则拒绝
    ├─ 4) 检查 allowed_roles → 非空且不在列表中则拒绝
    ├─ 5) 检查 space_scope → own_space 时校验工具所属空间与用户空间一致
    ├─ 6) 检查 requires_approval → 需要审批则标记为 pending
    │
    ▼ 通过 → 放行到 ToolExecutor
    ▼ 拒绝 → 返回 {error: "permission_denied", available_tools: [...]}
```

### 6.3 工具权限分级

对齐 PRD「明确 WebSearch、WebFetch、browse 等工具权限、降级路径和错误提示」：

| 权限级别 | 工具示例 | 说明 |
| --- | --- | --- |
| **公开** | 内部查询、文件读取 | 所有用户可用 |
| **团队授权** | 外部 API、MCP Server | 按团队 ACL 授权 |
| **受限** | WebSearch、WebFetch、browse | 需管理员显式开启，有降级路径 |
| **审批** | 数据导出、外部写入 | 需管理员审批后使用 |

---

## 7. 连通性测试（HealthChecker）

### 7.1 三级探活策略

| 级别 | 触发时机 | 深度 | 超时 |
| --- | --- | --- | --- |
| **注册测试** | 连接器注册/更新时 | 完整握手（MCP initialize / HTTP 全端点测试） | 30s |
| **周期巡检** | 可配置间隔（默认 5min） | 轻量探针（MCP ping / HTTP HEAD） | 10s |
| **调用前探活** | Agent 调用工具前 | 快速探活（缓存 TTL 60s 内跳过） | 5s |

### 7.2 健康状态机

```text
registered ──(测试通过)──► active
    │                        │
    │                        ├──(巡检失败)──► degraded ──(连续3次失败)──► offline
    │                        │                    │
    │                        │                    └──(恢复)──► active
    │                        │
    └──(测试失败)──► registered（等待修复重测）
```

### 7.3 巡检 Worker

```python
async def health_check_loop():
    while True:
        connectors = registry.list_active()
        for spec in connectors:
            interval = spec.health_check.get("interval", 300)
            last_check = health_cache.get_last_check(spec.connector_id)
            if time.time() - last_check < interval:
                continue
            result = await provider.health_check(spec)
            health_cache.update(spec.connector_id, result)
            if not result["ok"]:
                spec.status = ConnectorStatus.DEGRADED
                consecutive_fails = health_cache.increment_fail(spec.connector_id)
                if consecutive_fails >= 3:
                    spec.status = ConnectorStatus.OFFLINE
                    await notify_admin(spec, result)
            else:
                spec.status = ConnectorStatus.ACTIVE
                health_cache.reset_fail(spec.connector_id)
            metrics.record_health(spec.connector_id, result)
        await asyncio.sleep(60)
```

---

## 8. 模型与参数配置

### 8.1 工具级参数配置

每个工具可配置与模型相关的运行参数：

```python
@dataclass
class ToolModelConfig:
    preferred_model: str = ""        # 推荐模型（如工具内含 LLM 调用）
    temperature: float = 0.7
    thinking_level: str = "medium"   # low | medium | high
    max_tokens: int = 4096
    timeout_seconds: int = 30
    concurrent_limit: int = 10
```

### 8.2 Agent 绑定时的参数合并

Agent 绑定工具时，参数按优先级合并：Agent 级配置 > 工具默认配置 > 平台默认值。

```python
def merge_tool_config(agent_config: dict, tool_default: ToolModelConfig) -> dict:
    return {
        "model": agent_config.get("model") or tool_default.preferred_model or platform_default.model,
        "temperature": agent_config.get("temperature", tool_default.temperature),
        "thinking_level": agent_config.get("thinking_level", tool_default.thinking_level),
        "max_tokens": agent_config.get("max_tokens", tool_default.max_tokens),
        "timeout": agent_config.get("timeout", tool_default.timeout_seconds),
    }
```

---

## 9. 与 Agent 运行时的集成

### 9.1 工具集编译

Agent 创建时，平台根据其所属团队/角色编译可用工具集：

```python
async def compile_tool_set(agent_context: dict) -> dict:
    """为 Agent 编译可用工具集，返回 MCP Server 配置字典。"""
    team_id = agent_context["team_id"]
    role = agent_context["role"]
    space_id = agent_context["space_id"]

    available = []
    all_tools = registry.list_all_tools()

    for tool in all_tools:
        if auth_gateway.check_access(team_id, role, space_id, tool):
            connector = registry.get_connector(tool.connector_id)
            if connector.status in (ConnectorStatus.ACTIVE, ConnectorStatus.DEGRADED):
                available.append(tool)

    mcp_servers = {}
    for connector in group_by_connector(available):
        provider = connector_manager.get_provider(connector)
        mcp_servers[connector.connector_id] = await provider.to_mcp_config(connector)

    return mcp_servers
```

### 9.2 与多智能体团队系统（MATS）的集成

MATS 的 `SkillRegistry`（§3.3 技能匹配引擎）与本模块的 `DiscoveryService` 共用索引：

- **组队阶段**：`TeamBuilder` 调用 `DiscoveryService.search_semantic()` 为蓝图中的技能项匹配已有 skill/plugin。
- **运行阶段**：`AgentPool` 调用 `compile_tool_set()` 为每个 Worker 编译可用工具集，注入 `ClaudeAgentOptions.mcp_servers`。
- **工具调用**：Worker 的工具调用经 SDK 的 MCP 通道到达 `ToolExecutor`，走统一鉴权与执行流水线。

### 9.3 与数据工作台/知识工作台的集成

| 模块 | 集成方式 |
| --- | --- |
| 数据工作台 | ETL/解析/查询能力注册为 Internal 类型连接器，Agent 通过工具调用访问 Supabase 表查询、MinerU 解析 |
| 知识工作台 | RAG 检索、图谱查询注册为 Internal 类型连接器，Agent 通过工具调用消费知识库 |
| 文件管理 | 文件读写注册为 Internal 类型连接器，Agent 通过工具调用操作个人/团队空间文件 |

---

## 10. 技术栈与持久化

| 层 | 选型 | 说明 |
| --- | --- | --- |
| 服务 | FastAPI + asyncio | 与数据工作台、知识工作台同栈 |
| 工具协议 | MCP（Model Context Protocol） | 统一工具协议，与 Claude Agent SDK `mcp_servers` 原生对接 |
| 注册元数据 | Postgres | connectors / skills / plugins / tool_acl / health_logs / call_logs |
| 技能索引 | pgvector / Chroma（复用 MATS 索引） | 技能/插件 embedding 语义搜索 |
| 缓存 | Redis | 工具调用缓存、降级结果缓存、连通性状态缓存、临时文件 TTL |
| 对象存储 | MinIO / S3 | 个人 skills 包、工具配置模板、大文件引用 |
| 实时通道 | WebSocket | 连通性测试结果推送、工具调用日志流 |
| Agent 集成 | Claude Agent SDK `mcp_servers` / `allowed_tools` | 工具集注入 Agent 运行时 |

**部署形态**：私有化场景全栈自托管（Postgres + Redis + MinIO），MCP Server 进程由平台管理生命周期；快速验证场景可用 Supabase 云 + 云 Redis。

---

## 11. 与相邻模块的边界

| 模块 | 边界 | 接口 |
| --- | --- | --- |
| 多智能体团队系统（MATS） | 工具平台**提供**技能索引与工具执行能力，MATS **消费**工具集 | `DiscoveryService.search()`、`compile_tool_set()`、`ToolExecutor.invoke()` |
| 数据工作台 | 数据能力（解析/ETL/查询）注册为 Internal 连接器，工具平台不负责数据逻辑 | Internal ConnectorProvider |
| 知识工作台 | 知识能力（RAG/图谱）注册为 Internal 连接器，工具平台不负责知识逻辑 | Internal ConnectorProvider |
| 文件管理（个人/团队空间） | 文件操作注册为 Internal 连接器，工具平台不负责文件 CRUD | Internal ConnectorProvider |
| 权限与成员管理 | 工具平台**复用**平台权限模型（用户/团队/空间），ACL 数据由权限服务同步 | `AuthGateway` 调权限服务校验 |
| 运营统计后台 | 工具平台上报调用次数、成功率、延迟、token 消耗等指标 | `MetricsCollector` 写统计事件 |
| 项目资产库 | 工具配置、连接器注册信息可作为项目资产快照的一部分发布复用 | 资产导出/导入 JSON |

---

## 12. MVP 范围与实施阶段

### 12.1 MVP 必含（对齐 KR4 + KR13 + V0.1/V0.2）

1. **连接器注册中心**：MCP Server（stdio/HTTP）和 HTTP API 注册、配置、鉴权存储。
2. **连通性测试**：注册时强制测试 + 周期巡检（5min）+ 调用前快速探活（60s 缓存）。
3. **技能/插件索引**：扫描 SKILL.md + installed_plugins.json，构建向量索引。
4. **`/command` 快捷匹配**：精确前缀匹配 + 模糊搜索 + 分类过滤。
5. **语义搜索**：技能/插件向量召回 + 标签过滤。
6. **个人 skills 目录**：上传/编辑/引用个人技能。
7. **工具调用网关**：统一 MCP 协议适配 + AuthGateway ACL 校验 + 超时/重试。
8. **降级策略**：cache / alternative_tool / error_message 三种降级路径。
9. **稳定性拦截**：JSON buffer 限流 + 临时文件 TTL + 大文件引用化。
10. **团队/角色 ACL**：按团队和角色控制工具访问范围。
11. **调用统计**：次数、成功率、延迟基础统计。

### 12.2 MVP 暂不含

- 动态业务工具开发（PRD「后续增强」）。
- 工具市场/跨平台工具共享。
- 复杂工具编排（DAG 工作流，保留 ToolExecutor 升级口）。
- 工具级细粒度沙箱/网络隔离（后续版本）。
- 完整的工具版本管理与回滚（首版仅记录版本号）。

### 12.3 并行实施 lanes

```text
Lane A: RegistryService + ConnectorSpec + Postgres 元数据（无依赖）
Lane B: MCPServerProvider + HTTPAPIProvider + InternalProvider（无依赖）
Lane C: DiscoveryService + 向量索引构建（无依赖）
After A+B: Lane D: ConnectorManager + HealthChecker 三级探活
After A:   Lane E: AuthGateway 三维 ACL
After D+E: Lane F: ToolExecutor 统一调用网关 + StabilityInterceptor + 降级
After C:   Lane G: /command 搜索 + 语义搜索 + 个人 skills 目录
最后:      Lane H: 工具接入管理 UI + 技能/插件中心 UI + WebSocket，E2E 串联
```

---

## 13. 风险与应对

| 风险 | 表现 | 应对 |
| --- | --- | --- |
| MCP Server 协议兼容性 | 不同 MCP 实现版本握手/工具发现行为不一致 | Provider 层做协议版本适配；注册时强制完整握手验证 |
| 外部连接器不稳定 | 客户现场网络限制、API 限流、服务宕机 | 三级探活 + 降级策略 + 友好错误提示；巡检异常自动标记 degraded |
| 技能匹配召回差 | 语义搜索命中不相关技能、/command 匹配遗漏 | 阈值 + 人工确认；持续补 skill 元数据；精确匹配与语义搜索互补 |
| 鉴权配置错误 | 工具越权访问或误拒 | ACL 变更需管理员确认；Agent 运行时拒绝时返回可用工具列表辅助排查 |
| JSON buffer / 大文件问题 | 工具返回超大响应导致内存溢出或传输超时 | StabilityInterceptor 统一拦截：截断 + 引用化 + 分片 |
| 临时文件泄漏 | 工具调用产生的临时文件未清理占满磁盘 | temp_files 表登记 + TTL 自动清理 Worker |
| 索引与注册不同步 | 技能注册后搜索不到 | 注册触发异步索引更新；索引 Worker 失败时重试 + 告警 |
| 工具数量膨胀 | 连接器注册过多导致 Agent 工具列表过长、选择困难 | 按团队/角色 ACL 过滤；分类浏览；语义搜索排序 |

---

## 14. 测试策略

| 模块 | 必测 |
| --- | --- |
| ConnectorProvider | MCP stdio/HTTP 握手、HTTP API 鉴权注入、Internal 模块调用、Provider 切换 |
| HealthChecker | 注册测试通过/失败、巡检状态流转、调用前探活缓存 TTL、连续失败→offline |
| DiscoveryService | /command 精确/模糊匹配、语义搜索召回质量、分类过滤、空结果处理 |
| AuthGateway | 团队/角色/空间 ACL 正确放行与拒绝、denied_teams 优先、requires_approval 流程 |
| ToolExecutor | MCP 调用成功/超时/失败、降级策略（cache/alternative/retry/error）、并发限流 |
| StabilityInterceptor | JSON buffer 截断、临时文件 TTL 清理、大文件引用化、超时取消 |
| RegistryService | CRUD、版本更新、元数据一致性、索引触发 |
| E2E | 注册 MCP Server → 连通性测试 → ACL 配置 → Agent 绑定 → 工具调用 → 降级 → 统计，含权限校验与稳定性拦截 |

---

## 15. 结论

工具与技能管理平台以「**统一注册（ConnectorSpec + Provider 抽象）→ 智能发现（/command + 语义搜索）→ 安全调用（AuthGateway + ToolExecutor）→ 稳定治理（降级 + 拦截 + 探活）**」为主干，落点在 FastAPI 服务 + MCP 标准协议 + 向量索引（复用 MATS）+ Redis 缓存。关键工程取舍：MCP 作为统一工具协议与 Claude Agent SDK 零适配、ConnectorProvider 抽象三类连接器保扩展性、三维 ACL 对齐权限治理要求、降级策略 + 稳定性拦截保 Agent 运行时不因工具故障卡死。它为 Agent 提供"可发现、可授权、可调用、可容错"的能力底座，直接支撑 KR4、KR13 与 V0.1/V0.2。建议按 §12 的 lanes 先跑通注册→测试→调用 MVP 闭环，再叠加降级策略与稳定性治理，最后接入动态业务工具开发。
