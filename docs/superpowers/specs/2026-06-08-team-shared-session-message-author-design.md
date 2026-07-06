# 团队共享会话消息发送者设计

## 背景

团队空间共享会话允许多个成员在同一个会话中发送消息。当前前端只根据 `ChatEvent.type === "user_text"` 判断这是一条用户消息，并默认按当前登录用户渲染头像、名称和右侧气泡。因此 A 和 B 在同一个共享会话中各发送一次消息后，A 打开会话会看到两条用户消息都像是自己发送的，B 打开也会看到两条都像是自己发送的。

现有链路中，历史消息由 `/api/sessions/{id}/messages` 调用 `load_history()` 从 Claude SDK 会话 jsonl 读取并序列化；运行中恢复由 `run_state_store` 保存内存事件；`chat_sessions` 表只保存会话元信息，不保存每条消息的发送者身份。

## 目标

- 团队共享会话中，每条用户消息都能显示真实发送成员。
- 当前用户发送的消息继续保持“我”的视觉语义。
- 其他成员发送的消息显示成员名称和头像，不再冒充当前用户。
- 历史消息、刷新后的运行中恢复、SSE 实时消息三条路径使用一致的发送者元数据。
- 不把业务身份元数据写入 Claude SDK 历史文件作为唯一来源。
- 对旧历史消息做兼容，不强制一次性迁移 Claude 历史。

## 非目标

- 不新增完整消息系统，不在本次实现消息撤回、编辑、已读、搜索、引用。
- 不改变 Claude SDK 的原始会话历史格式。
- 不要求旧团队会话中的历史用户消息都能准确补回发送者；没有归属记录的旧消息使用兼容展示。

## 数据模型

新增 `chat_message_authors` 表，保存应用侧对用户消息发送者的事实记录。

字段：

- `id`: 自增主键。
- `session_id`: 关联 `chat_sessions.id`，会话删除时级联删除。
- `message_index`: 同一会话内第几条用户文本消息，从 1 开始递增。
- `sender_user_id`: 关联 `users.id`，发送者真实用户 ID。
- `sender_name_snapshot`: 发送当时展示名快照，优先 `display_name`，否则 `username`。
- `sender_avatar_url_snapshot`: 发送当时头像快照，可为空。
- `created_at`: 记录创建时间。

约束与索引：

- `UNIQUE(session_id, message_index)`，保证一条用户消息只有一个发送者归属。
- `INDEX(session_id, message_index)`，用于历史消息补齐 sender。
- `INDEX(sender_user_id, created_at)`，用于后续审计或统计扩展。

`message_index` 使用“用户文本消息序号”，而不是 Claude 事件全局序号。原因是 Claude 历史序列里包含 assistant、tool_use、tool_result、result 等事件，业务上只需要给 `user_text` 补发送者；按用户文本序号更稳定，也更容易和 `serialize_block(..., streaming=False)` 输出的 `user_text` 对齐。

## ChatEvent 扩展

扩展前端和后端返回的 `user_text` 事件：

```ts
type ChatEvent =
  | {
      type: "user_text";
      text: string;
      sender_user_id?: number | null;
      sender_name?: string | null;
      sender_avatar_url?: string | null;
    }
  | ...;
```

字段使用可选形式，兼容旧消息和旧运行态缓存。后端写新消息时必须填充 sender 字段。

## 后端行为

### 发送消息

`POST /api/sessions/{session_id}/chat` 进入 `stream_session_chat()` 后：

1. 校验当前用户可以访问该会话。
2. 如果是团队会话，仍按现有 `team_workspace_scope()` 校验空间权限。
3. 计算本会话下一条用户文本消息的 `message_index`。
4. 写入 `chat_message_authors`：
   - `session_id = cs.id`
   - `message_index = next_index`
   - `sender_user_id = user.id`
   - `sender_name_snapshot = user.display_name or user.username`
   - `sender_avatar_url_snapshot = user.avatar_url`
