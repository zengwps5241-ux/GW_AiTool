# Team Shared Session Message Author Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist and display the real sender for each user message in team shared sessions.

**Architecture:** Add an application-owned `chat_message_authors` table keyed by `(session_id, message_index)` so sender identity is independent from Claude SDK history. Write sender metadata when a user sends a prompt, enrich history and running-state events with that metadata, then render user turns by comparing `sender_user_id` with the current user.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, startup-compatible DDL in `backend/app/db/migrations.py`, pytest, React, TypeScript, Vite.

---

### Task 1: Backend Sender Metadata Model

**Files:**
- Create: `backend/app/models/chat_message_author.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/db/migrations.py`
- Test: `backend/tests/test_team_sessions_api.py`

- [ ] **Step 1: Add a failing model/migration smoke test**

Add this test to `backend/tests/test_team_sessions_api.py`:

```python
async def test_chat_message_author_table_is_available(db_session):
    from sqlalchemy import text

    result = await db_session.execute(
        text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name='chat_message_authors'")
    )

    assert result.scalar() == 1
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd backend && uv run pytest tests/test_team_sessions_api.py::test_chat_message_author_table_is_available -q
```

Expected: FAIL because `chat_message_authors` does not exist.

- [ ] **Step 3: Create the ORM model**

Create `backend/app/models/chat_message_author.py`:

```python
"""Chat message author ORM model。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatMessageAuthor(Base):
    __tablename__ = "chat_message_authors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    message_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sender_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    sender_name_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    sender_avatar_url_snapshot: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("session_id", "message_index", name="uq_chat_message_author_index"),
        Index("idx_chat_message_authors_session_index", "session_id", "message_index"),
        Index("idx_chat_message_authors_sender_created", "sender_user_id", "created_at"),
    )
```

- [ ] **Step 4: Export the model**

Modify `backend/app/models/__init__.py`:

```python
from app.models.chat_message_author import ChatMessageAuthor
```

Add `"ChatMessageAuthor"` to `__all__`.

- [ ] **Step 5: Add startup-compatible DDL**

Append this block in `backend/app/db/migrations.py` near the other table creation blocks:

```python
        # chat_message_authors 表：记录每条用户消息的真实发送者。
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='chat_message_authors'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE chat_message_authors ("
                "id SERIAL PRIMARY KEY, "
                "session_id VARCHAR NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE, "
                "message_index INTEGER NOT NULL, "
                "sender_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "sender_name_snapshot VARCHAR NOT NULL, "
                "sender_avatar_url_snapshot VARCHAR NULL, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "CONSTRAINT uq_chat_message_author_index UNIQUE (session_id, message_index)"
                ")"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_chat_message_authors_session_index "
                "ON chat_message_authors (session_id, message_index)"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_chat_message_authors_sender_created "
                "ON chat_message_authors (sender_user_id, created_at)"
            ))
```

- [ ] **Step 6: Run the model/migration test**

Run:

```bash
cd backend && uv run pytest tests/test_team_sessions_api.py::test_chat_message_author_table_is_available -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/chat_message_author.py backend/app/models/__init__.py backend/app/db/migrations.py backend/tests/test_team_sessions_api.py
git commit -m "feat:添加聊天消息发送者模型"
```

### Task 2: Backend Write and Enrich Sender Metadata

**Files:**
- Create: `backend/app/modules/sessions/message_authors.py`
- Modify: `backend/app/modules/sessions/streaming.py`
- Modify: `backend/app/api/routes/sessions.py`
- Test: `backend/tests/test_team_sessions_api.py`

- [ ] **Step 1: Add failing tests for author write and history enrichment**

Add tests to `backend/tests/test_team_sessions_api.py`. Reuse the existing team-space/session fixtures in this file; if fixture names differ, adapt only the setup lines and keep the assertions:

