# 运行中会话 SSE 恢复设计

## 背景

当前会话流式输出由 `POST /api/sessions/{session_id}/chat` 返回 `StreamingResponse`。后端在内存 `queue` 中把 Claude 输出转给当前 HTTP 连接，前端通过 `fetch` 读取 SSE 数据并追加到页面事件列表。

当用户在智能体仍在回复时离开当前会话，前端会中止当前请求，原 SSE 连接随之断开。后端 runner 仍可能继续等待 Claude 输出，但当前实现没有可查询的运行中状态，也没有保存断开后产生的最后一轮消息事件。用户再次进入该会话时，只能加载 Claude 历史，无法可靠恢复正在生成的最后一轮回复。

本设计不恢复旧 SSE 连接，而是在用户重新进入会话时创建新的 SSE 连接，并从服务端保存的最后一轮运行状态继续接收事件。

## 目标

- 用户离开运行中的会话后，再进入该会话时，页面能恢复最后一轮正在生成的消息。
- 不引入 Redis，先通过 `RunStateStore` 抽象使用进程内内存实现。
- 每个会话只记录最后一轮消息事件，避免长期历史堆积导致内存膨胀。
- 保持现有页面状态逻辑：`streaming=true` 时禁用输入、显示停止按钮、自动滚动，流结束后刷新会话列表和工作区。

## 非目标

- 不保证服务进程重启后的运行中流恢复。
- 不支持多后端 worker 之间共享运行中状态。
- 不把完整聊天历史搬到内存 store；历史仍以 Claude session jsonl 作为来源。
- 不改变 Claude SDK 的 session 语义，也不依赖 Claude session 判断当前 HTTP 流能否续接。

## 方案

新增 `RunStateStore`，封装运行中会话最后一轮消息状态。初版实现为进程内内存，后续可替换为 Redis 实现。

### 数据模型

每个 `session_id` 最多保存一条 `RunState`：

```python
class RunEvent(TypedDict):
    seq: int
    event: dict

class RunState(TypedDict):
    session_id: str
    run_id: str
    status: Literal["running", "completed", "failed", "interrupted"]
    events: list[RunEvent]
    next_seq: int
    started_at: str
    updated_at: str
    error_message: str | None
```

设计约束：

- 新一轮 `chat` 开始时覆盖同一 `session_id` 的旧 `RunState`。
- 每个事件分配递增 `seq`，用于恢复连接时避免重复追加。
- 只保存最后一轮事件，不保存更早轮次。
- 可设置最大事件数或最大字符数保护；超限时标记错误事件并结束该轮恢复能力。

### 后端流式发送

`stream_session_chat` 开始时：

1. 创建 `run_id`。
2. 调用 `RunStateStore.start(session_id, run_id)` 覆盖旧状态。
3. 将用户消息 `{type: "user_text", text: prompt}` 写入 store。
4. 前端当前请求已经本地追加用户消息，因此当前 SSE 不需要再次发送这条 `user_text`，避免重复显示。

Claude 事件到达时：

1. 先写入 `RunStateStore.append_event(...)`，得到对应 `seq`。
2. 再推送给当前 SSE 客户端。
3. 如果客户端断开，runner 仍继续消费 Claude 输出并写入 store。

运行结束时：

- 成功：标记 `completed`。
- 用户停止：标记 `interrupted`。
- 异常：写入 `{type: "error", message: safe_message}` 并标记 `failed`。
- 继续执行现有 usage 统计、会话标题更新和 workspace 刷新相关收尾逻辑。

### 恢复接口

新增两个接口：

```http
GET /api/sessions/{session_id}/running
```

返回当前会话最后一轮状态：

```json
{
  "running": true,
  "run_id": "uuid",
  "status": "running",
  "events": [
    { "seq": 1, "event": { "type": "user_text", "text": "..." } },
    { "seq": 2, "event": { "type": "assistant_text", "text": "..." } }
  ],
  "latest_seq": 2
}
```

如果没有未结束运行，返回：

