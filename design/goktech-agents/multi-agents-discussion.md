# 多 Agent 协作平台技术方案讨论稿

**日期：** 2026-05-20
**参与：** 技术团队
**状态：** 进行中

---

## 一、背景与目标

### 1.1 项目背景

当前已基于 Claude Agent SDK 实现单 Agent 运行，需要扩展为多 Agent 协作平台，支持：

- **多个业务场景**：业务流程自动化，知识管理与问答、运维智能化（AIOps/FinOps）
- **团队协作模式**：Leader Agent 指挥 + 专业 Agent 执行 + 灵活协作
- **企业级特性**：任务状态管理、失败重试、审计追溯

### 1.2 核心需求

| 需求 | 说明 |
|------|------|
| Leader Agent | 任务分解、调度、结果汇总 |
| 专业 Agent (3-5个) | 方案编写、审核、调研、FinOps 等 |
| 通信模式 | Leader 中转为主，Agent 间必要时直接通信 |
| 任务类型 | 灵活组合：并行、串行、讨论协作 |
| 状态管理 | 任务状态可查、失败可重试 |

---

## 二、Claude Code Agent Teams 研究

### 2.1 什么是 Agent Teams

Claude Code Agent Teams 是 Anthropic 在 2026 年 2 月推出的实验性功能，允许创建多个 AI 智能体组成"开发团队"并行处理复杂任务。

### 2.2 核心架构：星形拓扑

```
         User（你）
            │
            ▼
    ┌─────────────────┐
    │   Team Lead      │ ← 主会话，负责创建团队、分配任务、汇总结果
    └────────┬────────┘
             │
    ┌────────┼────────┐
    ▼        ▼        ▼
 ┌──────┐ ┌──────┐ ┌──────┐
 │ Teammate │Teammate│ Teammate │
 │   A    │   B    │   C    │
 └────────┘ └──────┘ └──────┘
```

### 2.3 四大核心组件

| 组件 | 说明 | 存储位置 |
|------|------|---------|
| **Team Lead** | 主会话，负责协调、分配、汇总 | 当前终端 |
| **Teammates** | 独立 Claude 实例，拥有独立上下文 | `~/.claude/teams/{team-name}/` |
| **Task List** | 带依赖关系的任务队列，自动阻塞/解阻塞 | `~/.claude/tasks/{team-name}/` |
| **Mailbox** | 消息系统，Agent 间可直接通信 | 内存 + 文件 |

### 2.4 Subagent vs Agent Teams

| 维度 | Subagent | Agent Teams |
|------|----------|-------------|
| **通信方式** | 仅向主 Agent 汇报 | Teammate 间可直接 P2P 通信 |
| **上下文** | 独立窗口，结果摘要回传 | 各自完全独立，互不继承 |
| **Token 开销** | 较低（摘要回传） | 较高（每个实例独立消耗） |
| **协调机制** | 主 Agent 全权调度 | 共享任务列表，支持自我认领 |
| **适用场景** | 专注任务、单一结果 | 讨论、交叉验证、并行探索 |
| **稳定性** | 正式发布 | 实验性（需手动开启） |

### 2.5 Claude Agent SDK 支持情况

| 功能 | Claude Code | Claude Agent SDK |
|------|-------------|-----------------|
| **Agent Teams** | ✅ 实验性功能 | ❌ 不支持 |
| **Mailbox** | ✅ Agent Teams 实验性功能 | ❌ 不支持 |
| **Subagent** | ✅ 正式功能 | ⚠️ 仅基础支持 |
| **Task List** | ✅ Agent Teams 实验性功能 | ❌ 不支持 |

**结论**：Mailbox 是 Claude Code 内部的实验性功能，Claude Agent SDK 不直接支持。需要自建实现。

### 2.6 启用方式

```json
// ~/.claude/settings.json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  },
  "teammateMode": "tmux",
  "model": "opus",
  "agentSettings": {
    "teammateModel": "sonnet"
  }
}
```

### 2.7 协作模式

#### 模式 1：并行探索
```
Team Lead: "分析这个代码库"
    │
    ├── Teammate A（安全审查）→ 并行执行
    ├── Teammate B（性能分析）→ 并行执行
    └── Teammate C（测试覆盖）→ 并行执行
```

#### 模式 2：讨论协作
```
Teammate A（编写方案）←──→ Teammate B（审核反馈）
         │                        │
         └─────── Mailbox ───────┘
```

#### 模式 3：流水线
```
Task 1（探索） → Task 2（编写） → Task 3（审核） → Task 4（测试）
```

