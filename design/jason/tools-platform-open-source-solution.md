# goktech-agents 工具管理平台 — 开源选型与集成方案

> 版本：v1.0
> 日期：2026-06-04
> 定位：售前/方案级技术方案（配套 `tools-platform-tech-design.md` v2.0）
> 关联文档：
> - `tools-platform-tech-design.md`（v2.0 主方案）
> - `goktech-agents-prd.md`、`multi-agent-team-tech-design.md`
> 输入：基于 2026-06-04 exa-win-search deep research 抓取的 8 个权威源（详见 §11 引用清单）
> 目标：把 v2.0 主方案中的关键能力点落到**具体的开源项目选型、协议级集成示例、可私有化部署清单**，让售前可直接拿出去和客户/研发对方案。

---

## 目录

1. 选型方法论与评估维度
2. 能力方向一：MCP Server 协议实现与工具网关
3. 能力方向二：Serverless 代码沙箱与多语言运行时
4. 能力方向三：用户身份贯通与细粒度权限
5. 能力方向四：Agent 工具集动态编译与 mcp_servers 注入
6. v2.0 主方案与开源能力映射表
7. 集成参考实现：Python 端到端示例
8. 集成参考实现：Java 端到端示例
9. 私有化部署清单
10. 风险与对账
11. 引用清单（deep research 来源）
12. 结论与下一步

---

## 1. 选型方法论与评估维度

为保证选型可追溯、可评审，本文按以下 6 维度对比每个候选开源项目：

| 维度 | 含义 | 在售前方案中的权重 |
| --- | --- | --- |
| **成熟度** | GitHub star、release 节奏、conformance 通过率、issue 关闭率 | 高 |
| **协议兼容** | 对 MCP 2025-11-25 / OAuth 2.1 / Streamable HTTP / SSE 等的支持 | 高 |
| **可私有化** | 能否完全离线/内网部署，是否依赖云服务 | **极高**（客户内网交付） |
| **多语言** | Python/Java 之外的覆盖范围，影响 FDE 工具生态 | 中 |
| **性能** | 冷启动延迟、吞吐、内存占用 | 中（结合 HPA 可补） |
| **治理** | 鉴权、审计、限流、ACL 等企业级能力 | 高 |

每个能力方向末尾给出"**主选 + 备选 + 不选**"的明确建议，避免售前交付时反复推敲。

---

## 2. 能力方向一：MCP Server 协议实现与工具网关

### 2.1 2026 年 MCP SDK 现状（MCP 项目官方分级）

MCP 项目 2026-02 引入 tier 分级 + conformance 测试，明确每种 SDK 的成熟度（来源 [1]）：

| Tier | SDK | Star | 维护方 | conformance | 备注 |
| --- | --- | --- | --- | --- | --- |
| **Tier 1** | **Python SDK** | ~22,400 | Anthropic | 100% Server / 100% Client | 默认选项，生态最成熟 |
| **Tier 1** | TypeScript SDK | ~12,000 | Anthropic | 100% | Node/前端 MCP 工具 |
| **Tier 1** | C# SDK | ~4,100 | Microsoft | 100% | .NET 生态 |
| **Tier 1** | Go SDK | ~4,200 | Google | 100% | 高性能网关 |
| **Tier 2** | **Java SDK** | ~3,300 | Spring AI 团队 | Server 100% / Auth 98.9% | Java 企业栈首选 |
| **Tier 2** | Rust SDK | ~3,200 | Community | 80%+ | 高性能场景 |
| **Tier 3** | PHP / Swift / Kotlin / Ruby | < 2,000 | 各方 | 无承诺 | 暂不进入主方案 |

> **售前口径**：本平台 Tools 范围对应 MCP，因此 **Python + Java 双 SDK 必须 Tier 1/2 全支持**。其余语言按客户需求增量补。

### 2.2 高阶框架对比

在官方 SDK 之上的高阶框架，决定 FDE 写一个 MCP 工具的开发体验：