```python
async def test_team_shared_session_records_sender_for_user_message(
    logged_in_client,
    db_session,
    test_user,
    team_space_factory,
    monkeypatch,
):
    from app.models import ChatMessageAuthor
    from sqlalchemy import select

    space = await team_space_factory(owner=test_user)
    created = await logged_in_client.post(
        "/api/sessions",
        json={"workspace_kind": "team", "team_space_id": space.id, "is_shared": True},
    )
    session_id = created.json()["id"]

    async def fake_stream_chat(**kwargs):
        from app.integrations.claude.runner import ChatRunSummary

        return ChatRunSummary(
            session_id="claude-1",
            is_error=False,
            stop_reason=None,
            usage=None,
            model_usage=None,
            duration_ms=None,
            duration_api_ms=None,
            total_cost_usd=None,
            interrupted=False,
            error_message=None,
        )

    monkeypatch.setattr("app.modules.sessions.streaming.stream_chat", fake_stream_chat)

    response = await logged_in_client.post(
        f"/api/sessions/{session_id}/chat",
        json={"prompt": "来自所有者的消息"},
    )

    assert response.status_code == 200
    rows = (await db_session.execute(
        select(ChatMessageAuthor).where(ChatMessageAuthor.session_id == session_id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].message_index == 1
    assert rows[0].sender_user_id == test_user.id
    assert rows[0].sender_name_snapshot == (test_user.display_name or test_user.username)
```

```python
async def test_history_messages_are_enriched_with_sender_metadata(
    logged_in_client,
    db_session,
    test_user,
    other_user,
    team_space_factory,
    monkeypatch,
):
    from app.models import ChatMessageAuthor

    space = await team_space_factory(owner=test_user, members=[other_user])
    created = await logged_in_client.post(
        "/api/sessions",
        json={"workspace_kind": "team", "team_space_id": space.id, "is_shared": True},
    )
    session_id = created.json()["id"]
    db_session.add_all([
        ChatMessageAuthor(
            session_id=session_id,
            message_index=1,
            sender_user_id=test_user.id,
            sender_name_snapshot=test_user.display_name or test_user.username,
            sender_avatar_url_snapshot=test_user.avatar_url,
        ),
        ChatMessageAuthor(
            session_id=session_id,
            message_index=2,
            sender_user_id=other_user.id,
            sender_name_snapshot=other_user.display_name or other_user.username,
            sender_avatar_url_snapshot=other_user.avatar_url,
        ),
    ])
    await db_session.commit()

    async def fake_load_history(*args, **kwargs):
        return [
            {"type": "user_text", "text": "A"},
            {"type": "assistant_text", "text": "ok"},
            {"type": "user_text", "text": "B"},
        ]

    monkeypatch.setattr("app.api.routes.sessions.load_history", fake_load_history)

    response = await logged_in_client.get(f"/api/sessions/{session_id}/messages")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["sender_user_id"] == test_user.id
    assert body[0]["sender_name"] == (test_user.display_name or test_user.username)
    assert body[2]["sender_user_id"] == other_user.id
    assert body[2]["sender_name"] == (other_user.display_name or other_user.username)
```

Also add a compatibility test:

```python
async def test_team_history_without_author_does_not_default_to_current_user(
    logged_in_client,
    team_space_factory,
    test_user,
    monkeypatch,
):
    space = await team_space_factory(owner=test_user)
    created = await logged_in_client.post(
        "/api/sessions",
        json={"workspace_kind": "team", "team_space_id": space.id, "is_shared": True},
    )
    session_id = created.json()["id"]

    async def fake_load_history(*args, **kwargs):
        return [{"type": "user_text", "text": "旧消息"}]

    monkeypatch.setattr("app.api.routes.sessions.load_history", fake_load_history)

    response = await logged_in_client.get(f"/api/sessions/{session_id}/messages")

    assert response.status_code == 200
    assert "sender_user_id" not in response.json()[0]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd backend && uv run pytest tests/test_team_sessions_api.py -q
```

Expected: FAIL because sender records and enrichment do not exist.

- [ ] **Step 3: Implement message author helpers**

Create `backend/app/modules/sessions/message_authors.py`:

