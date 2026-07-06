# Team Orchestrator File Protocol Design

## 背景

当前平台已有基于 Claude Agent SDK 的单智能体运行能力，并已有一版“团队管理”设计，重点是让团队对用户表现为一个黑盒智能体。本文设计的是下一阶段团队运行时规范：由平台后端 `Team Orchestrator` 调度 Leader 和成员 Agent，使用 `plan.yaml` 作为权威状态源，通过标准化 `input.md` / `output.md` 文件完成多智能体串行协作、审核、返工和恢复。

第一版目标是技术规范优先，先定义文件协议、状态机和调度协议，后续再进入具体实现。

## 设计原则

- 团队会话由平台后端内置 Orchestrator 调度。
- `plan.yaml` 是唯一权威计划状态源，由 Leader 动态维护完整 YAML 计划。
- Leader 具备 plan with file 技能，负责规划和流程判断，不做业务产物深度 review。
- 团队成员由用户事先确定。
- 在pwf技能里，由pwf技能确定执行的步骤以及何时调用什么agent。
- 同一个团队会话内持久化 Leader 和每个成员的 Claude `session_id`，成员跨 task 复用同一 session。
- 第一版只支持串行任务，任意时刻最多一个 `current_task`。
- 成员之间不直接通信，所有协作通过 Orchestrator控制和文件协议中转。
- 成员允许直接读写用户 workspace，但必须在任务输入中约束范围，并在 `output.md` 中索引产物。

## 非目标

- 不支持并行 task。
- 不设计成员间 mailbox 或点对点通信。
- 不让数据库任务表成为权威状态源。
- 不让 Leader 深度审核业务产物。
- 不做复杂流程图可视化。
- 不复用跨团队会话的成员上下文。
- 不自动解决多人同时修改同一业务文件的冲突。第一版通过串行调度和任务边界降低冲突风险。

## 总体架构

`Team Orchestrator` 是确定性的后端调度器，不是智能体。它负责创建团队运行目录、读取和校验 `plan.yaml`、启动或恢复 Leader/成员 Claude session、派发当前 task、收集成员输出、调用 Leader 维护计划，并处理停止、异常恢复和用户中途指令。

`Leader Agent` 是团队编排者。它理解用户目标、制定计划、选择成员、创建 produce / review / rework / final 等任务，并根据成员 `output.md` 判断流程是否推进。Leader 直接维护完整 `plan.yaml`，但 Orchestrator 会在每次调度前后解析和校验该文件，只从其中提取 `current_task` 和任务状态作为调度依据。

`Member Agent` 是长期会话执行者。每个成员在同一团队会话内持久化自己的 Claude `session_id`，后续任务都 resume 同一 session。成员接受 Orchestrator 生成的 `input.md`，执行任务，写入标准 `output.md`，并在用户 workspace 或任务 `artifacts/` 中产生产物。

整体循环：

```text
用户请求
  -> Orchestrator 创建 team run 目录
  -> 调用 Leader 生成初始 plan.yaml
  -> 读取 current_task
  -> 调用目标 Member 执行 task
  -> Member 写 output.md / artifacts
  -> Orchestrator 调用 Leader 判断流程推进并更新 plan.yaml
  -> Orchestrator 校验 plan.yaml 并提取下一个 current_task
  -> 重复直到 plan_status = completed / waiting_user_input / failed
```

## 运行目录

建议每个团队会话创建独立运行目录：

```text
.team-runs/{team_session_id}/
  plan.yaml
  inbox/
    user-instructions.md
  leader/
    session.json
    notes.md
  members/
    {member_code}/
      session.json
      memory.md
      tasks/
        T-001/
          input.md
          output.md
          run.json
          artifacts/
  events/
    000001.yaml
```

关键约束：

- `plan.yaml` 是权威计划文件。
- `leader/session.json` 保存 Leader 的 Claude `session_id` 和恢复元数据。
- `members/{member_code}/session.json` 保存成员 Claude `session_id` 和恢复元数据。
- `members/{member_code}/memory.md` 可保存成员在本团队会话内的连续工作笔记，但不能作为 Orchestrator 调度依据。
- 每个 task 必须有独立目录，正式任务交接以 `output.md` 为准。
- `events/` 由 Orchestrator 追加事件，用于审计和恢复辅助。

## `plan.yaml` 协议

