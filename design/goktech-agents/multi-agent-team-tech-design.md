# goktech-agents 多智能体团队系统 技术方案

> 版本：v1.0
> 日期：2026-05-31
> 实现栈：Claude Agent SDK（Python, `claude-agent-sdk`）
> 关联文档：《多智能体团队系统 PRD》（同目录 `multi-agent-team-prd.md`）
> 定位：独立的新设计；可把团队导出为 DDMAO v2 `team.yaml` 资产

---

## 1. 概述

本方案给出多智能体团队系统（MATS）的工程落地设计，覆盖四个核心需求：

1. **动态组建团队**：从一句团队目标，经澄清问答，自动产出角色与技能蓝图，检索并复用已有 skills/plugins，未命中的用 prompt 兜底，最终实例化一支团队。
2. **Leader 任务分解与分配**：默认一个具备 planning 能力的 Leader，对团队问题做分解、形成任务列表、分配给子智能体并调度执行、汇总结果。
3. **运行中人工干预**：用户随时插话，Leader 判断是否中断某个 Agent、对任务列表做增删改查、令某 Agent 重做某任务。
4. **Leader 中心化协调**：Agent 间不直接通信，所有协调与讨论经 Leader 中转并全程留痕。

### 1.1 设计取舍（关键决策）

| 决策点 | 选择 | 理由 |
| --- | --- | --- |
| 实现栈 | Python `claude-agent-sdk` | 与团队既有技术栈一致，异步原语完善，便于自建编排层 |
| 与 DDMAO v2 关系 | 独立新设计 | 面向实训营/MVP 的轻量路线，不背负重型编排器；可向 v2 演进 |
| teammate 运行机制 | **混合模式** | 一次性任务用无状态 subagent，省 token；需要中断/迭代/讨论的角色升级为持久会话 |
| 通信拓扑 | 星形（Leader 中转） | 满足需求 4，可观测、可审计、易控制 |
| 状态权威 | 编排层（非 LLM） | LLM 只提建议，任务状态由确定性的 TaskStore 维护 |

### 1.2 SDK 能力对照

Claude Agent SDK 原生不提供 Agent Teams / Mailbox / 共享任务列表，需自建。本方案使用的 SDK 原语：

| 需求 | SDK 原语 | 用途 |
| --- | --- | --- |
| 持久、可中断的 Agent | `ClaudeSDKClient`（异步上下文管理器） | 持久会话 teammate，支持 `interrupt()` |
| 一次性子任务 | `query()` | 无状态 subagent，结果回传即销毁 |
| 角色能力封装 | `AgentDefinition` + `ClaudeAgentOptions(agents=...)` | 用 SDK 子代理机制承载角色 |
| 自定义工具 | `@tool` + `create_sdk_mcp_server` | 把"汇报给 Leader""读写 Artifact"做成工具 |
| 技能/插件接入 | `setting_sources` / `mcp_servers` / `allowed_tools` | 复用平台已有 skills、plugins |
| 模型分层 | `ClaudeAgentOptions(model=...)` per agent | Leader 用 Opus，Worker 用 Sonnet/Haiku |
| 中断 | `client.interrupt()` | 运行中干预时打断正在跑的 Agent |
| 流式观测 | `async for msg in client.receive_response()` | 实时把消息推到协作时间线 |

---

## 2. 总体架构

### 2.1 架构分层

MATS 分为四层：交互层、编排层（Orchestrator，确定性核心）、Agent 运行层、状态与资产层。

```text
交互层    Web UI：组队向导 | 团队总览 | 任务看板 | 协作时间线
            │  WebSocket（流式消息/状态）
编排层    Orchestrator（确定性核心，非 LLM 控状态）
          ├─ TeamBuilder      组队引擎：澄清→蓝图→技能匹配→实例化
          ├─ LeaderRuntime    Leader 会话：分解/分配/调度/汇总
          ├─ TaskStore        任务列表权威状态（CRUD + 依赖 + 状态机）
          ├─ MessageBus       Leader 中转消息总线（星形拓扑）
          ├─ AgentPool        teammate 生命周期（持久会话/一次性）
          └─ SkillRegistry    skills/plugins 索引与匹配
Agent层   Leader(ClaudeSDKClient) ─ 中转 ─ Worker A/B/C（混合机制）
状态层    Postgres（团队/任务/审计） | 对象存储（Artifact） | 向量索引（技能匹配）
```