| 框架 | 语言 | star | 关键特性 | 适用场景 |
| --- | --- | --- | --- | --- |
| **FastMCP 3.0** | Python | ~24,100 | 函数即工具、热重载、OpenTelemetry 内置、`FastMCP.from_fastapi()`、Provider 系统 | **Python MCP 工具开发的事实标准**（约占 70% MCP server） |
| **FastMCP** | TypeScript | ~3,000 | OAuth discovery、Cloudflare Workers edge 支持 | TS 生态 |
| **Spring AI MCP** | Java | — | Boot Starter 注解 `@Tool`、Streamable HTTP、`mcp-security` 模块 | **Java MCP 工具开发事实标准** |
| **Quarkus MCP Server** | Java | ~190 | GraalVM native image，**平均延迟 4.04ms / P95 8.13ms** | 极致性能场景 |

### 2.3 工具网关候选

外部 MCP Server 数量增长后，需要一个统一网关聚合 + 鉴权：

| 网关 | 协议支持 | 鉴权深度 | 部署形态 | 适用 |
| --- | --- | --- | --- | --- |
| **Envoy AI Gateway / MCP Gateway** | MCP + OpenAI + Anthropic | **强**（Kuadrant AuthPolicy + OPA + Wristband） | Envoy + K8s | **主选**，聚合多 MCP Server + 细粒度 ACL |
| **MCP Auth（mcp-auth.dev）** | MCP | 中（OAuth 2.1 包装） | 库/服务 | 备选，鉴权实现可移植 |
| **Spring AI MCP Security** | MCP | 中（OAuth 2.0 + API Key） | Spring Boot | 备选，仅 Java 生态 |
| 自研 FastAPI 网关 | 自定义 | 高 | Python | 仅在客户拒绝引入 Envoy 时考虑 |

### 2.4 选型结论

| 主选 | 备选 | 不选 |
| --- | --- | --- |
| Python 工具开发用 **FastMCP 3.0**；Java 工具开发用 **Spring AI MCP**；外部多 MCP 聚合用 **Envoy AI Gateway / MCP Gateway** | C# / Go SDK（按客户语言生态补）；Quarkus MCP（极致性能场景） | Tier 3 的 PHP/Swift/Kotlin/Ruby（首版不进主方案） |

---

## 3. 能力方向二：Serverless 代码沙箱与多语言运行时

### 3.1 公有云 Sandbox 厂商对比（来源 [2]）

7 个主流厂商在 2026 年 1 月的最新横向对比：

| 厂商 | SDK 语言 | 最大运行时 | 冷启动 | GPU | 私有化 | 起价 | 适合场景 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Modal** | Python (主) / TS / Go (beta) | 24h | < 1s | **强** | ❌ | $0.000014/core/sec | ML 推理 + 沙箱 |
| **E2B** | Python / TS | 24h (Pro) | ~150ms | ❌ | ✅ **开源** | $100 免费额度 | **AI Agent 快速集成** |
| **Daytona** | Python / TS | 不限 | ~90ms | ✅ | ✅ Enterprise | $200 免费额度 | **完整开发环境** + 自定义 Docker 镜像 |
| Cloudflare Sandbox | TS | 可配 | 2-3s | ❌ | ❌ | $5/月 | 边缘部署 |
| Vercel Sandbox | TS | 5h (Pro) | 快 | ❌ | ❌ | $0.128/CPU·h | Next.js 生态 |
| Beam | Python (主) / TS (beta) | 不限 | 2-3s | **强** | ✅ **开源** | 15h 免费 | ML/GPU + 自托管 |
| Blaxel | Python / TS | 不限 | **~25ms** | ❌ | ❌ | $200 免费额度 | **有状态 agent 快速 resume** |

### 3.2 自托管 Serverless 平台对比（来源 [3]）

FDE 客户多有内网部署要求，必须有**完全私有化**的方案：

| 平台 | 复杂度 | 隔离机制 | 适合 |
| --- | --- | --- | --- |
| **OpenFaaS / faasd** | 低 | Docker + **可选 gVisor runsc** | **主选**：faasd 单机 + gVisor 满足"轻量 + 安全"，OpenFaaS Pro K8s 满足企业级 |
| **Knative** | 高 | Docker / gVisor | 备选：已有 K8s 平台、事件驱动 |
| **Nuclio** | 中 | Docker / gVisor | 备选：AI/ML 高性能 |
| 裸 K8s + 自研调度 | 极高 | 自选 | 不选（运维成本不划算） |