`plan.yaml` 是纯 YAML 文件，不再拆分 `plan_update` 和 Markdown 计划正文。Leader 每次规划、推进、返工或响应用户中途指令时，都直接维护完整 `plan.yaml`。Orchestrator 每轮读取该文件，校验 schema、状态、依赖和返工次数，然后只提取 `current_task` 执行调度。运行中的临时状态写入 `run.json` 和 `events/`，不由 Orchestrator 回写到计划文件。

示例：

```yaml
schema_version: 1
team_session_id: "team-run-20260521-001"
plan_status: running
current_task: T-001
revision: 1
rework_policy:
  default_max_rework: 2
format_retry_limit: 2
leader_decision_retry_limit: 2
tasks:
  - id: T-001
    title: "编写团队运行时技术方案初稿"
    assignee: writer
    status: ready
    kind: produce
    depends_on: []
    output_path: "members/writer/tasks/T-001/output.md"
    rework_of:
    rework_count: 0
    max_rework: 2
  - id: T-002
    title: "审核团队运行时技术方案初稿"
    assignee: reviewer
    status: blocked
    kind: review
    depends_on: ["T-001"]
    review_target: "members/writer/tasks/T-001/output.md"
    output_path: "members/reviewer/tasks/T-002/output.md"
    rework_count: 0
    max_rework: 2
notes:
  objective: "为用户产出一份团队运行时技术方案，并经过成员审核。"
  changelog:
    - revision: 1
      summary: "初始化计划，创建编写和审核任务。"
```

任务状态：

- `pending`：已创建，依赖未满足。
- `ready`：可执行。
- `running`：Orchestrator 已派发。
- `completed`：任务输出规范且流程上已完成。
- `blocked`：等待外部输入或前置问题。
- `failed`：执行失败且无法自动恢复。
- `skipped`：Leader 决定不再执行。

计划状态：

- `planning`：Leader 正在生成初始计划。
- `running`：正常执行中。
- `waiting_user_input`：等待用户决策。
- `completed`：团队任务完成。
- `failed`：无法继续。

## Leader 维护计划规则

Leader 直接维护 `plan.yaml`，不再输出独立 `plan_update`。Orchestrator 对 Leader 写入后的完整 YAML 做校验，校验通过后进入下一轮调度。

任务完成后的计划片段示例：

```yaml
plan_status: running
current_task: T-002
revision: 2
last_decision:
  id: D-002
  type: complete_task
  reason: "T-001 已提交规范 output.md，必需区块齐全。深度质量审核由 T-002 执行。"
  observed_task: T-001
tasks:
  - id: T-001
    status: completed
  - id: T-002
    status: ready
```

返工示例：

```yaml
plan_status: running
current_task: T-003
revision: 3
last_decision:
  id: D-003
  type: request_rework
  reason: "Reviewer 对 T-001 的产物提出 changes_requested，且 T-001 返工次数 0 < 2。"
  observed_task: T-002
tasks:
  - id: T-001
    status: completed
  - id: T-002
    status: completed
  - id: T-003
    title: "根据审核意见修订技术方案"
    assignee: writer
    status: ready
    kind: rework
    depends_on: ["T-002"]
    rework_of: T-001
    rework_count: 1
    max_rework: 2
    input_refs:
      - "members/writer/tasks/T-001/output.md"
      - "members/reviewer/tasks/T-002/output.md"
    output_path: "members/writer/tasks/T-003/output.md"
  - id: T-004
    title: "复审修订后的技术方案"
    assignee: reviewer
    status: blocked
    kind: review
    depends_on: ["T-003"]
    review_target: "members/writer/tasks/T-003/output.md"
    output_path: "members/reviewer/tasks/T-004/output.md"
```

超过返工次数后，Leader 只能升级给用户：

```yaml
plan_status: waiting_user_input
current_task: null
revision: 9
last_decision:
  id: D-009
  type: escalate_to_user
  reason: "T-001 的返工次数已达到 2，继续返工可能无限循环。"
user_question:
  summary: "Reviewer 仍不通过方案，是否接受当前风险、调整要求，或更换执行策略？"
```

Orchestrator 校验规则：

- `current_task` 必须存在，或在终止/等待用户状态下为空。
- 不能跳过未完成依赖。
- 不能超过 `max_rework`。
- review task 必须有 `review_target`。
- rework task 必须有 `rework_of` 和上游输入引用。
- Leader 写入的任务和计划状态必须属于协议允许值。
- Leader 更新计划时必须递增 `revision`。

## `output.md` 协议