### 2.2 组件职责

| 组件 | 职责 | 是否 LLM |
| --- | --- | --- |
| `TeamBuilder` | 解析目标、生成澄清问题、产出团队蓝图、调用技能匹配、实例化团队 | 部分（蓝图生成用 LLM） |
| `LeaderRuntime` | 承载 Leader 持久会话，驱动分解/分配/调度/汇总/干预决策 | 是 |
| `TaskStore` | 任务列表的权威状态：CRUD、依赖图、状态机流转 | 否（确定性） |
| `MessageBus` | 星形拓扑消息中转，Leader↔Worker 单跳，全量留痕 | 否 |
| `AgentPool` | 创建/复用/销毁 teammate，管理持久会话与一次性任务 | 否 |
| `SkillRegistry` | 索引 skills/plugins/command，提供语义匹配与绑定 | 检索（embedding） |
| `ArtifactStore` | 存放 Agent 产物，供 Leader 汇总与下游引用 | 否 |
| `AuditLog` | 记录组队、分配、状态变更、干预、消息等事件 | 否 |

### 2.3 控制反转：LLM 提建议，编排层定状态

核心原则：**Leader（LLM）输出的是"意图"（JSON 指令），编排层执行并写状态**。Leader 不直接修改 TaskStore，而是产出结构化指令（如 `assign_task`、`interrupt_agent`、`update_task`），由 Orchestrator 校验后执行。这样保证任务状态可审计、可恢复，避免 LLM 幻觉直接污染系统状态。

---

## 3. 动态组建团队（需求 1）

### 3.1 组队流水线

```text
团队目标(自然语言)
   │
   ▼ TeamBuilder.analyze_goal()      ← LLM：理解目标，产出澄清问题(3–5)
澄清问题  ──►  用户回答
   │
   ▼ TeamBuilder.draft_blueprint()   ← LLM：产出 TeamBlueprint(角色/技能/产出契约)
   │
   ▼ SkillRegistry.match()           ← 检索：每个技能项 → 已有 skill/plugin 或 prompt 兜底
   │
   ▼ 用户确认/微调(增删角色、改技能)
   │
   ▼ AgentPool.instantiate(team)     ← 创建 Leader + N Worker
   │
   ▼ 团队就绪（可保存为模板）
```

### 3.2 团队蓝图数据模型

```python
from dataclasses import dataclass, field

@dataclass
class SkillBinding:
    name: str                 # 技能逻辑名
    source: str               # "skill" | "plugin" | "command" | "prompt"
    ref: str | None = None    # 命中时的 skill/plugin 标识
    prompt_fallback: str | None = None  # 未命中时现场构造的能力描述

@dataclass
class RoleSpec:
    role_id: str
    name: str                 # 如 "需求分析师"
    description: str
    is_leader: bool = False
    model: str = "claude-sonnet-4-6"
    skills: list[SkillBinding] = field(default_factory=list)
    output_contract: str = "" # 产出契约（结构化模板）

@dataclass
class TeamBlueprint:
    team_id: str
    goal: str
    roles: list[RoleSpec]
    topology: str = "star"    # 星形：Leader 中转
```

### 3.3 技能匹配引擎（复用已有 skills/plugins）

平台 skill 以 `SKILL.md` frontmatter（`name` + `description`）描述，plugin 以 `installed_plugins.json` 登记。匹配流程：