> **OpenFaaS gVisor 关键事实**（来源 [5]）：faasd `install --gvisor` 即可启用，**专为 LLM 生成代码 / 用户上传代码 / 第三方不可信代码**设计 —— 与本平台 v2.0 §4 Serverless 沙箱目标完全匹配。

### 3.3 MicroVM 隔离对比（来源 [6]）

| 方案 | 启动 | 性能 | 隔离强度 | 适合 |
| --- | --- | --- | --- | --- |
| **Firecracker** | ~125ms | 接近裸机（≥95% 性能） | VM 级 | **主选**：短任务 < 60s |
| **gVisor** | ~200-500ms | 50-70% 裸机 | Syscall 拦截 | **主选**：长驻 + 不可信代码 |
| Docker（普通） | < 100ms | 接近裸机 | 内核共享（弱） | 仅用于内部系统连接器（INTERNAL 类型） |

### 3.4 选型结论

| 主选 | 备选 | 不选 |
| --- | --- | --- |
| **轻量短任务**：firecracker（自管 microVM）<br>**长驻 + 用户上传代码**：OpenFaaS faasd + gVisor（私有化）<br>**快速验证/公有云试点**：Daytona 或 E2B | Knative（已有 K8s 客户）；Modal/Beam（GPU 场景） | Cloudflare/Vercel Sandbox（不可私有化） |

> v2.0 §4 中"sandbox + Docker 双形态"的**具体落地**：sandbox → firecracker + faasd gVisor；Docker → 标准 K8s Pod + faasd。

---

## 4. 能力方向三：用户身份贯通与细粒度权限

### 4.1 协议层规范（MCP 2026 Auth 规范）

来源 [7]：MCP 2026 授权规范基于 **OAuth 2.1 + PKCE**，核心四件套：

| RFC | 作用 |
| --- | --- |
| **RFC 8707** Resource Indicators | 客户端必须声明要调用的 MCP server 名称，避免 token 被重放到其他 server |
| **RFC 7591** Dynamic Client Registration | 客户端（Claude Desktop / Cursor）首次接入即注册，无需人工配置 |
| **RFC 9728** Protected Resource Metadata | MCP server 暴露元数据，客户端可发现授权服务器 |
| **PKCE（强制）** | 防授权码截持 |

> **v2.0 §6.4 后端契约的对齐**：本平台 AuthGateway 透传 user_id 时，必须使用 `aud` 声明避免 token 重放；同时后端按 user_id 实施功能/数据权限。

### 4.2 三种常见反模式（来源 [7]）

| 反模式 | 后果 |
| --- | --- |
| 共享服务账号 token | 审计追溯不到具体人；MCP01 token 滥用 |
| 长期 per-user token 存 DB | 等于自建"无轮换/无撤销/无 scope 收紧"的破 vault |
| 透传 session cookie | 跨域/不同 OIDC 即失效；违反 MCP 规范的 token passthrough 禁令 |

### 4.3 落地模式：OAuth 2.1 Token Exchange + Wristband（来源 [4][7]）

Red Hat / Kuadrant 在 Envoy MCP Gateway 上实现的**生产级模式**（v2.0 §6 的具体实现）：

```text
Agent (持有 broad-scope OAuth2 token)
   │
   ▼ tools/call with X-User-Id = alice
Envoy MCP Gateway (AuthPolicy)
   │
   ├─ 1) 校验 agent 的 token（keycloak JWT 校验）
   ├─ 2) Authorino 从 IdP 拉取 alice 的角色与权限
   ├─ 3) 生成 signed "wristband" JWT，含 alice 可调用的工具清单
   │      写入 x-authorized-tools header
   ├─ 4) MCP Broker 用 wristband 过滤 tools/list 响应
   ├─ 5) 调用下游 MCP server 时，**RFC 8693 Token Exchange**
   │      把 broad-scope token 换成 narrow-scope token（aud = 目标 server）
   │      PAT/API Key 从 HashiCorp Vault 取
   ▼
下游 MCP server 收到 narrow-scope token + X-User-Id，按 user_id 鉴权
```