### 2.8 限制与注意事项

1. **实验性功能**：Agent Teams 仍为实验性，需开启标志
2. **成本较高**：每个 Teammate 是完整 Claude 实例，5人团队 ≈ 5倍 Token
3. **上下文不继承**：创建时必须提供完整上下文
4. **文件冲突**：尽量分配不同文件给不同 Agent
5. **生产环境建议**：截至 2026 年 4 月，稳定性关键路径建议继续使用 Subagent 架构

---

## 三、技术方案对比

### 3.1 Agent 间通信方案

| 方案 | 实现方式 | 优点 | 缺点 | 适用场景 |
|------|---------|------|------|---------|
| **Leader 中转** | Leader 持有所有上下文，分发给各 Agent | 简单、容易控制 | Leader 单点负载高 | 小团队、简单任务 |
| **共享上下文** | 所有 Agent 读写同一个 Context/Store | 透明、无需复杂通信 | 并发写有冲突风险 | 需要共同数据的场景 |
| **消息队列** | Agent 通过 Queue 传递消息（Redis/RabbitMQ） | 解耦、异步、可靠 | 架构复杂 | 生产环境、高并发 |
| **直接通信** | Agent 之间直接调用 | 低延迟、实时 | 耦合度高 | 紧密协作的场景 |

### 3.2 框架对比

| 框架 | 通信模式 | 状态管理 | 适合场景 | 学习曲线 |
|------|---------|---------|---------|---------|
| **LangGraph** | 图结构 + 状态流转 | 内置 StateGraph | 多 Agent 协作编排 | 中等 |
| **AutoGen** | 消息传递 | 外部存储 | 对话式 Agent | 低 |
| **CrewAI** | 任务层级 | 外部存储 | 角色扮演团队 | 低 |
| **自研** | 灵活 | 自定义 | 深度定制 | 高 |

### 3.3 状态存储方案

| 方案 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| **内存模式** | 开发测试 | 简单、无额外依赖 | 重启丢失 |
| **Redis** | 高性能要求 | 高速读写、支持发布订阅 | 无持久化（需 RDB/AOF） |
| **PostgreSQL** | 企业级应用 | 完整审计日志、事务支持 | 相对较重 |
| **Redis + PostgreSQL** | 生产环境 | 高速 + 持久化 | 架构复杂 |

---

## 四、推荐方案

### 4.1 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                        用户层                               │
│                   API / Web UI                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Leader Agent                              │
│  • 任务理解与分解                                          │
│  • 调度策略（并行/串行/讨论）                              │
│  • 结果汇总与返回                                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    消息总线层                                 │
│  • Redis Streams（异步消息队列）                            │
│  • 消息持久化与消费确认                                    │
│  • 支持 Agent 间直接通信                                    │
└─────────────────────────────────────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Agent A    │  │  Agent B    │  │  Agent C    │
│  方案编写    │  │  方案审核    │  │  调研分析    │
└──────────────┘  └──────────────┘  └──────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    状态存储层                                 │
│  • PostgreSQL：任务状态、审计日志、执行历史                  │
│  • Redis：热点数据缓存                                     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 技术栈选择

| 组件 | 推荐技术 | 原因 |
|------|---------|------|
| **Agent SDK** | Claude Agent SDK | 已基于此实现单 Agent |
| **编排框架** | LangGraph | 原生支持 Supervisor、状态管理、条件路由 |
| **消息队列** | Redis Streams | 支持持久化、消费确认、消息重试 |
| **状态存储** | PostgreSQL | 审计日志、任务历史、失败重试 |
| **通信模式** | Leader 中转 + Mailbox | 符合 Agent Teams 设计理念 |

### 4.3 核心实现

#### Leader Agent 实现