1. **索引构建**：启动时扫描 `~/.claude/skills/*/SKILL.md` 与 plugins 目录，对每个 skill/plugin/command 的 `name + description` 做 embedding，写入向量索引。
2. **语义召回**：对蓝图中每个技能项，用其描述向量检索 Top-K 候选。
3. **阈值判定**：相似度 ≥ 阈值 → 绑定为 `source="skill"/"plugin"`；否则进入兜底。
4. **Prompt 兜底**：未命中项由 LLM 生成一段能力描述，作为该角色 system prompt 的一部分（`source="prompt"`）。

```python
def match_skill(query: str, top_k=5, threshold=0.78) -> SkillBinding:
    hits = vector_index.search(embed(query), top_k=top_k)
    if hits and hits[0].score >= threshold:
        h = hits[0]
        return SkillBinding(name=query, source=h.kind, ref=h.id)
    # 未命中：用 prompt 现场构造能力
    cap = llm_generate_capability_prompt(query)
    return SkillBinding(name=query, source="prompt", prompt_fallback=cap)
```

### 3.4 团队实例化（映射到 SDK）

每个角色编译为一个 `AgentDefinition`；技能绑定转换为该角色的 `allowed_tools`（命中 skill/plugin）与 `prompt` 增量（prompt 兜底）。Worker 默认通过持有这些 `agents` 的运行容器承载。

```python
from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions

def compile_role(role: RoleSpec) -> AgentDefinition:
    base = f"你是{role.name}。{role.description}\n产出契约：\n{role.output_contract}"
    fallbacks = [s.prompt_fallback for s in role.skills if s.source == "prompt"]
    prompt = base + ("\n\n额外能力：\n" + "\n".join(fallbacks) if fallbacks else "")
    tools = [s.ref for s in role.skills if s.source in ("skill", "plugin", "command")]
    return AgentDefinition(
        description=role.description,
        prompt=prompt,
        tools=tools or None,
        model="opus" if role.is_leader else "sonnet",
    )
```

> 说明：命中的 skill/plugin 通过平台 MCP server 暴露为工具，`tools` 引用其工具名；`setting_sources=["user","project"]` 使 SDK 加载已安装的技能与插件。

---

## 4. Leader 任务分解与分配（需求 2）

### 4.1 任务数据模型

```python
from enum import Enum

class TaskStatus(str, Enum):
    TODO = "todo"; ASSIGNED = "assigned"; RUNNING = "running"
    DONE = "done"; REWORK = "rework"; BLOCKED = "blocked"; CANCELLED = "cancelled"

@dataclass
class Task:
    task_id: str
    title: str
    detail: str
    assignee_role: str            # 负责的角色 role_id
    depends_on: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.TODO
    mode: str = "serial"          # serial | parallel | discussion
    result_ref: str | None = None # 产物 Artifact 引用
    attempt: int = 0
```

TaskStore 是任务列表的**唯一权威**，提供 `create/read/update/delete/list`、依赖图维护、状态机校验（非法流转拒绝），并对每次变更写 AuditLog。

### 4.2 Leader 的工具集（编排指令）

Leader 不直接改状态，而是调用一组自定义工具，由 Orchestrator 落地。用 SDK 的 `@tool` + `create_sdk_mcp_server` 暴露：

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("create_tasks", "创建任务列表", {"tasks": list})
async def create_tasks(args):
    ids = task_store.bulk_create(args["tasks"])  # 校验依赖 + 写状态
    return {"content": [{"type": "text", "text": f"created: {ids}"}]}

@tool("assign_task", "把任务分配给某角色并指定执行模式",
      {"task_id": str, "role_id": str, "mode": str})
async def assign_task(args):
    task_store.assign(args["task_id"], args["role_id"], args["mode"])
    return {"content": [{"type": "text", "text": "assigned"}]}

@tool("dispatch", "下发已分配任务给 Worker 执行", {"task_id": str})
async def dispatch(args):
    await orchestrator.dispatch(args["task_id"])
    return {"content": [{"type": "text", "text": "dispatched"}]}