### 4.4 平台级实现建议

| 阶段 | 实现 |
| --- | --- |
| **MVP** | 平台 AuthGateway 注入 `X-User-Id` header 到 MCP metadata + HTTP Header + JSON payload（**多通道冗余**），后端按需读取。Token 由平台用户中心（已对接 keycloak / 内部 IdP）签发。 |
| **增强** | 引入 Envoy AI Gateway / MCP Gateway + Kuadrant，承担 token 收窄、工具过滤、vault 集成 |
| **成熟** | Wristband + Token Exchange + 平台定期对账（抽样审计后端是否忽略 user_id） |

### 4.5 选型结论

| 主选 | 备选 | 不选 |
| --- | --- | --- |
| **MVP**：平台 AuthGateway 直接注入 `X-User-Id` 多通道（Header/metadata/payload）<br>**企业增强**：Envoy MCP Gateway + Kuadrant（AuthPolicy + Wristband + RFC 8693 Token Exchange） | mcp-auth.dev（库级别 OAuth 包装）；Spring AI MCP Security（仅 Java 工具） | 透传 session cookie；共享 service token；长期 per-user token 存 DB |

---

## 5. 能力方向四：Agent 工具集动态编译与 mcp_servers 注入

### 5.1 Claude Agent SDK 用法（来源 [8]）

```python
from claude_agent_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(
    mcp_servers={
        "claude-code-docs": {"type": "http", "url": "https://..."},
        "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]},
    },
    allowed_tools=[
        "mcp__github__*",        # 整个 server 全部工具
        "mcp__db__query",        # 某个 server 的某个工具
    ],
)

async for message in query(prompt="...", options=options):
    ...
```

**关键事实**：
- MCP 工具命名规范：`mcp__<server_name>__<tool_name>`
- `allowed_tools` 支持通配符 `mcp__<server>__*`
- `mcp_servers` 可在 code 或 `.mcp.json` 配置；推荐运行时编译（按 user_id 过滤）

### 5.2 大规模工具集的性能优化：Tool Search（来源 [9]）

当工具数量大（> 100）时，Agent 模型选择工具会变慢。**Tool Search** 模式：

```python
# 方式 A：嵌入式（全部工具放入 prompt） — 工具 < 50 时
options = ClaudeAgentOptions(tools=["tool1", "tool2", ...])

# 方式 B：Tool Search（按需检索，仅暴露相关子集） — 工具 ≥ 50
options = ClaudeAgentOptions(
    tool_search=True,
    tool_catalog=catalog,  # 平台预编译的 user_id 过滤后工具目录
)
```

**本平台的实施**：默认按 user_id + 三维 ACL 编译工具子集 → 工具 < 50 走嵌入式；≥ 50 自动启用 Tool Search。

### 5.3 平台编译流水

```python
async def compile_tool_set(user_id: str, team_id: str, role: str, space_id: str) -> dict:
    """把 user_id 编译为 ClaudeAgentOptions.mcp_servers + allowed_tools。"""
    catalog = await tool_catalog.list_for_user(user_id, team_id, space_id)

    mcp_servers, allowed = {}, []
    for conn in catalog:
        if conn.kind == "mcp_server":
            mcp_servers[conn.name] = {
                "type": "http", "url": conn.endpoint,
                "headers": {"X-User-Id": user_id},       # 透传
            }
            allowed.append(f"mcp__{conn.name}__*")
        elif conn.kind == "http_api":
            mcp_servers[conn.name] = {"type": "http", "url": conn.endpoint}
            allowed.append(f"mcp__{conn.name}__*")
        elif conn.kind == "user_code":
            mcp_servers[conn.name] = {"type": "http", "url": f"internal://usercode/{conn.connector_id}"}
            allowed.append(f"mcp__{conn.name}__*")

    use_tool_search = len(allowed) > 50
    return ClaudeAgentOptions(
        mcp_servers=mcp_servers,
        allowed_tools=allowed,
        tool_search=use_tool_search,
    )
```

### 5.4 选型结论