```python
"""会话用户消息发送者归属。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessageAuthor, ChatSession, User


def sender_snapshot(user: User) -> dict:
    """生成写入事件和数据库的发送者快照。"""
    return {
        "sender_user_id": user.id,
        "sender_name": user.display_name or user.username,
        "sender_avatar_url": user.avatar_url,
    }


async def record_user_message_author(
    db: AsyncSession,
    session_id: str,
    user: User,
) -> dict:
    """记录本会话下一条用户文本消息的发送者，并返回前端事件可用元数据。"""
    max_index = await db.scalar(
        select(func.max(ChatMessageAuthor.message_index)).where(
            ChatMessageAuthor.session_id == session_id
        )
    )
    message_index = int(max_index or 0) + 1
    snapshot = sender_snapshot(user)
    db.add(
        ChatMessageAuthor(
            session_id=session_id,
            message_index=message_index,
            sender_user_id=user.id,
            sender_name_snapshot=snapshot["sender_name"],
            sender_avatar_url_snapshot=snapshot["sender_avatar_url"],
        )
    )
    await db.commit()
    return {**snapshot, "message_index": message_index}


async def enrich_user_text_authors(
    db: AsyncSession,
    user: User,
    session: ChatSession,
    events: list[dict],
) -> list[dict]:
    """为历史 user_text 事件补充发送者，团队旧消息不能默认归属当前用户。"""
    rows = (
        await db.execute(
            select(ChatMessageAuthor).where(ChatMessageAuthor.session_id == session.id)
        )
    ).scalars().all()
    by_index = {row.message_index: row for row in rows}

    current_index = 0
    enriched: list[dict] = []
    for event in events:
        if event.get("type") != "user_text":
            enriched.append(event)
            continue

        current_index += 1
        item = dict(event)
        author = by_index.get(current_index)
        if author is not None:
            item.update(
                {
                    "sender_user_id": author.sender_user_id,
                    "sender_name": author.sender_name_snapshot,
                    "sender_avatar_url": author.sender_avatar_url_snapshot,
                }
            )
        elif getattr(session, "workspace_kind", "personal") != "team":
            item.update(sender_snapshot(user))
        enriched.append(item)
    return enriched
```

- [ ] **Step 4: Record sender in `stream_session_chat()`**

Modify `backend/app/modules/sessions/streaming.py`:

```python
from app.modules.sessions.message_authors import record_user_message_author
```

Inside `stream_session_chat()`, record the sender inside the existing `_session_lock_for(session_id)` block before `run_state_store.append_event(...)`. This keeps `message_index` generation and run-state append serialized per session:

```python
    async with _session_lock_for(session_id):
        async with async_session() as author_db:
            sender_meta = await record_user_message_author(author_db, session_id, user)
        run_state_store.start(session_id, run_id)
        user_event = {"type": "user_text", "text": prompt, **sender_meta}
        run_state_store.append_event(
            session_id,
            RunEvent(type="user_text", payload=user_event),
            run_id=run_id,
        )
```

Replace the old local user event payload:

```python
        run_state_store.append_event(
            session_id,
            RunEvent(type="user_text", payload={"type": "user_text", "text": prompt}),
            run_id=run_id,
        )
```

- [ ] **Step 5: Enrich history response**

Modify `backend/app/api/routes/sessions.py`:

```python
from app.modules.sessions.message_authors import enrich_user_text_authors
```

In `list_messages()`, replace the direct return:

```python
    events = await load_history(
        cs.claude_session_id,
        scope.root,
        agent=agent,
    )
    return await enrich_user_text_authors(db, user, cs, events)
```

- [ ] **Step 6: Run backend tests**

Run:

```bash
cd backend && uv run pytest tests/test_team_sessions_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/sessions/message_authors.py backend/app/modules/sessions/streaming.py backend/app/api/routes/sessions.py backend/tests/test_team_sessions_api.py
git commit -m "feat:记录共享会话消息发送者"
```

### Task 3: Frontend Types and User Turn Rendering

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/ChatWorkspace.tsx`

- [ ] **Step 1: Extend `ChatEvent.user_text`**

Modify `frontend/src/types/index.ts`:

```ts
export type ChatEvent =
  | {
      type: "user_text";
      text: string;
      sender_user_id?: number | null;
      sender_name?: string | null;
      sender_avatar_url?: string | null;
    }
  | { type: "assistant_text"; text: string }
  | { type: "assistant_thinking"; text?: string }
  | {
      type: "tool_use";
      id: string;
      name: string;
      input: unknown;
    }
  | {
      type: "tool_result";
      tool_use_id: string;
      content: unknown;
      is_error?: boolean;
    }
  | { type: "result"; [key: string]: unknown }
  | { type: "error"; message: string };