leader_tools = create_sdk_mcp_server(
    "leader_ctrl", "1.0",
    [create_tasks, assign_task, dispatch],
)
```

### 4.3 Leader 运行时（持久会话）

Leader 用 `ClaudeSDKClient` 持久会话承载，便于后续接收用户插话与中断。

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

leader_opts = ClaudeAgentOptions(
    model="opus",
    system_prompt="你是团队 Leader，具备 planning 能力。"
                  "负责把团队问题分解为带依赖的任务列表，分配给合适角色，"
                  "选择执行模式(serial/parallel/discussion)，"
                  "并在所有任务完成后汇总为最终交付物。"
                  "你只能通过 leader_ctrl 工具改动任务，不要臆造状态。",
    mcp_servers={"leader_ctrl": leader_tools},
    allowed_tools=["mcp__leader_ctrl__create_tasks",
                   "mcp__leader_ctrl__assign_task",
                   "mcp__leader_ctrl__dispatch"],
    setting_sources=["user", "project"],
)

async def run_leader(problem: str):
    async with ClaudeSDKClient(options=leader_opts) as leader:
        await leader.query(f"团队问题：{problem}\n请分解、分配并开始调度。")
        async for msg in leader.receive_response():
            await timeline.push(msg)     # 流式推送到协作时间线
```

### 4.4 调度模式

Orchestrator 的 `dispatch` 根据任务 `mode` 与依赖图调度：

| 模式 | 触发条件 | 执行 |
| --- | --- | --- |
| serial | 任务有未完成的 `depends_on` | 依赖全 `done` 后才进入 ready，逐个执行 |
| parallel | 多个 ready 任务且无相互依赖 | `asyncio.gather` 并发执行，受团队并发上限约束 |
| discussion | 任务标 `discussion` | Leader 串行征询相关角色意见，汇总后产出（见 §6.2） |

调度主循环（确定性）：

```python
async def scheduler_loop(team):
    while not task_store.all_terminal():
        ready = task_store.ready_tasks()          # 依赖满足 & status=assigned
        parallel = [t for t in ready if t.mode == "parallel"]
        serial   = [t for t in ready if t.mode == "serial"]
        if parallel:
            await asyncio.gather(*(run_worker(team, t) for t in parallel[:team.max_parallel]))
        elif serial:
            await run_worker(team, serial[0])
        else:
            await asyncio.sleep(0.2)              # 等待干预或讨论解阻塞
    await leader_summarize(team)                  # 汇总
```

---

## 5. Worker 执行（混合机制）

### 5.1 两种 Worker，按需选择

| 机制 | SDK 原语 | 适用 | 优势 | 代价 |
| --- | --- | --- | --- | --- |
| 一次性 Worker | `query()` | 无需中断/迭代的独立子任务 | token 省、无状态、易并发 | 不可中途中断 |
| 持久会话 Worker | `ClaudeSDKClient` | 需中断/多轮迭代/参与讨论 | 可 `interrupt()`、可追问 | 占用会话、成本高 |

选择规则：任务 `mode == "discussion"` 或角色被标记为"可能被干预"→ 持久会话；其余默认一次性。

### 5.2 一次性 Worker

```python
from claude_agent_sdk import query, ClaudeAgentOptions

async def run_worker_oneshot(team, task):
    role = team.role(task.assignee_role)
    opts = ClaudeAgentOptions(
        model=role.model,
        system_prompt=role.system_prompt,
        agents={r.role_id: compile_role(r) for r in team.roles},
        setting_sources=["user", "project"],
    )
    task_store.set_status(task.task_id, TaskStatus.RUNNING)
    out = []
    async for msg in query(prompt=build_task_prompt(task), options=opts):
        out.append(msg); await timeline.push(msg)
    ref = artifact_store.save(task.task_id, out)
    # 结果经 MessageBus 回报 Leader（中转），不直接写他人状态
    await bus.report_to_leader(task.task_id, ref)
    task_store.set_result(task.task_id, ref, TaskStatus.DONE)
```

### 5.3 持久会话 Worker

持久 Worker 注册到 `AgentPool`，保留 `ClaudeSDKClient` 句柄，使 Orchestrator 能对其 `interrupt()`。