| 主选 | 备选 | 不选 |
| --- | --- | --- |
| **Claude Agent SDK 原生** + 平台预编译工具集（按 user_id 过滤）+ 工具数 ≥ 50 时启用 Tool Search | LangChain/LlamaIndex MCP Adapter（仅在客户已用 LangChain 时） | 自研协议适配（与 Claude SDK 零适配的优势不可替代） |

---

## 6. v2.0 主方案与开源能力映射表

把 v2.0 文档 12.1 的 MVP 必含项落到具体开源项目：

| v2.0 MVP 项 | 选型（开源项目） | 落地方式 |
| --- | --- | --- |
| 连接器注册中心 MCP/HTTP/INTERNAL/USER_CODE | **FastAPI** + **MCP Python SDK** | 自研服务，FastAPI + Postgres |
| Python 工具快速开发 | **FastMCP 3.0** | FDE 写 MCP server 直接用 FastMCP |
| Java 工具快速开发 | **Spring AI MCP** + **Spring Boot Starter** | FDE 写 MCP server 直接用 `@Tool` 注解 |
| Serverless Python 沙箱 | **OpenFaaS faasd + gVisor** | faasd 私有化，函数即 MCP server |
| Serverless 长驻 Docker | **K8s + faasd Profile** | 长驻服务用 K8s 部署 |
| 工具网关（聚合 + 鉴权） | **Envoy AI Gateway / MCP Gateway** | K8s 部署，Kuadrant AuthPolicy |
| 身份贯通（注入 X-User-Id） | **Kuadrant AuthPolicy** + Wristband | Envoy filter + RFC 8693 Token Exchange |
| 凭据托管 | **HashiCorp Vault** | Token/PAT/API Key 集中存储 |
| 工具动态编译 | **Claude Agent SDK** `mcp_servers` + `allowed_tools` | 平台预编译后注入 |
| 工具数 ≥ 50 优化 | **Claude Tool Search** | 自动启用 |
| HPA 横向扩缩 | **KEDA**（基于 K8s）或 faasd 内置 | 监控 CPU/QPS/并发 |
| 主从心跳与重启 | **faasd watchdog** + K8s LivenessProbe | 平台侧加 1 主 N 从编排 |
| 对象存储 | **MinIO** | 自托管 S3 兼容 |
| 缓存/会话 | **Redis** | 标准 |
| 容器镜像仓库 | **Harbor** | 自托管 |

---

## 7. 集成参考实现：Python 端到端示例

下面的代码展示 v2.0 主方案"**用户上传 Python 代码 → Serverless 沙箱 → 注册为 MCP 工具 → Agent 调用并注入 user_id**"的端到端骨架。

### 7.1 用户上传的 Python MCP 工具（FastMCP 风格）

```python
# presale_pdf_splitter/app.py  —— 用户上传的代码包
from fastmcp import FastMCP, Context

mcp = FastMCP("presale-pdf-splitter")

@mcp.tool()
async def split_pdf(file_id: str, max_pages: int, ctx: Context) -> dict:
    """按 user_id 鉴权后拆分 PDF。"""
    # ★ 关键：user_id 来自 MCP metadata，由平台 AuthGateway 注入
    user_id = ctx.request_context.meta.get("user_id")
    if not user_id:
        return {"error": "user_id missing"}

    # 按 user_id 鉴权（业务侧实现）
    if not file_service.user_can_read(user_id, file_id):
        return {"error": "permission_denied"}

    result = file_service.split(file_id, max_pages)
    return {"file_id": file_id, "parts": result.parts, "user_id": user_id}

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8080)
```

`manifest.yaml`：

```yaml
name: presale-pdf-splitter
language: python
runtime: sandbox          # 用 OpenFaaS faasd + gVisor
expose_as: mcp
entry: app:mcp
requirements: requirements.txt
port: 8080
scaling:
  base_replicas: 1
  min_replicas: 1
  max_replicas: 5
  hpa:
    cpu_percent: 70
    qps_per_instance: 50
user_permission:
  pass_user_id: true
  pass_via: header         # 同时写 header + metadata + payload
  header_name: X-User-Id
fallback:
  strategy: error_message
  error_message: "工具暂时不可用，已记录工单"
```

### 7.2 平台侧：CodeSandbox Runtime 注册 + 调用