`output.md` 是成员交给 Leader 的任务交接单，不是完整产物本身。它记录任务结果概要、产物索引、下游输入摘要和问题。Leader 根据它判断计划是否推进；下一个节点的 `input.md` 也主要由它转换得到。

标准格式：

```markdown
---
schema_version: 1
task_id: T-001
assignee: writer
status: completed
result: success
created_at: "2026-05-21T10:30:00+08:00"
---

# Task Output

## Summary

已完成多智能体协作框架技术方案初稿，覆盖目标范围、总体架构、运行目录、plan.yaml 协议、调度循环和异常恢复。

## Deliverables

| 类型 | 路径 | 说明 |
| --- | --- | --- |
| design_doc | artifacts/team-runtime-design-draft.md | 技术方案初稿 |
| workspace_file | docs/team-runtime-design.md | 已写入用户工作空间的方案文档 |

## Downstream Input

给下一个节点使用的摘要：

- 本任务产物主文件：`artifacts/team-runtime-design-draft.md`
- 需要重点审核：架构边界、plan.yaml 作为权威状态源、sessionId 持久化恢复、返工控制
- 已知限制：第一版只支持串行任务，不支持成员间直接通信

## Issues

无。

## Suggested Next Step

建议由 reviewer 审核 `artifacts/team-runtime-design-draft.md`，判断是否需要返工。
```

字段约束：

- `status` 只允许 `completed | failed | partial`。
- `result` 只允许 `success | changes_requested | blocked | error`。
- `Summary` 应简洁说明任务结果。
- `Deliverables` 必须列出所有正式产物路径。
- `Downstream Input` 是下游 `input.md` 的主要内容来源。
- `Issues` 记录执行中的阻塞、缺口和风险。
- `Suggested Next Step` 只是建议，不能直接决定计划。

如果 `output.md` 缺少 front matter、必需区块或产物路径不存在，这属于格式补交，不计入业务返工次数。Orchestrator 可要求原成员补交规范输出，超过 `format_retry_limit` 后任务失败。

## `input.md` 生成规则

Orchestrator 创建下一个 task 的 `input.md` 时，不内联大型产物，而是组合 plan 上下文、上游 `output.md` 摘要和产物路径。

示例：

```markdown
# Task T-003

## Task

根据 reviewer 的审核意见修订技术方案。

## Context From Plan

- 当前任务：T-003
- 任务类型：rework
- 返工来源：T-001
- 上游审核任务：T-002

## Upstream Outputs

### T-001 writer output

Summary:
已完成多智能体协作框架技术方案初稿，覆盖目标范围、总体架构、运行目录、状态协议和异常恢复。

Deliverables:
- `artifacts/team-runtime-design-draft.md`
- `docs/team-runtime-design.md`

### T-002 reviewer output

Summary:
方案方向正确，但缺少 output.md 格式、下游 input.md 转换规则和 Leader 职责边界。

Required Changes:
- 明确 `output.md` 只记录结果概要和产物索引
- 增加 `output.md -> input.md` 转换规则
- 明确 Leader 只做格式和流程判断

## Required Output

请将本任务结果概要写入：

`members/writer/tasks/T-003/output.md`

正式修订产物请写入 `artifacts/`，并在 `Deliverables` 表格中索引。
```

转换原则：

- 默认引用上游 `output.md` 的 `Summary`、`Deliverables`、`Downstream Input`、`Issues`。
- 大产物只引用路径，不内联。
- review / rework task 必须带上目标产物索引。
- Leader 判断计划推进时只读 `output.md`，不扫描完整 artifacts。
- 深度判断由 review task 完成。

## 调度循环

```text
1. Orchestrator 获取 team_run 文件锁。
2. 读取并解析 plan.yaml。
3. 校验 schema_version、revision、current_task、任务状态合法性。
4. 若 inbox/user-instructions.md 有未处理用户指令：
   - 若当前没有 running task，先调用 Leader 处理用户指令。
   - 若已有 running task，不打断，等 task 完成后处理。
5. 找到 current_task。
6. 在该 task 的 run.json 和 events/ 中记录 running，不改写 plan.yaml。
7. 生成成员 task input.md。
8. resume 对应成员 claude_session_id，执行任务。
9. 成员结束后校验 output.md。
10. 调用 Leader，输入 plan.yaml、当前 task output.md、必要上游 output.md。
11. Leader 直接更新完整 plan.yaml，包括任务状态、current_task、revision 和 last_decision。
12. Orchestrator 校验更新后的 plan.yaml。
13. Orchestrator 从 plan.yaml 提取下一个 current_task。
14. 如果 plan_status 未终止，进入下一轮。
```