5. 写入 `run_state_store` 的本地 `user_text` 事件时带 sender 元数据。
6. 前端本地乐观追加的 `user_text` 也带 sender 元数据；后端 SSE 不需要重复回推用户输入，仍由运行态恢复保证刷新后可见。

`message_index` 的生成和 `run_state_store.append_event()` 必须处在同一个 `_session_lock_for(session_id)` 临界区内，避免两个成员同时发送消息时都读到相同的最大序号。

个人会话也可以写入 `chat_message_authors`，这样实现路径统一；前端个人会话继续按当前用户展示，不增加额外视觉负担。

### 历史消息

`GET /api/sessions/{session_id}/messages`：

1. 继续通过 `load_history()` 读取 Claude 历史并序列化为 `ChatEvent[]`。
2. 查询 `chat_message_authors` 中该会话所有归属记录，按 `message_index` 排序。
3. 遍历历史事件，每遇到一条 `user_text` 就递增用户文本序号。
4. 如果存在对应 `message_index` 的归属记录，则给该 `user_text` 补充 sender 字段。
5. 如果没有归属记录：
   - 个人会话：可以补当前访问用户作为兼容。
   - 团队会话：不补当前访问用户，避免错误归属；前端显示“未知成员”。

### 运行中恢复

`GET /api/sessions/{id}/running` 和 `/running/stream` 使用 `_chat_event_from_run_event()` 返回 `RunEvent.payload`。新写入的 `RunEvent.payload` 已经包含 sender 字段，因此刷新后恢复运行中的用户消息时可以保持发送者身份。

## 前端行为

### 折叠事件

`foldEvents()` 遇到 `user_text` 时，把 sender 信息写入 `Turn`：

```ts
interface Turn {
  kind: "user" | "assistant";
  sender_user_id?: number | null;
  sender_name?: string | null;
  sender_avatar_url?: string | null;
  parts: Part[];
}
```

### 渲染规则

- `turn.kind === "assistant"`：保持现有智能体消息样式。
- `turn.kind === "user"` 且 `turn.sender_user_id === me.id`：保持当前用户消息样式，右侧气泡，头像使用当前用户。
- `turn.kind === "user"` 且 `turn.sender_user_id !== me.id`：显示为团队成员消息，展示 `sender_name` 和头像，避免显示成“我”。
- `sender_user_id` 缺失：
  - 个人会话：按当前用户展示。
  - 团队会话：显示“未知成员”，使用普通成员样式。

视觉上不需要做成强提醒，只要能清楚区分“我”和“其他成员”。建议其他成员用户气泡靠左，名称显示在气泡上方或旁边，与 assistant 气泡保持可区分。

## 兼容性

- 新 `ChatEvent.user_text` 字段是可选字段，旧前端类型可以逐步扩展。
- 旧历史消息没有 `chat_message_authors` 记录时不做错误归属。
- 已经在内存中的旧 `run_state_store` 事件没有 sender 字段时按兼容规则展示。
- 数据库迁移只新增表和索引，不修改现有 `chat_sessions` 字段。

## 验收标准

- A 和 B 都是同一个团队空间成员，且能访问同一个共享会话。
- A 发送一条消息，B 发送一条消息。
- A 打开该共享会话时，A 的消息显示为自己，B 的消息显示为 B。
- B 打开该共享会话时，B 的消息显示为自己，A 的消息显示为 A。
- 刷新页面后，历史消息仍保持正确发送者。
- 正在运行的会话刷新后，通过 running 恢复出来的用户消息仍带正确发送者。
- 旧团队会话中没有发送者归属记录的用户消息，不显示成当前登录用户。

## 测试策略

- 后端新增测试覆盖：
  - 发送团队共享会话消息时写入 `chat_message_authors`。
  - 多成员同一会话发送消息时 `message_index` 递增且发送者不同。
  - 历史消息补齐 sender 字段。
  - 缺少归属记录的团队历史消息不补当前用户。
  - running state 返回的本地 `user_text` 带 sender 字段。
- 前端执行 `npm run build` 验证类型。
- 如后续有前端测试框架，再补 `foldEvents()` 的单元测试；当前仓库没有 `npm test`，本次以类型构建验证为主。