```python
class PersistentWorker:
    def __init__(self, team, role):
        self.role = role
        self.client = ClaudeSDKClient(options=ClaudeAgentOptions(
            model=role.model, system_prompt=role.system_prompt,
            setting_sources=["user", "project"]))
        self._task = None  # 当前运行的 asyncio.Task

    async def open(self):  await self.client.connect()

    async def run(self, task):
        task_store.set_status(task.task_id, TaskStatus.RUNNING)
        await self.client.query(build_task_prompt(task))
        out = []
        async for msg in self.client.receive_response():
            out.append(msg); await timeline.push(msg)
        ref = artifact_store.save(task.task_id, out)
        await bus.report_to_leader(task.task_id, ref)
        task_store.set_result(task.task_id, ref, TaskStatus.DONE)

    async def interrupt(self):
        await self.client.interrupt()   # 打断正在进行的生成
```

`AgentPool` 负责创建、复用、关闭（`async with` 或显式 `disconnect`）持久 Worker，并维护 `role_id → PersistentWorker` 映射。

---

## 6. Leader 中心化协调（需求 4）

### 6.1 星形拓扑与 MessageBus

Worker 之间**没有**直接通道。所有消息经 `MessageBus` 单跳中转，且全量落 AuditLog。消息结构：

```python
@dataclass
class Message:
    msg_id: str
    sender: str        # role_id 或 "leader" / "user"
    recipient: str     # 总是 "leader" 或由 leader 指定的 role_id
    kind: str          # report | instruction | discussion | intervention
    payload: dict
    ts: float
```

`MessageBus` 强制约束：`sender` 为 Worker 时，`recipient` 只能是 `"leader"`；Worker→Worker 直发被拒绝。Leader 是唯一可把消息转发给具体 Worker 的角色。

### 6.2 讨论模式（经 Leader 中转）

首版的"讨论"不是 Worker 间自由协商，而是 **Leader 主持的串行征询**：

```text
讨论任务
   │
   ▼ Leader 拟定讨论提纲与参与角色
   ▼ for role in participants:           ← 串行，经 bus 中转
        Leader → role：抛出问题/上文
        role  → Leader：返回意见
   ▼ Leader 汇总各方意见 → 形成结论/决策
   ▼ 把结论作为该讨论任务的产物
```

这样既满足"多角色协作 + 交叉验证"，又保证全程可观测、可审计，避免自由协商的失控。后续版本可在稳定后引入受控的多轮协商。

### 6.3 为什么不用 SDK 子代理的隐式委派

SDK 的 `agents=` 机制会让主 Agent 自行决定调用哪个子代理，委派路径对编排层不透明。MATS 需要**显式控制**分配与中转，因此采用"Leader 产出指令 → Orchestrator 执行 → MessageBus 中转"的显式路径，子代理机制仅用于封装角色能力（system prompt + 工具），不用于隐式编排。

---

## 7. 运行中人工干预（需求 3）

### 7.1 干预流水线

```text
用户插话（新要求/约束/纠偏）
   │
   ▼ 作为 user 消息进 MessageBus → 注入 Leader 会话
   ▼ Leader 评估影响 → 产出干预指令(JSON)：
       • interrupt_agent(role_id)        是否中断正在跑的 Agent
       • update_task / add_task / delete_task   任务 CRUD
       • rework_task(task_id, role_id)   令某 Agent 重做
   ▼ Orchestrator 校验并执行（确定性）
   ▼ Leader 向用户说明：调整方案 + 影响范围
   ▼ scheduler_loop 按新状态继续
```

### 7.2 中断正在执行的 Agent

只有持久会话 Worker 可被中断。一次性 Worker 通过取消其 `asyncio.Task` 实现"软中断"（丢弃结果、标记为 cancelled）。