```python
# tools_platform/code_sandbox_runtime.py
import httpx, yaml
from claude_agent_sdk import query, ClaudeAgentOptions
from pathlib import Path

class CodeSandboxRuntime:
    """把用户上传的代码包部署到 faasd 并自动注册为 MCP server。"""

    async def deploy(self, package_zip: Path, manifest: dict) -> dict:
        # 1) 上传到 faasd（faas-cli publish）
        await self._faas_publish(package_zip, manifest)

        # 2) 部署到 faasd（gVisor runtime）
        endpoint = await self._faas_deploy(manifest["name"], runtime="gvisor")

        # 3) 调用 __tools/list 拿工具清单
        async with httpx.AsyncClient() as c:
            r = await c.get(f"http://{endpoint}/__tools/list", timeout=10)
            tools = r.json()["tools"]

        # 4) 注册为 ConnectorSpec
        spec = ConnectorSpec(
            connector_id=f"usercode-{manifest['name']}",
            name=manifest["name"],
            kind=ConnectorKind.USER_CODE,
            endpoint=endpoint,
            tools=[t["name"] for t in tools],
            user_permission=UserPermission(
                pass_user_id=manifest["user_permission"]["pass_user_id"],
                pass_user_id_via=manifest["user_permission"]["pass_via"],
                pass_user_id_header=manifest["user_permission"].get("header_name", "X-User-Id"),
            ),
            fallback=FallbackPolicy(**manifest["fallback"]),
        )
        await self.registry.save(spec)
        return spec

    async def invoke(self, spec: ConnectorSpec, tool_name: str, args: dict, ctx: ToolInvokeContext) -> dict:
        """带 user_id 多通道透传的调用。"""
        # 多通道冗余注入：header + metadata + payload
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"{spec.endpoint}/mcp",
                json={
                    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": {**args, "user_id": ctx.user_id},   # 通道 3：payload
                        "_meta": {"user_id": ctx.user_id},              # 通道 2：MCP metadata
                    },
                },
                headers={
                    "X-User-Id": ctx.user_id,                          # 通道 1：header
                    "X-Team-Id": ctx.team_id,
                    "X-Trace-Id": ctx.trace_id,
                },
                timeout=30,
            )
        return r.json()
```

### 7.3 平台侧：编译 Agent 工具集

```python
# tools_platform/agent_compiler.py
async def compile_for_user(user_id: str, team_id: str, role: str, space_id: str) -> ClaudeAgentOptions:
    """v2.0 §9.1 的具体实现。"""
    catalog = await tool_catalog.list_for_user(user_id, team_id, space_id)

    mcp_servers, allowed = {}, []
    for conn in catalog:
        server_cfg = {
            "type": "http",
            "url": _endpoint_for(conn),
            "headers": {"X-User-Id": user_id},   # 默认注入
        }
        mcp_servers[conn.name] = server_cfg
        allowed.append(f"mcp__{conn.name}__*")

    return ClaudeAgentOptions(
        mcp_servers=mcp_servers,
        allowed_tools=allowed,
        tool_search=len(allowed) > 50,           # 工具数 ≥ 50 启用 Tool Search
    )
```

---

## 8. 集成参考实现：Java 端到端示例

### 8.1 Spring AI MCP 工具（用户上传 Java 代码）

```java
// com.example.demo.PresaleTools —— 用户上传的 Java 代码包
@RestController
public class PresaleTools {

    @Tool(description = "查询销售订单")
    public List<Order> queryOrders(
        @ToolParam(description = "客户ID") String customerId,
        @Meta(name = "user_id") String userId        // ★ 平台注入
    ) {
        if (!securityService.canReadOrders(userId, customerId)) {
            return List.of();
        }
        return orderRepo.findByCustomerAndUser(customerId, userId);
    }

    @Tool(description = "导出订单 CSV")
    public FileExport exportOrders(
        @ToolParam String customerId,
        @Meta(name = "user_id") String userId
    ) {
        // 审批级别工具，userId 绑定审计
        audit.log("export_orders", userId, customerId);
        return orderExportService.export(customerId, userId);
    }
}
```

### 8.2 Spring AI MCP Server Boot 配置