```json
{
  "running": false,
  "status": "completed",
  "events": [],
  "latest_seq": 0
}
```

```http
GET /api/sessions/{session_id}/running/stream?after_seq=2
```

当最后一轮仍在 `running` 状态时，建立新的 SSE 连接：

- 先补发 `seq > after_seq` 的已缓存事件。
- 再等待后续新事件。
- 运行结束后发送结束事件并关闭连接。

如果最后一轮已经结束，接口补发剩余事件后关闭连接。

### 前端恢复流程

选择会话时保持现有历史加载流程，并在历史加载后增加运行中检查：

1. 调用 `api.sessionMessages(id)` 加载 Claude 历史。
2. 调用 `api.sessionRunning(id)`。
3. 如果 `running=false`，保持当前行为。
4. 如果 `running=true`：
   - 将 `events` 中缓存的最后一轮事件追加到页面事件列表。
   - 设置 `streaming=true`。
   - 记录 `latest_seq`。
   - 调用 `streamRunningSession(id, latest_seq)` 创建新的 SSE。
5. 恢复 SSE 回调继续沿用当前“如果用户已切换会话则丢弃事件”的保护逻辑。
6. 恢复流结束后执行现有结束流程：`setStreaming(false)`、刷新会话列表、刷新 workspace。

为了避免重复显示：

- 当前发起新消息的 `sendMessage` 仍由前端立即追加用户消息。
- 恢复场景下，前端没有本地追加过最后一轮用户消息，因此从 `RunStateStore` 返回的 `user_text` 需要追加。
- `seq` 只用于后续恢复 SSE 去重，页面事件模型仍沿用现有 `ChatEvent[]` 和 `foldEvents`。

### 停止逻辑

现有 `/api/sessions/{session_id}/stop` 继续通过 `_active_stops` 设置 stop event。恢复出来的新 SSE 只负责监听最后一轮输出，不创建新的 Claude runner。

如果恢复页面点击停止：

1. 调用现有 stop 接口。
2. abort 当前恢复 SSE 请求。
3. 后端 runner 收到 stop event 后中断 Claude，并将 `RunState` 标记为 `interrupted`。

### 内存控制

进程内 store 使用以下策略控制内存：

- 每个 `session_id` 只保存最后一轮 `RunState`。
- 新一轮开始覆盖旧状态。
- 可配置 `MAX_EVENTS_PER_RUN` 和 `MAX_TEXT_CHARS_PER_RUN`。
- 事件追加超过限制时，写入一个错误事件提示“运行中消息缓存超过限制，请等待本轮完成后重新打开会话”，并停止继续缓存恢复事件。

## 错误处理

- `running` 查询失败：前端只展示历史消息，不进入恢复状态。
- 恢复 SSE 断开：前端可以重新调用 `running` 获取最新 `latest_seq` 后再次连接。
- 后端进程重启：store 为空，前端展示 Claude 历史；若 Claude runner 也已不存在，则本轮无法恢复。
- 会话不存在或不属于当前用户：沿用现有 404 权限逻辑。

## 测试计划

后端测试：

- `RunStateStore` 新一轮覆盖旧状态。
- `append_event` 分配递增 `seq`。
- `snapshot` 只返回最后一轮事件。
- running 查询正确区分 `running` 和非运行状态。
- 恢复 stream 能补发 `after_seq` 之后的事件。

前端测试：

- 选择会话时先加载历史，再追加运行中最后一轮事件。
- 恢复运行中会话后 `streaming=true`，输入区禁用。
- 切换会话时 abort 恢复流，不把旧会话事件追加到新会话。
- 恢复流结束后刷新会话列表和 workspace，并恢复 `streaming=false`。

手动验证：

1. 发起一条耗时较长的智能体消息。
2. 在输出过程中切到其他会话或刷新页面。
3. 重新进入原会话，确认最后一轮用户消息和已生成回复可见。
4. 确认继续生成的内容追加在同一轮 assistant 消息中。
5. 点击停止，确认按钮状态和后端中断行为正常。