```python
async def apply_intervention(team, directive: dict):
    # 1) 中断
    for rid in directive.get("interrupt", []):
        w = pool.get(rid)
        if isinstance(w, PersistentWorker):
            await w.interrupt()
        else:
            pool.cancel_oneshot(rid)             # 取消 asyncio.Task
        task_store.mark_interrupted(rid)

    # 2) 任务 CRUD（确定性校验：依赖、环检测、状态合法性）
    for op in directive.get("task_ops", []):
        task_store.apply_op(op)                  # add/update/delete

    # 3) 重做：重置 attempt 与状态，重新进 ready
    for r in directive.get("rework", []):
        task_store.requeue(r["task_id"], r["role_id"])

    audit.log("intervention", directive)
```

### 7.3 干预的并发安全

干预与调度可能并发改任务，需用 **TaskStore 级别的锁 / 单写者队列**保证一致性：所有状态写入串行化到一个事件循环任务里，Leader 指令与 scheduler 的状态变更都经同一队列，避免竞争。

---

## 8. 任务状态机

Task 状态流转（编排层校验，非法流转拒绝）：

- `todo` → `assigned`：Leader 分配角色后
- `assigned` → `running`：依赖满足并被 dispatch
- `running` → `done`：Worker 产出且回报 Leader
- `running` → `rework`：Leader 校验不通过或用户要求重做 → 重置后回 `assigned`
- `running` → `cancelled`：被干预中断且不重做
- `*` → `blocked`：依赖失败或缺输入，等待干预解阻塞

---

## 9. 端到端示例：电网 AI 售前方案团队

1. **组队**：用户输入"组一支做电网 AI 售前方案的团队"。TeamBuilder 反问 3 题（交付物形式 / 客户细分 / 是否要竞品分析），产出蓝图：`需求分析师`、`方案撰写`、`竞品调研`、`评审`（+ Leader）。SkillRegistry 命中 `presales-req-analysis`、`competitor-analysis` 直接绑定，"评审"用 prompt 兜底。用户确认。
2. **分解**：用户给问题"基于这份招标文件输出应答方案"。Leader 调 `create_tasks` 生成：T1 解析招标(需求分析师) → T2 提取评分项(需求分析师) → [T3 撰写技术章节(方案撰写) ∥ T4 竞品对比(竞品调研)] → T5 汇总评审(评审)。
3. **执行**：T1/T2 serial；T3/T4 parallel 并发；Worker 产出经 bus 回报 Leader。
4. **干预**：T3 进行中用户插话"竞品要重点对比 XX 厂商"。Leader 产出干预指令：interrupt 竞品调研、给 T4 update 约束、T3 标记 rework。Orchestrator 执行并向用户说明影响（T3 将重做，T1/T2 不受影响）。
5. **汇总**：全部 done 后 Leader 串联各产物，输出一版完整应答方案。团队可保存为模板。

---

## 10. 技术栈与持久化

| 层 | 选型 | 说明 |
| --- | --- | --- |
| Agent 运行 | `claude-agent-sdk`（Python） | `query()` 一次性 / `ClaudeSDKClient` 持久 |
| 编排服务 | FastAPI + asyncio | 单进程事件循环承载 Orchestrator |
| 实时通道 | WebSocket | 把 timeline/状态流式推前端 |
| 状态库 | Postgres | teams / roles / tasks / messages / audit_events |
| Artifact | 对象存储（MinIO/S3） | Worker 产物，按 task_id 归档 |
| 技能索引 | 向量库（pgvector/Chroma） | skills/plugins 的 embedding 匹配 |
| 技能/插件来源 | `setting_sources=["user","project"]` | 复用 `~/.claude/skills`、已安装 plugins |

**状态权威**：TaskStore 在内存维护运行态，每次变更同步 append 到 Postgres `audit_events`，并更新 `tasks` 快照表，支持崩溃恢复（重放事件 + 快照）。

**模型分层**：Leader=Opus（强 planning）；Worker 默认 Sonnet；轻量抽取/格式化类任务可降级 Haiku。每角色可在蓝图覆盖。

---

## 11. MVP 范围与实施阶段

### 11.1 MVP 必含