```yaml
# application.yml
spring:
  ai:
    mcp:
      server:
        name: presale-order-tools
        transport: streamable-http
        port: 8080
        security:
          oauth2:
            enabled: true
            issuer: https://keycloak.goktech.local/realms/goktech
            resource-indicator: https://mcp.goktech.local/presale-order  # RFC 8707
```

### 8.3 平台侧：Java 工具包部署

```python
# tools_platform/java_runtime.py
class JavaCodeSandboxRuntime(CodeSandboxRuntime):
    """Java 工具包部署：基础镜像 eclipse-temurin:21-jre。"""

    BASE_IMAGE = "eclipse-temurin:21-jre"
    BUILD_TOOL = "maven"   # 或 gradle

    async def deploy(self, package_zip, manifest):
        # 同 Python 流程，差异：
        # 1) 基础镜像换成 temurin
        # 2) mvn package → 生成 fat-jar
        # 3) 启动命令：java -jar app.jar
        # 4) 健康探针：/actuator/health
        return await super().deploy(package_zip, manifest)
```

---

## 9. 私有化部署清单

### 9.1 MVP 最小可交付栈

| 组件 | 选型 | 部署形态 | 资源估算 |
| --- | --- | --- | --- |
| **平台服务** | FastAPI + Postgres | 3 节点 K8s | 4 vCPU / 8GB / 节点 |
| **MCP 网关** | Envoy AI Gateway | 2 节点 K8s | 2 vCPU / 4GB / 节点 |
| **沙箱运行时** | faasd + gVisor | 3 节点（裸金属/K8s） | 8 vCPU / 16GB / 节点 |
| **长驻容器** | K8s（faasd profile） | 共用 faasd 集群 | 按工具数 |
| **镜像仓库** | Harbor | 2 节点（主备） | 4 vCPU / 8GB / 节点 |
| **凭据存储** | HashiCorp Vault | 2 节点 | 2 vCPU / 4GB / 节点 |
| **对象存储** | MinIO | 4 节点（纠删码） | 4 vCPU / 8GB / 节点 |
| **缓存** | Redis Sentinel | 3 节点 | 2 vCPU / 4GB / 节点 |
| **关系库** | Postgres 16 | 主从 | 4 vCPU / 16GB |
| **向量库** | pgvector | 复用 Postgres | — |
| **认证** | Keycloak | 2 节点 | 2 vCPU / 4GB / 节点 |
| **总规模** | — | — | **约 12 个节点 / 60 vCPU / 200GB RAM** |

### 9.2 快速验证栈（演示/PoC）

- 平台服务：1 节点 FastAPI + Supabase
- MCP 网关：1 节点 Envoy
- 沙箱：1 节点 faasd（gVisor）
- 长驻容器：本地 Docker
- 凭据：env var 即可（演示用）
- 规模：单台 8 vCPU / 32GB 即可跑通

### 9.3 网络与安全

- 沙箱默认禁止 egress；manifest 中显式声明白名单
- 平台 → 沙箱经内部 Service Mesh（Linkerd）通信
- 平台 → 外部 IdP 经 OAuth2 客户端凭据流
- 所有 API 调用全链路 trace（OpenTelemetry）

---

## 10. 风险与对账

| 风险 | 主选方案的应对 | 对账方式 |
| --- | --- | --- |
| 后端忽略 X-User-Id 导致越权 | 多通道注入（Header + MCP metadata + payload） | 平台定期对账：抽样审计 + 模糊测试 |
| Token 在 MCP server 间被重放 | RFC 8707 Resource Indicators + audience 声明 | Kuadrant AuthPolicy 检查 `aud` |
| 沙箱逃逸 | gVisor runsc（K8s）或 firecracker microVM | 每月红蓝对抗测试 |
| 工具膨胀 → Agent 选择困难 | 三维 ACL + user_id 过滤 + Tool Search（≥50 自动启用） | 工具数监控 + 定期清理 |
| Faasd gVisor 性能损耗 | gVisor 适合不可信代码；可信长驻用普通 Docker | 按工具类型分池 |
| Envoy 引入的运维成本 | Kuadrant CRD 统一管理；提供 Helm Chart | 客户内网部署时给完整 runbook |