```

- [ ] **Step 2: Add sender fields to `Turn`**

Modify `frontend/src/pages/ChatWorkspace.tsx`:

```ts
interface Turn {
  kind: "user" | "assistant";
  sender_user_id?: number | null;
  sender_name?: string | null;
  sender_avatar_url?: string | null;
  parts: Part[];
}
```

- [ ] **Step 3: Preserve sender in `foldEvents()`**

Change the `user_text` branch:

```ts
    if (evt.type === "user_text") {
      out.push({
        kind: "user",
        sender_user_id: evt.sender_user_id,
        sender_name: evt.sender_name,
        sender_avatar_url: evt.sender_avatar_url,
        parts: [{ kind: "text", text: normalizeUserText(evt.text) }],
      });
```

- [ ] **Step 4: Include sender in local optimistic message**

In `sendMessage()`, change:

```ts
      setEvents((es) => [...es, { type: "user_text", text: finalPrompt }]);
```

to:

```ts
      setEvents((es) => [
        ...es,
        {
          type: "user_text",
          text: finalPrompt,
          sender_user_id: me.id,
          sender_name: me.display_name ?? me.username,
          sender_avatar_url: me.avatar_url,
        },
      ]);
```

Add `me` to the `sendMessage` dependency list.

- [ ] **Step 5: Render other team members distinctly**

Change `TurnView` props:

```ts
function TurnView({
  turn,
  me,
  isTeamSession,
}: {
  turn: Turn;
  me: UserMe;
  isTeamSession: boolean;
}) {
```

Change the call site:

```tsx
<TurnView
  key={i}
  turn={turn}
  me={me}
  isTeamSession={currentSession?.workspace_kind === "team"}
/>
```

In the `turn.kind === "user"` branch, compute sender state:

```ts
    const isMine = turn.sender_user_id == null ? !isTeamSession : turn.sender_user_id === me.id;
    const displayName = isMine
      ? me.display_name ?? me.username
      : turn.sender_name || "未知成员";
```

For `isMine`, keep the existing right-aligned layout. For `!isMine`, render a left-aligned member message:

```tsx
    if (!isMine) {
      return (
        <div style={{ display: "flex", justifyContent: "flex-start", gap: 12, animation: "fadeUp 240ms" }}>
          <Avatar name={displayName} size={30} />
          <div style={{ maxWidth: "72%", display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
            <div style={{ fontSize: 12, color: "var(--ink-3)", fontWeight: 600 }}>{displayName}</div>
            <div
              style={{
                background: "var(--surface)",
                color: "var(--ink)",
                padding: "10px 14px",
                border: "1px solid var(--line)",
                borderRadius: "14px 14px 14px 4px",
                fontSize: 14,
                lineHeight: 1.55,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {copyText}
            </div>
            <CopyMessageButton copied={copied} onClick={copyMessage} align="start" />
          </div>
        </div>
      );
    }
```

The existing right-aligned block should use `displayName` instead of the old `username` prop.

- [ ] **Step 6: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/pages/ChatWorkspace.tsx
git commit -m "feat:区分共享会话消息发送者"
```

### Task 4: Final Verification

**Files:**
- Verify all changed backend and frontend files.

- [ ] **Step 1: Run backend session tests**

```bash
cd backend && uv run pytest tests/test_team_sessions_api.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Check whitespace**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 4: Manual acceptance check**

Use two users in the same team shared session:

- A sends `A message`.
- B sends `B message`.
- A refreshes the session and sees `A message` as self, `B message` as B.
- B refreshes the session and sees `B message` as self, `A message` as A.
- An old team message without sender metadata is not displayed as the current user.

- [ ] **Step 5: Commit any final fixes**

```bash
git status --short
git add <files changed by verification fixes>
git commit -m "fix:完善共享会话发送者展示"
```

Skip this commit if verification required no changes.