1. TeamBuilder：目标→澄清(固定3–5题)→蓝图→技能匹配→实例化。
2. SkillRegistry：skills/plugins 索引 + 语义匹配 + prompt 兜底。
3. Leader 持久会话 + `create_tasks/assign_task/dispatch` 工具。
4. TaskStore：CRUD + 依赖图 + 状态机 + 审计。
5. Worker 混合机制：一次性 `query()` + 持久 `ClaudeSDKClient`。
6. 调度：serial / parallel。
7. MessageBus 星形中转 + 全量留痕。
8. 干预：interrupt + 任务 CRUD + rework + 影响说明。
9. WebSocket 推送任务看板与协作时间线。

### 11.2 MVP 暂不含

- 复杂多轮自由协商（讨论模式首版仅 Leader 串行征询）。
- 团队模板市场、跨团队共享。
- 细粒度沙箱/网络/Secret 权限（对齐 DDMAO v2，后续引入）。
- 预算上限自动暂停（先只统计，不强制）。

### 11.3 并行实施 lanes

```text
Lane A: TaskStore + 状态机 + Postgres（无依赖）
Lane B: SkillRegistry 索引/匹配（无依赖）
Lane C: SDK 封装：一次性/持久 Worker、AgentPool
After A+C: Lane D: Orchestrator 调度 + MessageBus
After B:   Lane E: TeamBuilder 组队流水线
After D:   Lane F: 干预与中断
最后：Lane G: WebSocket + 前端看板/时间线，E2E 串联
```

---

## 12. 风险与应对

| 风险 | 表现 | 应对 |
| --- | --- | --- |
| SDK 持久会话/中断能力不达预期 | `interrupt()` 行为不稳定 | 最小原型先验证；不达标则全用一次性 Worker + 软取消 |
| Leader 幻觉产出非法任务图 | 环依赖、引用不存在角色 | TaskStore 确定性校验，拒绝并要求 Leader 重提 |
| 技能匹配召回差 | 命中率低、错绑 | 阈值 + 人工确认环节；持续补 skill 元数据 |
| Leader 中心化瓶颈 | 大团队延迟高 | 团队规模 ≤6；Leader 只做编排不做重活 |
| Token 成本 | 并行多 Worker 翻倍 | 按需唤醒、Worker 降级模型、一次性优先 |
| 干预与调度竞争 | 状态写冲突 | 单写者队列串行化所有状态变更 |
| 上下文不继承 | Worker 缺背景 | Context Builder 注入最小必要上下文 + Artifact 引用 |

---

## 13. 测试策略

| 模块 | 必测 |
| --- | --- |
| TaskStore | CRUD、依赖图、环检测、非法状态流转拒绝 |
| SkillRegistry | 命中绑定、未命中兜底、阈值边界 |
| TeamBuilder | 澄清生成、蓝图结构、实例化 AgentDefinition 正确 |
| Scheduler | serial 依赖阻塞、parallel 并发上限、ready 选择 |
| MessageBus | Worker→Worker 直发被拒、中转留痕完整 |
| 干预 | 持久 Worker interrupt、一次性软取消、rework 重排、并发安全 |
| 汇总 | 多产物串联、缺产物时的阻塞与提示 |
| E2E | §9 全流程：组队→分解→并行执行→干预重做→汇总 |

---

## 14. 结论

MATS 用"对话式动态组队 + Leader 中心化智能调度 + 人在环干预"覆盖四条核心需求，落点在 Claude Agent SDK（Python）：一次性 `query()` 与持久 `ClaudeSDKClient` 的混合机制兼顾成本与可控，自建的 TaskStore / MessageBus / Orchestrator 补齐 SDK 不原生支持的团队协作能力，并坚持"LLM 提建议、编排层定状态"以保证可观测、可审计、可恢复。建议先按 §11 跑通 MVP 闭环，再逐步引入讨论协商、权限沙箱与预算控制，并在成熟后把团队导出为 DDMAO v2 `team.yaml` 资产。
