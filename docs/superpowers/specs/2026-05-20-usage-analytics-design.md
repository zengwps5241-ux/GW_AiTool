# 用户使用情况统计设计

## 概述

为平台增加使用情况采集与管理员统计面板。每次用户发送消息触发的一轮对话作为一条主统计事件，记录用户、会话、智能体、状态、耗时和 token 消耗；实际触发的 skill/plugin 作为资源使用明细单独记录。管理员可以按今天、最近 7 天、最近 30 天或自定义日期查看全平台汇总趋势、智能体排行、skill 排行、plugin 排行和 token 消耗情况。

本设计不展示单轮调用明细，不存储 prompt、assistant 回复、tool result 内容或文件内容。

## 目标

- 采集每轮对话的用户、会话、智能体、状态、耗时、token 和 SDK usage 原始数据。
- 采集每轮对话中实际触发的多个 skill 和多个 plugin。
- 管理员每天能查看平台整体使用情况。
- 支持按时间范围分析调用次数、活跃用户、智能体使用、skill 使用、plugin 使用和 token 消耗。
- 失败和中断的对话也纳入统计，并带状态维度。

## 非目标

- 不提供单轮调用明细表页面。
- 不展示或保存用户 prompt、模型回答正文、tool result 内容。
- 不为普通用户提供个人使用统计。
- 不引入后台 ETL 或预聚合任务；MVP 使用明细表实时聚合。
- 不把智能体已配置的 skills/plugins 计为实际使用，只统计真实触发。

## 数据模型

新增 `usage_events` 表，作为主事实表。每次 `POST /api/sessions/{session_id}/chat` 对应一条记录。

主要字段：

- `id`: 自增主键。
- `user_id`: 当前用户 ID。
- `username`: 用户名快照。
- `session_id`: 平台内部会话 ID。
- `agent_id`: 智能体 ID，可为空。
- `agent_name`: 智能体名称快照。
- `agent_code`: 智能体 code 快照。
- `started_at`: 本轮开始时间。
- `ended_at`: 本轮结束时间。
- `status`: `success`、`error` 或 `interrupted`。
- `stop_reason`: SDK 返回的停止原因。
- `input_tokens`: 输入 token。
- `output_tokens`: 输出 token。
- `total_tokens`: 输入 + 输出 token。
- `duration_ms`: SDK 总耗时。
- `duration_api_ms`: SDK API 耗时。
- `total_cost_usd`: SDK 返回的费用，允许为空。
- `sdk_usage_json`: SDK `ResultMessage.usage` 原始 JSON。
- `sdk_model_usage_json`: SDK `ResultMessage.model_usage` 原始 JSON。
- `error_message`: 错误摘要，允许为空。

索引：

- `idx_usage_events_started_at`：按时间范围聚合。
- `idx_usage_events_user_started`：按用户和时间统计活跃用户。
- `idx_usage_events_agent_started`：按智能体排行。
- `idx_usage_events_status_started`：按状态统计错误和中断。

新增 `usage_resource_events` 表，记录本轮实际触发的 skill/plugin。它与 `usage_events` 是 1:N 关系。

主要字段：

- `id`: 自增主键。
- `usage_event_id`: 外键，关联 `usage_events.id`，级联删除。
- `resource_type`: `skill` 或 `plugin`。
- `resource_name`: 资源名称，例如 `brainstorming` 或 `superpowers:brainstorming`。
- `plugin_name`: 插件资源时填写插件名，例如 `superpowers`。
- `source`: `tool_use` 或 `slash_command`。
- `tool_use_id`: SDK tool_use id，slash command 可为空。
- `is_error`: 对应工具结果是否失败。
- `created_at`: 记录创建时间。

索引：

- `idx_usage_resource_event`：`usage_event_id`。
- `idx_usage_resource_type_name`：资源类型和名称排行。
- `idx_usage_resource_plugin`：插件排行。

## 采集流程

采集位于 `stream_session_chat` 和 `stream_chat` 的协作边界。流式执行期间收集以下信息：

- 开始时间、结束时间和当前用户/会话/智能体快照。
- `tool_use` 事件，用于识别 skill/plugin。
- `tool_result` 事件，用于标记对应资源调用是否错误。
- `ResultMessage`，用于读取 `session_id`、`stop_reason`、`usage`、`model_usage`、`duration_ms`、`duration_api_ms`、`total_cost_usd` 和错误状态。

SDK 正常完成时写 `status=success`。SDK 抛异常时写 `status=error`，同时保留现有 SSE 错误事件行为。用户点击停止后，`stop_event` 触发并写 `status=interrupted`。如果没有收到 `ResultMessage`，仍写主事件，token 填 0，结束时间用捕获到的结束时刻。

统计落库失败不能影响聊天主链路。失败只记录服务端日志，不中断 SSE。

## Skill 和 Plugin 识别规则

skill 使用优先从实际 `tool_use` 识别。当流式事件出现 `tool_use.name == "Skill"` 时，读取 `input` 中的技能标识字段。实现时兼容 `skill`、`name`、`command` 等常见键。无法识别时跳过该资源，不影响主事件落库。

如果技能标识是 `superpowers:brainstorming` 这种带冒号格式，记录为插件资源：

- `resource_type=plugin`
- `plugin_name=superpowers`
- `resource_name=superpowers:brainstorming`

如果技能标识没有插件前缀，记录为普通 skill：

- `resource_type=skill`
- `resource_name=<skill>`