## 异常恢复

后端重启后，数据库只用于找到 `team_session_id`、运行目录、Leader sessionId、成员 sessionId 和最后错误摘要。恢复后必须以 `plan.yaml` 为准继续调度。

成员 Agent 异常终止时，Orchestrator 不立刻判失败。它使用成员持久化 `session_id` resume，同一个 task 再发恢复提示，要求成员读取 `input.md`、检查已有产物，并补齐 `output.md`。

Leader 写入非法 `plan.yaml` 时，Orchestrator 拒绝进入下一轮调度，并提示 Leader 按 schema 修正。超过 `leader_decision_retry_limit` 后，Orchestrator 停止自动调度，并将错误写入 `events/` 和数据库最后错误摘要，等待用户或管理员处理。

`plan.yaml` 写入应采用临时文件 + rename，并在写入前保存 `plan.yaml.bak`。如果解析失败，优先从备份或最近事件快照恢复。

用户中途指令写入 `inbox/user-instructions.md`。当前 task 不打断；任务完成后 Orchestrator 优先调用 Leader 处理该指令，Leader 可追加、跳过、调整后续任务，但必须维护合法 `plan.yaml`。

## 权限边界

- Leader 可读写 `plan.yaml`，可读所有成员 `output.md` 和必要 artifacts，可写 `leader/`。
- Member 可读自己的 `input.md`、必要上游 output/artifacts、用户 workspace；可写自己的 task 目录和用户 workspace；不能写其他成员目录和 `plan.yaml`。
- Orchestrator 可写 `session.json`、`run.json`、`events/`，负责读取、校验 `plan.yaml` 并提取 `current_task`；计划结构、任务状态、任务拆解和下一步任务选择由 Leader 维护。
- 用户中途指令只能进入 inbox，不能直接改 plan。

## Leader Skill 规范

`team worker` skill 应安装给 Leader，指导 Leader 遵守以下规则：

- 根据用户目标生成或更新完整 `plan.yaml`。
- 显式创建 produce / review / rework / final 等 task。
- 对成员 `output.md` 只做格式、完整性和流程判断。
- 当需要深度质量判断时，创建 review task 指派给合适成员。
- 根据 review `output.md` 决定是否创建 rework task。
- 遵守 `max_rework`，超过后进入 `waiting_user_input`。
- 直接维护结构化 `plan.yaml`，不输出自由格式状态变更。
- 每次计划变化都要更新 `revision` 和 `last_decision`，便于 Orchestrator 校验和审计。

## 成员任务提示词规范

Orchestrator 生成成员任务提示词时，必须包含：

- 当前 `task_id`、`title`、`kind`、`assignee`。
- 用户原始目标摘要。
- plan 中与当前 task 有关的上下文。
- 上游 `output.md` 摘要和产物索引。
- 允许读写的 workspace 范围。
- 必须写入的 `output.md` 路径。
- `output.md` schema 和必需区块。
- 产物写入位置和索引要求。

成员长期 session 复用时，每个 task 开头都要强调任务边界：

```text
这是同一团队会话中的新任务。你可以利用之前上下文，但本次只能以当前 input.md、plan 摘要和显式引用的上游产物为准。不要把未引用的历史假设当作事实。
```

## 测试重点

- `plan.yaml` 解析、schema 校验、revision 增长、备份恢复。
- `plan.yaml` 合法性校验：非法状态跳转、超返工次数、current_task 不存在、依赖未完成。
- `output.md` 校验：缺 front matter、缺区块、Deliverables 路径不存在、result/status 非法。
- 调度循环：初始化计划、执行 task、生成 input.md、成员完成、Leader 推进、最终 completed。
- 异常恢复：running task 后端重启、成员异常终止后 resume、Leader 写入非法计划后重试。
- 用户中途指令：当前 task 不打断，完成后优先处理 inbox。
- 权限边界：成员不能修改 `plan.yaml`，Leader 维护计划但 Orchestrator 必须校验后才调度。

## 分阶段落地

1. 先实现协议解析器和本地文件状态机，不接真实 Claude，用 fake Leader/Member 跑通完整流程。
2. 接入 Claude Agent SDK session 持久化，跑通 Leader 和单个成员的真实串行任务。
3. 增加多成员、review/rework 链路、异常恢复和用户中途指令。