---

## 11. 引用清单（deep research 来源）

| # | 标题 | 用途 |
| --- | --- | --- |
| [1] | MCP Server Frameworks and SDKs: A Developer's Guide — ChatForest | MCP SDK tier 分级、FastMCP 3.0 特性 |
| [2] | AI Code Sandbox Benchmark 2026 — Modal vs E2B vs Daytona vs Cloudflare vs Vercel vs Beam vs Blaxel — Superagent | 7 个 sandbox 厂商对比 |
| [3] | Serverless with Open Source in 2026: OpenFaaS vs Knative vs Nuclio — House of FOSS | 自托管 serverless 平台对比 |
| [4] | Advanced authentication and authorization for MCP Gateway — Red Hat Developer | Envoy MCP Gateway + Kuadrant + Wristband |
| [5] | gVisor runtime — OpenFaaS docs | faasd gVisor 安装与使用 |
| [6] | gVisor vs Firecracker in 2026: Choosing a Sandbox for Untrusted Workloads — Safeguard.sh | MicroVM 隔离对比 |
| [7] | OAuth in MCP: Threading User Identity Through Tool Servers — Tianpan.co | MCP 2026 Auth 规范、token 透传反模式 |
| [8] | Connect to external tools with MCP — Claude Agent SDK docs | Claude SDK mcp_servers + allowed_tools 用法 |
| [9] | Scale to many tools with tool search — Claude Code Docs | Tool Search 大规模工具集优化 |
| 附 | MCP Java SDK — github.com/modelcontextprotocol/java-sdk | Java SDK 与 Spring AI 集成 |

---

## 12. 结论与下一步

### 核心选型（"主选"清单）

| 能力 | 主选开源项目 | 关键理由 |
| --- | --- | --- |
| Python MCP 工具开发 | **FastMCP 3.0** | 占 MCP server 70% 份额，函数即工具，开发体验最好 |
| Java MCP 工具开发 | **Spring AI MCP + Spring Boot Starter** | Tier 2 / 100% Server conformance，注解式开发 |
| MCP 协议聚合网关 | **Envoy AI Gateway / MCP Gateway** | MCP + OpenAI + Anthropic 三协议统一聚合 |
| 身份贯通 | **Kuadrant AuthPolicy + Wristband + RFC 8693 Token Exchange** | 企业级 OAuth 2.1 完整实现 |
| Serverless 沙箱（轻量） | **faasd + gVisor** | 专为不可信代码设计，私有化友好 |
| Serverless 沙箱（GPU/高性能） | **Beam**（自托管） | 唯一开源支持 GPU 的方案 |
| Agent 工具集注入 | **Claude Agent SDK** `mcp_servers` + `allowed_tools` | 与 Anthropic SDK 零适配 |
| 大规模工具集优化 | **Claude Tool Search** | 工具 ≥ 50 自动启用 |
| 凭据托管 | **HashiCorp Vault** | 企业标准 |
| 镜像仓库 | **Harbor** | 自托管、企业级 |

### 售前一句话总结

> "工具管理平台以 **Claude Agent SDK + MCP** 为协议底座，**FastMCP + Spring AI MCP** 双栈开发，**OpenFaaS faasd + gVisor** 提供私有化 Serverless 沙箱，**Envoy MCP Gateway + Kuadrant** 实现用户身份贯通与细粒度权限，全部组件均可纯内网私有化部署。"

### 下一步建议

1. **PoC 阶段（2 周）**：用 FastMCP 3.0 写 1 个 Python MCP 工具 + 用 Spring AI MCP 写 1 个 Java MCP 工具，跑通"上传代码 → faasd gVisor 部署 → 注册 → Agent 调用 → X-User-Id 透传"端到端。
2. **MVP 阶段（4 周）**：在 PoC 基础上加上 Envoy MCP Gateway + Kuadrant，验证多 MCP server 聚合 + 身份细粒度授权。
3. **企业增强（4 周）**：Token Exchange + Wristband + Vault 集成，补齐审计与对账。
4. **横向扩展**：按客户需求补 C# / Go SDK 工具，引入 Beam 处理 GPU 类工具。