```python
from langgraph.graph import StateGraph
from dataclasses import dataclass
from typing import List, Literal

@dataclass
class TeamState:
    messages: List[dict]           # 对话历史
    task: str                      # 当前任务
    writer_result: str = None       # 方案草稿
    reviewer_feedback: str = None   # 审核意见
    writer_status: str = "idle"    # idle/running/done
    reviewer_status: str = "idle"

def leader_node(state: TeamState) -> TeamState:
    """Leader: 分解任务，决定调度策略"""
    if needs_parallel(state.task):
        # 并行调度
        return route_to_parallel_agents(state)
    elif needs_discussion(state.task):
        # 讨论模式：Agent 间直接通信
        return route_for_discussion(state)
    else:
        # 串行
        return route_sequential(state)

def writer_node(state: TeamState) -> TeamState:
    """Writer: 编写方案，可与 Reviewer 讨论"""
    # 调用 Claude Agent SDK
    result = claude_agent.run(
        prompt=f"编写方案: {state.task}",
        tools=[...]
    )
    # 通过 Redis 发布消息给 Reviewer
    redis.publish("agent:reviewer", {"type": "draft", "content": result})
    return {"writer_result": result, "writer_status": "done"}

def reviewer_node(state: TeamState) -> TeamState:
    """Reviewer: 审核方案，可直接与 Writer 讨论"""
    # 订阅 Redis 消息
    msg = redis.subscribe("agent:reviewer")
    feedback = claude_agent.run(
        prompt=f"审核方案: {msg['content']}",
        tools=[...]
    )
    return {"reviewer_feedback": feedback}
```

#### 自建 Mailbox 实现

```python
import redis
import json
from typing import Dict, Optional
import asyncio

class Mailbox:
    """自建消息系统，支持 Agent 间直接通信"""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url)

    async def send(self, to_agent: str, message: dict):
        """发送消息给指定 Agent"""
        channel = f"mailbox:{to_agent}"
        self.redis.publish(channel, json.dumps(message))

    async def receive(self, agent_id: str, timeout: int = 30) -> Optional[dict]:
        """接收消息（异步等待）"""
        pubsub = self.redis.pubsub()
        pubsub.subscribe(f"mailbox:{agent_id}")
        message = pubsub.get_message(timeout=timeout)
        if message:
            return json.loads(message["data"])
        return None

    async def broadcast(self, message: dict):
        """广播消息给所有 Agent"""
        self.redis.publish("mailbox:broadcast", json.dumps(message))
```

### 4.4 任务执行流程

```
用户请求
    │
    ▼
Leader Agent 接收任务
    │
    ├── 分析任务类型
    │   ├── 并行任务 → 同时分派给多个 Agent
    │   ├── 串行任务 → 按依赖顺序执行
    │   └── 讨论任务 → 开启 Agent 间通信
    │
    ▼
任务写入 PostgreSQL（状态：pending）
    │
    ▼
Agent 执行任务，结果回写 Redis + PostgreSQL
    │
    ├── 失败 → 重试机制（最多 3 次）
    │
    ▼
Leader Agent 汇总结果
    │
    ▼
返回用户，任务归档
```

---

## 五、实施阶段

| 阶段 | 任务 | 产出 | 时间 |
|------|------|------|------|
| **Phase 1** | 用 LangGraph 实现 Leader + 2-3 Agent 原型 | 验证协作流程 | 2 周 |
| **Phase 2** | 加入 Redis Streams 支持异步消息 | 支持重试、持久化 | 2 周 |
| **Phase 3** | 加入 PostgreSQL 审计日志 | 生产级稳定性 | 2 周 |

---

## 六、风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| Claude Agent SDK 不支持 Mailbox | 无法使用原生多 Agent 通信 | 自建消息系统（推荐方案） |
| Agent Teams 实验性功能不稳定 | 生产环境风险 | 等待稳定版发布或使用自研方案 |
| Token 成本较高 | 5 人团队 ≈ 5 倍消耗 | 按需调度，非所有 Agent 全时运行 |
| 上下文不继承 | Agent 协作需要重复传递上下文 | Leader 统一管理上下文，按需分发给 Agent |

---

## 七、结论

1. **Claude Agent SDK 不直接支持 Mailbox**，需要自建消息系统实现多 Agent 通信
2. **推荐采用 Leader 中转 + 自建 Mailbox** 的混合模式，参考 Agent Teams 设计理念
3. **LangGraph + Redis Streams + PostgreSQL** 是成熟的技术组合
4. **分阶段实施**，Phase 1 先验证核心流程，Phase 2/3 逐步完善生产级特性

---

## 八、参考资料

- [Claude Code Agent Teams 官方文档](https://code.claude.com/docs/en/agent-teams)
- [Claude Agent SDK 文档](https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-overview)
- [LangGraph 多 Agent 协作](https://python.langchain.com/docs/concepts/langgraph/)
- [Claude Code 多 Agent 协同机制深度解析](https://www.cnblogs.com/itech/p/19823068)
- [什么是 Claude Managed Agents 企业 IT 团队完整指南](https://segmentfault.com/a/1190000047701368)

---

**下一步：** 确认方案后进入 Phase 1 原型开发