plugin 使用还需要识别 slash command。后端从本轮用户 prompt 中解析 `/xxx` 或 `/plugin:command` 形式的命令片段，并用现有 `scan_agent_commands(workdir)` 命令清单校验归属：

- 命中 `source=plugin` 时写 plugin 资源使用。
- 命中 `source=skill` 时写 skill 资源使用。
- 未命中清单时不记录，避免把普通文本误判为资源使用。

普通工具调用如 `Read`、`Write`、`Bash`、`Grep` 不计入 plugin 使用。启用某个插件不等于实际使用某个插件。

同一轮内相同 `resource_type + resource_name + source + tool_use_id` 不重复写。相同 skill/plugin 在同一轮内多次真实触发且 `tool_use_id` 不同，可以保留多条，用于触发次数统计。

## 管理员统计 API

新增管理员接口：

```text
GET /api/admin/usage/summary?range=today|7d|30d|custom&start=YYYY-MM-DD&end=YYYY-MM-DD
```

权限：`require_admin`。

默认 `range=today`。时间以数据库 UTC 存储，查询边界按 `Asia/Shanghai` 自然日换算。今天按小时返回时间序列，跨天按天返回时间序列。

响应结构：

- `overview`
  - 调用次数：每次发送消息为一次。
  - 活跃用户数。
  - 使用过的智能体数。
  - skill 触发次数。
  - plugin 触发次数。
  - 输入 token、输出 token、总 token。
  - 错误次数、中断次数。
  - 平均耗时。
- `timeseries`
  - 每小时或每天的调用次数、活跃用户数、总 token、错误数。
- `agents`
  - 智能体排行，含调用次数、活跃用户数、token、错误数。
- `skills`
  - skill 排行，只含触发次数。
- `plugins`
  - plugin 排行，只含触发次数。
- `tokens`
  - 输入/输出 token 的总量与时间序列。
- `status_breakdown`
  - `success`、`error`、`interrupted` 分布。

接口不返回单轮调用明细，不返回 prompt 或回答内容。

## 前端统计面板

新增管理员菜单项“使用统计”，仅 `user.role === "admin"` 可见。页面挂在主应用现有管理区域，与“技能管理”“反馈管理”保持同一套视觉风格。

页面结构：

- 顶部标题与时间范围切换：今天、7 天、30 天、自定义日期。
- KPI 区域：调用次数、活跃用户、总 token、错误/中断。
- 趋势区：调用次数、活跃用户、token 和错误趋势。
- 状态分布：成功、错误、中断占比。
- 排行区：
  - 智能体排行：调用次数、活跃用户数、token、错误数。
  - Skill 排行：触发次数。
  - Plugin 排行：触发次数。

MVP 不引入图表库，使用轻量 CSS/SVG 组件实现折线、柱状、状态分布和排行榜。后续如果需要复杂交互，再引入图表库。

页面需要处理加载中、空数据、接口失败和窄屏布局。空数据时展示“当前时间范围暂无使用数据”，不显示错误样式。

## 隐私与安全

- 统计表不存 prompt、assistant 回复、tool result 内容或文件内容。
- 管理员面板只展示汇总数据，不提供单轮明细。
- 活跃用户只展示去重计数，不列出用户排行。
- 资源识别只记录资源名称、类型、插件名和触发次数。
- 管理员 API 使用 `require_admin` 保护，普通用户访问返回 403，未登录返回 401。

## 错误处理

- SDK 错误：保留现有 SSE 错误响应，同时写 `status=error`。
- 用户停止：写 `status=interrupted`。
- 缺少 `ResultMessage`：仍写主事件，token 填 0。
- usage 字段解析失败：输入/输出 token 填 0，保留原始 JSON。
- 资源识别失败：跳过该资源，不影响主事件。
- 统计落库失败：记录服务端日志，不影响聊天响应。
- 统计 API 参数非法：返回 422。

## 测试计划

后端测试：

- 模型注册测试：`usage_events`、`usage_resource_events` 和索引存在。
- 迁移测试：已有数据库启动时能创建新表。
- 采集测试：成功对话写入主事件、token、耗时和智能体快照。
- 采集测试：一轮对话可写入多个 skill 和多个 plugin。
- 采集测试：SDK 异常写 `status=error`，且不泄露 prompt。
- 采集测试：用户停止写 `status=interrupted`。
- 资源识别测试：`Skill` 工具调用、插件前缀命令、slash command 都能正确归因。
- API 权限测试：未登录 401、普通用户 403、管理员 200。
- API 聚合测试：today、7d、30d、自定义日期的 overview、timeseries、agents、skills、plugins 和 token 汇总正确。

前端测试：

- API 类型与 client 方法。
- 管理员菜单显示“使用统计”，普通用户不显示。
- 时间范围切换触发重新请求。
- KPI、趋势、状态分布和三类排行渲染正确。
- 空数据和接口失败状态可读。
- 窄屏下图表和文字不重叠。

手工验证：

- 管理员进入使用统计页，默认展示今天数据。
- 切换 7 天、30 天、自定义日期正常。
- 发送一轮带 skill/plugin 的对话后，刷新面板能看到调用、token 和资源触发次数变化。

## 实施顺序

1. 增加 ORM 模型、模型导出和兼容迁移。
2. 增加 usage 采集服务和资源识别工具函数。
3. 在流式会话编排中接入采集，保证采集失败不影响聊天。
4. 增加管理员统计 schema、service 和 route。
5. 增加后端测试。
6. 增加前端类型、API client、导航项和使用统计页面。
7. 增加前端测试并做手工验证。
