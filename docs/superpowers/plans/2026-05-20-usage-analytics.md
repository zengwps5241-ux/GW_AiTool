# Usage Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build administrator-only usage analytics that records each chat call, records actually triggered skills/plugins, and displays aggregate platform usage.

**Architecture:** Add normalized usage tables, collect usage at the chat streaming boundary, expose one admin summary API, then add a React admin dashboard. The chat path must keep streaming even if analytics persistence fails.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, PostgreSQL, pytest/pytest-asyncio, React 18, TypeScript, Vite, inline CSS/SVG charts.

---

## File Structure

Backend:

- Create `backend/app/models/usage.py`: ORM models for `UsageEvent` and `UsageResourceEvent`.
- Modify `backend/app/models/__init__.py`: export new models.
- Modify `backend/app/db/__init__.py`: include usage model in test reload shim.
- Modify `backend/tests/conftest.py`: reload usage model, schema, module, and route files added below.
- Modify `backend/app/db/migrations.py`: create compatible tables and indexes on startup.
- Create `backend/app/modules/usage/__init__.py`: package marker.
- Create `backend/app/modules/usage/service.py`: usage extraction, resource recognition, persistence, and aggregation queries.
- Create `backend/app/schemas/usage.py`: response schemas for admin summary API.
- Modify `backend/app/schemas/__init__.py`: export usage schemas.
- Create `backend/app/api/routes/admin_usage.py`: `/api/admin/usage/summary`.
- Modify `backend/app/api/router.py`: register admin usage router.
- Modify `backend/app/integrations/claude/runner.py`: return a run summary object containing SDK result metadata.
- Modify `backend/app/modules/sessions/streaming.py`: capture serialized tool events, call usage persistence in `finally`/completion path.
- Add tests in `backend/tests/test_usage_models.py`, `backend/tests/test_usage_service.py`, `backend/tests/test_usage_api.py`, and extend `backend/tests/test_chat_api.py`.

Frontend:

- Modify `frontend/src/types/index.ts`: add usage analytics response types and `ViewName` value.
- Modify `frontend/src/api/client.ts`: add `api.adminUsageSummary(...)`.
- Modify `frontend/src/icons/index.tsx`: add or reuse `LayoutDashboard` for usage navigation.
- Modify `frontend/src/components/Sidebar.tsx`: add admin-only “使用统计” menu item.
- Modify `frontend/src/App.tsx`: route `view === "usage"` to new page and breadcrumb.
- Create `frontend/src/pages/UsageAnalyticsPage.tsx`: dashboard page, filters, KPI, SVG charts, rankings.

---

### Task 1: Backend Usage Models and Migration

**Files:**
- Create: `backend/app/models/usage.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/db/__init__.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_usage_models.py`

- [ ] **Step 1: Write failing model registration tests**

Create `backend/tests/test_usage_models.py`:

```python
async def test_usage_models_are_registered():
    from app.models import Base

    assert "usage_events" in Base.metadata.tables
    assert "usage_resource_events" in Base.metadata.tables

    usage_table = Base.metadata.tables["usage_events"]
    resource_table = Base.metadata.tables["usage_resource_events"]

    assert usage_table.c.status.nullable is False
    assert usage_table.c.input_tokens.default.arg == 0
    assert usage_table.c.output_tokens.default.arg == 0
    assert usage_table.c.total_tokens.default.arg == 0
    assert resource_table.c.usage_event_id.nullable is False
    assert resource_table.c.resource_type.nullable is False
    assert resource_table.c.resource_name.nullable is False

    usage_indexes = {index.name for index in usage_table.indexes}
    resource_indexes = {index.name for index in resource_table.indexes}

    assert "idx_usage_events_started_at" in usage_indexes
    assert "idx_usage_events_user_started" in usage_indexes
    assert "idx_usage_events_agent_started" in usage_indexes
    assert "idx_usage_events_status_started" in usage_indexes
    assert "idx_usage_resource_event" in resource_indexes
    assert "idx_usage_resource_type_name" in resource_indexes
    assert "idx_usage_resource_plugin" in resource_indexes
```

- [ ] **Step 2: Run the model test and verify it fails**

Run:

```bash
cd backend
uv run pytest tests/test_usage_models.py -v
```

Expected: FAIL because `usage_events` is not registered.

- [ ] **Step 3: Create ORM models**

Create `backend/app/models/usage.py`:

```python
"""Usage analytics ORM models。"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UsageEvent(Base):
    """每次用户发送消息产生的一轮对话统计。"""

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_code: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_api_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    sdk_usage_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sdk_model_usage_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    resources: Mapped[list["UsageResourceEvent"]] = relationship(
        back_populates="usage_event",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_usage_events_started_at", "started_at"),
        Index("idx_usage_events_user_started", "user_id", "started_at"),
        Index("idx_usage_events_agent_started", "agent_id", "started_at"),
        Index("idx_usage_events_status_started", "status", "started_at"),
    )


class UsageResourceEvent(Base):
    """一轮对话中实际触发的 skill/plugin 资源。"""

    __tablename__ = "usage_resource_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usage_event_id: Mapped[int] = mapped_column(
        ForeignKey("usage_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String, nullable=False)
    resource_name: Mapped[str] = mapped_column(String, nullable=False)
    plugin_name: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    tool_use_id: Mapped[str | None] = mapped_column(String, nullable=True)
    is_error: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    usage_event: Mapped[UsageEvent] = relationship(back_populates="resources")

    __table_args__ = (
        Index("idx_usage_resource_event", "usage_event_id"),
        Index("idx_usage_resource_type_name", "resource_type", "resource_name"),
        Index("idx_usage_resource_plugin", "plugin_name"),
    )
```

- [ ] **Step 4: Export and reload the models**

Modify `backend/app/models/__init__.py`:

```python
from app.models.usage import UsageEvent, UsageResourceEvent
```

Add `"UsageEvent"` and `"UsageResourceEvent"` to `__all__`.

Modify `backend/app/db/__init__.py` model reload list:

```python
for _mod_name in [
    "app.models.user",
    "app.models.agent",
    "app.models.session",
    "app.models.category",
    "app.models.conversion_task",
    "app.models.feedback",
    "app.models.usage",
]:
```

Modify `backend/tests/conftest.py` in Layer 2 imports:

```python
from app.models import usage as model_usage
reload(model_usage)
```

- [ ] **Step 5: Add compatible database migration**

Modify `backend/app/db/migrations.py` after feedback table migrations or before the final function exit:

```python
        # usage_events 表
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='usage_events'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE usage_events ("
                "id SERIAL PRIMARY KEY, "
                "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "username VARCHAR NOT NULL, "
                "session_id VARCHAR NOT NULL, "
                "agent_id INTEGER NULL, "
                "agent_name VARCHAR NULL, "
                "agent_code VARCHAR NULL, "
                "started_at TIMESTAMP WITH TIME ZONE NOT NULL, "
                "ended_at TIMESTAMP WITH TIME ZONE NOT NULL, "
                "status VARCHAR NOT NULL, "
                "stop_reason VARCHAR NULL, "
                "input_tokens INTEGER NOT NULL DEFAULT 0, "
                "output_tokens INTEGER NOT NULL DEFAULT 0, "
                "total_tokens INTEGER NOT NULL DEFAULT 0, "
                "duration_ms INTEGER NULL, "
                "duration_api_ms INTEGER NULL, "
                "total_cost_usd NUMERIC(12, 6) NULL, "
                "sdk_usage_json JSON NULL, "
                "sdk_model_usage_json JSON NULL, "
                "error_message TEXT NULL"
                ")"
            ))
            await conn.execute(text("CREATE INDEX idx_usage_events_started_at ON usage_events (started_at)"))
            await conn.execute(text("CREATE INDEX idx_usage_events_user_started ON usage_events (user_id, started_at)"))
            await conn.execute(text("CREATE INDEX idx_usage_events_agent_started ON usage_events (agent_id, started_at)"))
            await conn.execute(text("CREATE INDEX idx_usage_events_status_started ON usage_events (status, started_at)"))

        # usage_resource_events 表
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='usage_resource_events'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE usage_resource_events ("
                "id SERIAL PRIMARY KEY, "
                "usage_event_id INTEGER NOT NULL REFERENCES usage_events(id) ON DELETE CASCADE, "
                "resource_type VARCHAR NOT NULL, "
                "resource_name VARCHAR NOT NULL, "
                "plugin_name VARCHAR NULL, "
                "source VARCHAR NOT NULL, "
                "tool_use_id VARCHAR NULL, "
                "is_error BOOLEAN NOT NULL DEFAULT FALSE, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))
            await conn.execute(text("CREATE INDEX idx_usage_resource_event ON usage_resource_events (usage_event_id)"))
            await conn.execute(text("CREATE INDEX idx_usage_resource_type_name ON usage_resource_events (resource_type, resource_name)"))
            await conn.execute(text("CREATE INDEX idx_usage_resource_plugin ON usage_resource_events (plugin_name)"))
```

- [ ] **Step 6: Run tests and commit**

Run:

```bash
cd backend
uv run pytest tests/test_usage_models.py tests/test_db.py -v
```

Expected: PASS.

Commit:

```bash
git add backend/app/models/usage.py backend/app/models/__init__.py backend/app/db/__init__.py backend/app/db/migrations.py backend/tests/conftest.py backend/tests/test_usage_models.py
git commit -m "feat: add usage analytics models"
```

---

### Task 2: Usage Extraction and Persistence Service

**Files:**
- Create: `backend/app/modules/usage/__init__.py`
- Create: `backend/app/modules/usage/service.py`
- Test: `backend/tests/test_usage_service.py`

- [ ] **Step 1: Write failing service tests**

Create `backend/tests/test_usage_service.py`:

```python
from datetime import datetime, timezone
from types import SimpleNamespace


def test_extract_token_counts_prefers_usage_fields():
    from app.modules.usage.service import extract_token_counts

    usage = {"input_tokens": 12, "output_tokens": 34}

    assert extract_token_counts(usage) == (12, 34, 46)


def test_extract_token_counts_supports_nested_model_usage():
    from app.modules.usage.service import extract_token_counts

    usage = None
    model_usage = {
        "claude-sonnet": {
            "input_tokens": 7,
            "output_tokens": 8,
        },
        "claude-haiku": {
            "input_tokens": 2,
            "output_tokens": 3,
        },
    }

    assert extract_token_counts(usage, model_usage) == (9, 11, 20)


def test_collect_resources_records_skill_tool_use_and_plugin_prefix():
    from app.modules.usage.service import collect_usage_resources

    resources = collect_usage_resources(
        prompt="普通问题",
        commands=[],
        tool_uses=[
            {"id": "t1", "name": "Skill", "input": {"skill": "employee-management"}},
            {"id": "t2", "name": "Skill", "input": {"skill": "superpowers:brainstorming"}},
        ],
        tool_results=[{"tool_use_id": "t2", "is_error": True}],
    )

    assert [r.resource_type for r in resources] == ["skill", "plugin"]
    assert resources[0].resource_name == "employee-management"
    assert resources[0].source == "tool_use"
    assert resources[1].resource_name == "superpowers:brainstorming"
    assert resources[1].plugin_name == "superpowers"
    assert resources[1].is_error is True


def test_collect_resources_records_valid_slash_commands_only():
    from app.modules.usage.service import collect_usage_resources

    resources = collect_usage_resources(
        prompt="/superpowers:brainstorming 请先设计\n/unknown 不应记录",
        commands=[
            {"name": "superpowers:brainstorming", "source": "plugin", "plugin": "superpowers"},
            {"name": "employee-management", "source": "skill", "plugin": None},
        ],
        tool_uses=[],
        tool_results=[],
    )

    assert len(resources) == 1
    assert resources[0].resource_type == "plugin"
    assert resources[0].resource_name == "superpowers:brainstorming"
    assert resources[0].source == "slash_command"


async def test_persist_usage_event_writes_main_and_resources(app_env):
    from app.db.session import async_session
    from app.models import Agent, ChatSession, UsageEvent, User
    from app.modules.usage.service import CollectedResource, persist_usage_event
    from sqlalchemy import select

    async with async_session() as session:
        user = User(username="alice", password_hash="x", display_name="Alice")
        agent = Agent(name="分析助手", code="analysis-agent")
        session.add_all([user, agent])
        await session.commit()
        await session.refresh(user)
        await session.refresh(agent)
        chat = ChatSession(id="sid-1", user_id=user.id, agent_id=agent.id, title="t")
        session.add(chat)
        await session.commit()

    await persist_usage_event(
        user=SimpleNamespace(id=user.id, username="alice"),
        session_id="sid-1",
        agent=SimpleNamespace(id=agent.id, name="分析助手", code="analysis-agent"),
        started_at=datetime(2026, 5, 20, 1, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 20, 1, 1, tzinfo=timezone.utc),
        status="success",
        stop_reason="end_turn",
        usage={"input_tokens": 10, "output_tokens": 20},
        model_usage=None,
        duration_ms=1000,
        duration_api_ms=900,
        total_cost_usd=None,
        error_message=None,
        resources=[
            CollectedResource(
                resource_type="skill",
                resource_name="employee-management",
                plugin_name=None,
                source="tool_use",
                tool_use_id="t1",
                is_error=False,
            )
        ],
    )

    async with async_session() as session:
        event = (await session.execute(select(UsageEvent))).scalar_one()
        assert event.username == "alice"
        assert event.agent_name == "分析助手"
        assert event.input_tokens == 10
        assert event.output_tokens == 20
        assert event.total_tokens == 30
        assert len(event.resources) == 1
        assert event.resources[0].resource_name == "employee-management"
```

- [ ] **Step 2: Run service tests and verify they fail**

Run:

```bash
cd backend
uv run pytest tests/test_usage_service.py -v
```

Expected: FAIL because `app.modules.usage.service` does not exist.

- [ ] **Step 3: Implement extraction and persistence service**

Create `backend/app/modules/usage/__init__.py`:

```python
"""Usage analytics module。"""
```

Create `backend/app/modules/usage/service.py`:

```python
"""Usage analytics 采集与聚合服务。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.db.session import async_session
from app.models import Agent, UsageEvent, UsageResourceEvent, User

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectedResource:
    resource_type: str
    resource_name: str
    plugin_name: str | None
    source: str
    tool_use_id: str | None
    is_error: bool


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    return 0


def extract_token_counts(
    usage: dict[str, Any] | None,
    model_usage: dict[str, Any] | None = None,
) -> tuple[int, int, int]:
    """从 SDK usage/model_usage 中提取输入、输出和总 token。"""
    if isinstance(usage, dict):
        input_tokens = _int_value(usage.get("input_tokens"))
        output_tokens = _int_value(usage.get("output_tokens"))
        if input_tokens or output_tokens:
            return input_tokens, output_tokens, input_tokens + output_tokens

    input_total = 0
    output_total = 0
    if isinstance(model_usage, dict):
        for value in model_usage.values():
            if not isinstance(value, dict):
                continue
            input_total += _int_value(value.get("input_tokens"))
            output_total += _int_value(value.get("output_tokens"))
    return input_total, output_total, input_total + output_total


def _skill_name_from_input(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if not isinstance(value, dict):
        return None
    for key in ("skill", "name", "command"):
        raw = value.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip().lstrip("/")
    return None


def _resource_from_command(command: str, *, source: str, tool_use_id: str | None, is_error: bool) -> CollectedResource:
    if ":" in command:
        plugin_name = command.split(":", 1)[0]
        return CollectedResource("plugin", command, plugin_name, source, tool_use_id, is_error)
    return CollectedResource("skill", command, None, source, tool_use_id, is_error)


def _prompt_commands(prompt: str) -> list[str]:
    return [match.group(1) for match in re.finditer(r"(?<!\S)/([A-Za-z0-9_.:-]+)", prompt)]


def collect_usage_resources(
    *,
    prompt: str,
    commands: list[dict[str, Any]],
    tool_uses: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
) -> list[CollectedResource]:
    """根据 tool_use/tool_result 与 slash command 收集实际资源使用。"""
    result_errors = {
        str(item.get("tool_use_id")): bool(item.get("is_error", False))
        for item in tool_results
        if item.get("tool_use_id")
    }
    collected: list[CollectedResource] = []
    seen: set[tuple[str, str, str, str | None]] = set()

    def add(resource: CollectedResource) -> None:
        key = (resource.resource_type, resource.resource_name, resource.source, resource.tool_use_id)
        if key in seen:
            return
        seen.add(key)
        collected.append(resource)

    for evt in tool_uses:
        if evt.get("name") != "Skill":
            continue
        command = _skill_name_from_input(evt.get("input"))
        if not command:
            continue
        tool_use_id = str(evt.get("id") or "") or None
        add(_resource_from_command(
            command,
            source="tool_use",
            tool_use_id=tool_use_id,
            is_error=result_errors.get(tool_use_id or "", False),
        ))

    command_map = {str(item.get("name")): item for item in commands}
    for command in _prompt_commands(prompt):
        meta = command_map.get(command)
        if meta is None:
            continue
        source = str(meta.get("source") or "")
        if source == "plugin":
            plugin_name = str(meta.get("plugin") or command.split(":", 1)[0])
            add(CollectedResource("plugin", command, plugin_name, "slash_command", None, False))
        elif source == "skill":
            add(CollectedResource("skill", command, None, "slash_command", None, False))
    return collected


async def persist_usage_event(
    *,
    user: User,
    session_id: str,
    agent: Agent | None,
    started_at: datetime,
    ended_at: datetime,
    status: str,
    stop_reason: str | None,
    usage: dict[str, Any] | None,
    model_usage: dict[str, Any] | None,
    duration_ms: int | None,
    duration_api_ms: int | None,
    total_cost_usd: float | Decimal | None,
    error_message: str | None,
    resources: list[CollectedResource],
) -> None:
    """保存一轮对话统计；调用方负责捕获异常以保护聊天链路。"""
    input_tokens, output_tokens, total_tokens = extract_token_counts(usage, model_usage)
    cost = Decimal(str(total_cost_usd)) if total_cost_usd is not None else None
    async with async_session() as session:
        event = UsageEvent(
            user_id=user.id,
            username=user.username,
            session_id=session_id,
            agent_id=agent.id if agent else None,
            agent_name=agent.name if agent else None,
            agent_code=agent.code if agent else None,
            started_at=started_at,
            ended_at=ended_at,
            status=status,
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            duration_api_ms=duration_api_ms,
            total_cost_usd=cost,
            sdk_usage_json=usage,
            sdk_model_usage_json=model_usage,
            error_message=error_message[:1000] if error_message else None,
        )
        session.add(event)
        await session.flush()
        for item in resources:
            session.add(UsageResourceEvent(
                usage_event_id=event.id,
                resource_type=item.resource_type,
                resource_name=item.resource_name,
                plugin_name=item.plugin_name,
                source=item.source,
                tool_use_id=item.tool_use_id,
                is_error=item.is_error,
            ))
        await session.commit()
```

- [ ] **Step 4: Run service tests and commit**

Run:

```bash
cd backend
uv run pytest tests/test_usage_service.py -v
```

Expected: PASS.

Commit:

```bash
git add backend/app/modules/usage backend/tests/test_usage_service.py
git commit -m "feat: add usage analytics capture service"
```

---

### Task 3: Integrate Usage Capture Into Chat Streaming

**Files:**
- Modify: `backend/app/integrations/claude/runner.py`
- Modify: `backend/app/modules/sessions/streaming.py`
- Test: `backend/tests/test_claude_runner.py`
- Test: `backend/tests/test_chat_api.py`

- [ ] **Step 1: Write failing chat persistence tests**

Extend `backend/tests/test_chat_api.py`:

```python
async def test_chat_sse_persists_usage_event(logged_in_client, monkeypatch):
    from dataclasses import dataclass

    c = logged_in_client
    from app.db.session import async_session
    from app.models import Agent

    async with async_session() as session:
        agent = Agent(name="统计助手", code="usage-agent")
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        agent_id = agent.id

    sid = (await c.post("/api/sessions", json={"agent_id": agent_id})).json()["id"]

    from app.integrations.claude.runner import ChatRunSummary

    async def fake_stream_chat(*, prompt, claude_session_id, user_workspace, agent, on_message, stop_event=None):
        await on_message({"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "demo-skill"}})
        await on_message({"type": "tool_result", "tool_use_id": "t1", "is_error": False})
        await on_message({"type": "result", "session_id": "new-sid", "is_error": False, "stop_reason": "end_turn"})
        return ChatRunSummary(
            session_id="new-sid",
            is_error=False,
            stop_reason="end_turn",
            usage={"input_tokens": 11, "output_tokens": 22},
            model_usage=None,
            duration_ms=100,
            duration_api_ms=90,
            total_cost_usd=None,
            interrupted=False,
            error_message=None,
        )

    import app.modules.sessions.streaming as streaming_mod
    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)

    async with c.stream("POST", f"/api/sessions/{sid}/chat", json={"prompt": "你好"}) as response:
        async for _ in response.aiter_bytes():
            pass

    from app.db.session import async_session
    from app.models import UsageEvent
    from sqlalchemy import select

    async with async_session() as session:
        event = (await session.execute(select(UsageEvent))).scalar_one()
        assert event.session_id == sid
        assert event.agent_name == "统计助手"
        assert event.input_tokens == 11
        assert event.output_tokens == 22
        assert event.total_tokens == 33
        assert event.status == "success"
        assert event.resources[0].resource_name == "demo-skill"


async def test_chat_sse_records_error_usage_without_prompt(logged_in_client, monkeypatch):
    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]

    async def fake_stream_chat(**kwargs):
        raise RuntimeError("claude exploded")

    import app.modules.sessions.streaming as streaming_mod
    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)

    async with c.stream("POST", f"/api/sessions/{sid}/chat", json={"prompt": "敏感内容"}) as response:
        async for _ in response.aiter_bytes():
            pass

    from app.db.session import async_session
    from app.models import UsageEvent
    from sqlalchemy import select

    async with async_session() as session:
        event = (await session.execute(select(UsageEvent))).scalar_one()
        assert event.status == "error"
        assert "claude exploded" in event.error_message
        assert "敏感内容" not in event.error_message
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
cd backend
uv run pytest tests/test_chat_api.py::test_chat_sse_persists_usage_event tests/test_chat_api.py::test_chat_sse_records_error_usage_without_prompt -v
```

Expected: FAIL because `ChatRunSummary` and persistence integration do not exist.

- [ ] **Step 3: Add `ChatRunSummary` to Claude runner**

Modify `backend/app/integrations/claude/runner.py` imports:

```python
from dataclasses import dataclass
from typing import Any
```

Add near the top:

```python
@dataclass(frozen=True)
class ChatRunSummary:
    """Claude 一轮运行结束后的统计元数据。"""

    session_id: str | None
    is_error: bool
    stop_reason: str | None
    usage: dict[str, Any] | None
    model_usage: dict[str, Any] | None
    duration_ms: int | None
    duration_api_ms: int | None
    total_cost_usd: float | None
    interrupted: bool
    error_message: str | None
```

Change `stream_chat` return type from `str | None` to `ChatRunSummary`. Inside the receive loop, keep `result_message: ResultMessage | None = None`; when a `ResultMessage` arrives, assign it. At the end return:

```python
    return ChatRunSummary(
        session_id=new_session_id,
        is_error=bool(result_message.is_error) if result_message else False,
        stop_reason=result_message.stop_reason if result_message else None,
        usage=result_message.usage if result_message else None,
        model_usage=result_message.model_usage if result_message else None,
        duration_ms=result_message.duration_ms if result_message else None,
        duration_api_ms=result_message.duration_api_ms if result_message else None,
        total_cost_usd=result_message.total_cost_usd if result_message else None,
        interrupted=bool(stop_event and stop_event.is_set()),
        error_message="; ".join(result_message.errors or []) if result_message and result_message.errors else None,
    )
```

- [ ] **Step 4: Update runner tests that expected a string**

In `backend/tests/test_claude_runner.py`, replace assertions like:

```python
assert sid == "new-sid"
```

with:

```python
assert summary.session_id == "new-sid"
```

Use the variable name `summary` in tests that call `stream_chat`.

- [ ] **Step 5: Capture events and persist usage in streaming**

Modify `backend/app/modules/sessions/streaming.py` imports:

```python
from app.modules.catalog.commands import scan_agent_commands
from app.modules.agents.workdir import get_agent_workdir
from app.modules.usage.service import collect_usage_resources, persist_usage_event
```

Inside `stream_session_chat`, before `on_message`:

```python
    started_at = datetime.now(timezone.utc)
    tool_uses: list[dict] = []
    tool_results: list[dict] = []
```

Update `on_message`:

```python
    async def on_message(evt: dict) -> None:
        if evt.get("type") == "tool_use":
            tool_uses.append(evt)
        elif evt.get("type") == "tool_result":
            tool_results.append(evt)
        await queue.put(evt)
```

In `runner`, assign `summary = await stream_chat(...)` and queue `summary` instead of only session id:

```python
            await queue.put({"__internal": "done", "summary": summary})
```

In the exception block, queue a done payload with `summary=None` and `error_message=str(exc)`.

In `event_source`, when handling done:

```python
                    summary = evt.get("summary")
                    error_message = evt.get("error_message")
                    new_sid = summary.session_id if summary else prior_session_id
                    status_value = (
                        "error" if error_message else
                        "interrupted" if summary and summary.interrupted else
                        "error" if summary and summary.is_error else
                        "success"
                    )
                    commands = []
                    if agent is not None:
                        commands = scan_agent_commands(get_agent_workdir(agent.code))
                    resources = collect_usage_resources(
                        prompt=prompt,
                        commands=commands,
                        tool_uses=tool_uses,
                        tool_results=tool_results,
                    )
                    try:
                        await persist_usage_event(
                            user=user,
                            session_id=session_id,
                            agent=agent,
                            started_at=started_at,
                            ended_at=datetime.now(timezone.utc),
                            status=status_value,
                            stop_reason=summary.stop_reason if summary else None,
                            usage=summary.usage if summary else None,
                            model_usage=summary.model_usage if summary else None,
                            duration_ms=summary.duration_ms if summary else None,
                            duration_api_ms=summary.duration_api_ms if summary else None,
                            total_cost_usd=summary.total_cost_usd if summary else None,
                            error_message=error_message or (summary.error_message if summary else None),
                            resources=resources,
                        )
                    except Exception:
                        logger.exception("Usage analytics persistence failed")
```

Keep the existing `ChatSession` update logic, using `new_sid`.

- [ ] **Step 6: Run chat and runner tests**

Run:

```bash
cd backend
uv run pytest tests/test_claude_runner.py tests/test_chat_api.py tests/test_usage_service.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/integrations/claude/runner.py backend/app/modules/sessions/streaming.py backend/tests/test_claude_runner.py backend/tests/test_chat_api.py
git commit -m "feat: capture usage during chat streaming"
```

---

### Task 4: Admin Usage Summary API

**Files:**
- Create: `backend/app/schemas/usage.py`
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/modules/usage/service.py`
- Create: `backend/app/api/routes/admin_usage.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_usage_api.py`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/test_usage_api.py`:

```python
from datetime import datetime, timezone


async def _seed_usage():
    from app.db.session import async_session
    from app.models import UsageEvent, UsageResourceEvent, User

    async with async_session() as session:
        user = User(username="bob", password_hash="x", role="user")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        event = UsageEvent(
            user_id=user.id,
            username="bob",
            session_id="sid",
            agent_id=10,
            agent_name="分析助手",
            agent_code="analysis",
            started_at=datetime(2026, 5, 20, 1, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 5, 20, 1, 1, tzinfo=timezone.utc),
            status="success",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )
        session.add(event)
        await session.flush()
        session.add_all([
            UsageResourceEvent(
                usage_event_id=event.id,
                resource_type="skill",
                resource_name="employee-management",
                source="tool_use",
                is_error=False,
            ),
            UsageResourceEvent(
                usage_event_id=event.id,
                resource_type="plugin",
                resource_name="superpowers:brainstorming",
                plugin_name="superpowers",
                source="slash_command",
                is_error=False,
            ),
        ])
        await session.commit()


async def test_usage_summary_requires_admin(logged_in_client):
    res = await logged_in_client.get("/api/admin/usage/summary")
    assert res.status_code == 403


async def test_usage_summary_returns_overview_and_rankings(admin_client):
    await _seed_usage()

    res = await admin_client.get("/api/admin/usage/summary?range=custom&start=2026-05-20&end=2026-05-20")

    assert res.status_code == 200
    body = res.json()
    assert body["overview"]["call_count"] == 1
    assert body["overview"]["active_user_count"] == 1
    assert body["overview"]["total_tokens"] == 150
    assert body["agents"][0]["agent_name"] == "分析助手"
    assert body["agents"][0]["call_count"] == 1
    assert body["agents"][0]["active_user_count"] == 1
    assert body["agents"][0]["total_tokens"] == 150
    assert body["agents"][0]["error_count"] == 0
    assert body["skills"][0] == {"resource_name": "employee-management", "trigger_count": 1}
    assert body["plugins"][0] == {
        "plugin_name": "superpowers",
        "resource_name": "superpowers:brainstorming",
        "trigger_count": 1,
    }
```

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```bash
cd backend
uv run pytest tests/test_usage_api.py -v
```

Expected: FAIL with 404 for `/api/admin/usage/summary`.

- [ ] **Step 3: Add usage response schemas**

Create `backend/app/schemas/usage.py`:

```python
"""Usage analytics API schemas。"""

from pydantic import BaseModel


class UsageOverviewOut(BaseModel):
    call_count: int
    active_user_count: int
    agent_count: int
    skill_trigger_count: int
    plugin_trigger_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    error_count: int
    interrupted_count: int
    avg_duration_ms: float | None


class UsageTimeseriesPointOut(BaseModel):
    bucket: str
    call_count: int
    active_user_count: int
    total_tokens: int
    error_count: int
    input_tokens: int
    output_tokens: int


class UsageAgentRankOut(BaseModel):
    agent_id: int | None
    agent_name: str
    call_count: int
    active_user_count: int
    total_tokens: int
    error_count: int


class UsageSkillRankOut(BaseModel):
    resource_name: str
    trigger_count: int


class UsagePluginRankOut(BaseModel):
    plugin_name: str
    resource_name: str
    trigger_count: int


class UsageStatusBreakdownOut(BaseModel):
    status: str
    count: int


class UsageTokenSummaryOut(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    timeseries: list[UsageTimeseriesPointOut]


class UsageSummaryOut(BaseModel):
    range: str
    start: str
    end: str
    granularity: str
    overview: UsageOverviewOut
    timeseries: list[UsageTimeseriesPointOut]
    agents: list[UsageAgentRankOut]
    skills: list[UsageSkillRankOut]
    plugins: list[UsagePluginRankOut]
    tokens: UsageTokenSummaryOut
    status_breakdown: list[UsageStatusBreakdownOut]
```

Export these in `backend/app/schemas/__init__.py`.

- [ ] **Step 4: Add aggregation service functions**

Append to `backend/app/modules/usage/service.py`:

```python
from datetime import date, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UsageResourceEvent

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def resolve_usage_window(range_name: str, start: date | None, end: date | None) -> tuple[datetime, datetime, str, str, str]:
    today = datetime.now(SHANGHAI_TZ).date()
    if range_name == "today":
        local_start = datetime.combine(today, time.min, tzinfo=SHANGHAI_TZ)
        local_end = local_start + timedelta(days=1)
        granularity = "hour"
    elif range_name == "7d":
        local_start = datetime.combine(today - timedelta(days=6), time.min, tzinfo=SHANGHAI_TZ)
        local_end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=SHANGHAI_TZ)
        granularity = "day"
    elif range_name == "30d":
        local_start = datetime.combine(today - timedelta(days=29), time.min, tzinfo=SHANGHAI_TZ)
        local_end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=SHANGHAI_TZ)
        granularity = "day"
    elif range_name == "custom" and start and end:
        local_start = datetime.combine(start, time.min, tzinfo=SHANGHAI_TZ)
        local_end = datetime.combine(end + timedelta(days=1), time.min, tzinfo=SHANGHAI_TZ)
        granularity = "hour" if start == end else "day"
    else:
        raise ValueError("无效的时间范围")
    return (
        local_start.astimezone(ZoneInfo("UTC")),
        local_end.astimezone(ZoneInfo("UTC")),
        granularity,
        local_start.date().isoformat(),
        (local_end.date() - timedelta(days=1)).isoformat(),
    )


async def build_usage_summary(
    db: AsyncSession,
    *,
    range_name: str,
    start: date | None,
    end: date | None,
) -> dict:
    start_dt, end_dt, granularity, start_label, end_label = resolve_usage_window(range_name, start, end)
    base_filter = (UsageEvent.started_at >= start_dt, UsageEvent.started_at < end_dt)

    overview_row = (await db.execute(
        select(
            func.count(UsageEvent.id),
            func.count(distinct(UsageEvent.user_id)),
            func.count(distinct(UsageEvent.agent_id)),
            func.coalesce(func.sum(UsageEvent.input_tokens), 0),
            func.coalesce(func.sum(UsageEvent.output_tokens), 0),
            func.coalesce(func.sum(UsageEvent.total_tokens), 0),
            func.coalesce(func.sum(case((UsageEvent.status == "error", 1), else_=0)), 0),
            func.coalesce(func.sum(case((UsageEvent.status == "interrupted", 1), else_=0)), 0),
            func.avg(UsageEvent.duration_ms),
        ).where(*base_filter)
    )).one()

    skill_count = (await db.execute(
        select(func.count(UsageResourceEvent.id))
        .join(UsageEvent, UsageEvent.id == UsageResourceEvent.usage_event_id)
        .where(*base_filter, UsageResourceEvent.resource_type == "skill")
    )).scalar_one()
    plugin_count = (await db.execute(
        select(func.count(UsageResourceEvent.id))
        .join(UsageEvent, UsageEvent.id == UsageResourceEvent.usage_event_id)
        .where(*base_filter, UsageResourceEvent.resource_type == "plugin")
    )).scalar_one()

    agents = (await db.execute(
        select(
            UsageEvent.agent_id,
            func.coalesce(UsageEvent.agent_name, "未选择智能体").label("agent_name"),
            func.count(UsageEvent.id).label("call_count"),
            func.count(distinct(UsageEvent.user_id)).label("active_user_count"),
            func.coalesce(func.sum(UsageEvent.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(case((UsageEvent.status == "error", 1), else_=0)), 0).label("error_count"),
        )
        .where(*base_filter)
        .group_by(UsageEvent.agent_id, UsageEvent.agent_name)
        .order_by(func.count(UsageEvent.id).desc())
        .limit(10)
    )).mappings().all()

    skills = (await db.execute(
        select(UsageResourceEvent.resource_name, func.count(UsageResourceEvent.id).label("trigger_count"))
        .join(UsageEvent, UsageEvent.id == UsageResourceEvent.usage_event_id)
        .where(*base_filter, UsageResourceEvent.resource_type == "skill")
        .group_by(UsageResourceEvent.resource_name)
        .order_by(func.count(UsageResourceEvent.id).desc())
        .limit(10)
    )).mappings().all()

    plugins = (await db.execute(
        select(
            func.coalesce(UsageResourceEvent.plugin_name, "").label("plugin_name"),
            UsageResourceEvent.resource_name,
            func.count(UsageResourceEvent.id).label("trigger_count"),
        )
        .join(UsageEvent, UsageEvent.id == UsageResourceEvent.usage_event_id)
        .where(*base_filter, UsageResourceEvent.resource_type == "plugin")
        .group_by(UsageResourceEvent.plugin_name, UsageResourceEvent.resource_name)
        .order_by(func.count(UsageResourceEvent.id).desc())
        .limit(10)
    )).mappings().all()

    status_rows = (await db.execute(
        select(UsageEvent.status, func.count(UsageEvent.id).label("count"))
        .where(*base_filter)
        .group_by(UsageEvent.status)
    )).mappings().all()

    # PostgreSQL date_trunc 以 UTC bucket 聚合；前端只展示短日期/小时标签。
    bucket_expr = func.date_trunc("hour" if granularity == "hour" else "day", UsageEvent.started_at)
    series_rows = (await db.execute(
        select(
            bucket_expr.label("bucket"),
            func.count(UsageEvent.id).label("call_count"),
            func.count(distinct(UsageEvent.user_id)).label("active_user_count"),
            func.coalesce(func.sum(UsageEvent.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(case((UsageEvent.status == "error", 1), else_=0)), 0).label("error_count"),
            func.coalesce(func.sum(UsageEvent.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(UsageEvent.output_tokens), 0).label("output_tokens"),
        )
        .where(*base_filter)
        .group_by(bucket_expr)
        .order_by(bucket_expr)
    )).mappings().all()

    timeseries = [
        {
            "bucket": row["bucket"].astimezone(SHANGHAI_TZ).isoformat(),
            "call_count": row["call_count"],
            "active_user_count": row["active_user_count"],
            "total_tokens": row["total_tokens"],
            "error_count": row["error_count"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
        }
        for row in series_rows
    ]

    overview = {
        "call_count": overview_row[0],
        "active_user_count": overview_row[1],
        "agent_count": overview_row[2],
        "skill_trigger_count": skill_count,
        "plugin_trigger_count": plugin_count,
        "input_tokens": overview_row[3],
        "output_tokens": overview_row[4],
        "total_tokens": overview_row[5],
        "error_count": overview_row[6],
        "interrupted_count": overview_row[7],
        "avg_duration_ms": float(overview_row[8]) if overview_row[8] is not None else None,
    }
    return {
        "range": range_name,
        "start": start_label,
        "end": end_label,
        "granularity": granularity,
        "overview": overview,
        "timeseries": timeseries,
        "agents": [dict(row) for row in agents],
        "skills": [dict(row) for row in skills],
        "plugins": [dict(row) for row in plugins],
        "tokens": {
            "input_tokens": overview["input_tokens"],
            "output_tokens": overview["output_tokens"],
            "total_tokens": overview["total_tokens"],
            "timeseries": timeseries,
        },
        "status_breakdown": [dict(row) for row in status_rows],
    }
```

- [ ] **Step 5: Add admin route**

Create `backend/app/api/routes/admin_usage.py`:

```python
"""管理员使用统计 API。"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import User
from app.modules.usage.service import build_usage_summary
from app.schemas import UsageSummaryOut

router = APIRouter(prefix="/api/admin/usage", dependencies=[Depends(require_admin)])


@router.get("/summary", response_model=UsageSummaryOut)
async def usage_summary(
    range: str = Query("today", pattern="^(today|7d|30d|custom)$"),
    start: date | None = None,
    end: date | None = None,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UsageSummaryOut:
    try:
        data = await build_usage_summary(db, range_name=range, start=start, end=end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UsageSummaryOut.model_validate(data)
```

Modify `backend/app/api/router.py`:

```python
from app.api.routes import admin_usage
router.include_router(admin_usage.router)
```

Modify `backend/tests/conftest.py` Layer 4 and Layer 5 to reload `app.modules.usage.service` and `app.api.routes.admin_usage`.

- [ ] **Step 6: Run API tests and commit**

Run:

```bash
cd backend
uv run pytest tests/test_usage_api.py tests/test_usage_service.py -v
```

Expected: PASS.

Commit:

```bash
git add backend/app/schemas/usage.py backend/app/schemas/__init__.py backend/app/modules/usage/service.py backend/app/api/routes/admin_usage.py backend/app/api/router.py backend/tests/conftest.py backend/tests/test_usage_api.py
git commit -m "feat: add usage analytics admin API"
```

---

### Task 5: Frontend Types, API Client, and Navigation

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add frontend usage types**

Modify `frontend/src/types/index.ts`:

```ts
export interface UsageOverview {
  call_count: number;
  active_user_count: number;
  agent_count: number;
  skill_trigger_count: number;
  plugin_trigger_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  error_count: number;
  interrupted_count: number;
  avg_duration_ms: number | null;
}

export interface UsageTimeseriesPoint {
  bucket: string;
  call_count: number;
  active_user_count: number;
  total_tokens: number;
  error_count: number;
  input_tokens: number;
  output_tokens: number;
}

export interface UsageAgentRank {
  agent_id: number | null;
  agent_name: string;
  call_count: number;
  active_user_count: number;
  total_tokens: number;
  error_count: number;
}

export interface UsageSkillRank {
  resource_name: string;
  trigger_count: number;
}

export interface UsagePluginRank {
  plugin_name: string;
  resource_name: string;
  trigger_count: number;
}

export interface UsageStatusBreakdown {
  status: "success" | "error" | "interrupted" | string;
  count: number;
}

export interface UsageTokenSummary {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  timeseries: UsageTimeseriesPoint[];
}

export interface UsageSummary {
  range: string;
  start: string;
  end: string;
  granularity: "hour" | "day" | string;
  overview: UsageOverview;
  timeseries: UsageTimeseriesPoint[];
  agents: UsageAgentRank[];
  skills: UsageSkillRank[];
  plugins: UsagePluginRank[];
  tokens: UsageTokenSummary;
  status_breakdown: UsageStatusBreakdown[];
}
```

Update `ViewName`:

```ts
export type ViewName = "new" | "chat" | "workspace" | "agents" | "skills" | "feedback" | "usage";
```

- [ ] **Step 2: Add API client method**

Modify imports in `frontend/src/api/client.ts` to include `UsageSummary`.

Add:

```ts
  adminUsageSummary: (params: {
    range?: "today" | "7d" | "30d" | "custom";
    start?: string;
    end?: string;
  } = {}) => {
    const query = new URLSearchParams();
    if (params.range) query.set("range", params.range);
    if (params.start) query.set("start", params.start);
    if (params.end) query.set("end", params.end);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<UsageSummary>(`/api/admin/usage/summary${suffix}`);
  },
```

- [ ] **Step 3: Add admin navigation**

Modify `frontend/src/components/Sidebar.tsx` in `getNavItems`:

```ts
    items.push({ id: "usage", label: "使用统计", icon: I.LayoutDashboard, group: "管理" });
```

Place it before “反馈管理”.

- [ ] **Step 4: Add app route placeholder**

Create the import in `frontend/src/App.tsx`:

```ts
import UsageAnalyticsPage from "@/pages/UsageAnalyticsPage";
```

Update breadcrumb:

```ts
      : view === "usage"
      ? ["管理", "使用统计"]
```

Update main content routing:

```tsx
          ) : view === "usage" && auth.me.role === "admin" ? (
            <UsageAnalyticsPage />
```

- [ ] **Step 5: Run typecheck and commit after Task 6 creates the page**

Do not commit this task until Task 6 creates `UsageAnalyticsPage.tsx`; otherwise TypeScript import fails.

---

### Task 6: Frontend Usage Analytics Page

**Files:**
- Create: `frontend/src/pages/UsageAnalyticsPage.tsx`
- Modify: files from Task 5 are committed together here.

- [ ] **Step 1: Create dashboard page**

Create `frontend/src/pages/UsageAnalyticsPage.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import type {
  UsageAgentRank,
  UsagePluginRank,
  UsageSkillRank,
  UsageSummary,
  UsageTimeseriesPoint,
} from "@/types";
import { I } from "@/icons";
import { Btn } from "@/components/ui";

type RangeKey = "today" | "7d" | "30d" | "custom";

const emptyCustom = { start: "", end: "" };

export default function UsageAnalyticsPage() {
  const [range, setRange] = useState<RangeKey>("today");
  const [custom, setCustom] = useState(emptyCustom);
  const [data, setData] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (range === "custom" && (!custom.start || !custom.end)) return;
    let alive = true;
    setLoading(true);
    setError(null);
    api.adminUsageSummary({
      range,
      start: range === "custom" ? custom.start : undefined,
      end: range === "custom" ? custom.end : undefined,
    })
      .then((result) => {
        if (alive) setData(result);
      })
      .catch((err) => {
        if (alive) setError(formatError(err));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [range, custom.start, custom.end]);

  const hasData = !!data && data.overview.call_count > 0;

  return (
    <div style={{ flex: 1, overflow: "auto", padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-end", marginBottom: 18 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 650, color: "var(--ink)" }}>使用统计</h1>
          <p style={{ margin: "6px 0 0", fontSize: 13, color: "var(--ink-3)" }}>
            按时间段查看平台调用、智能体、技能、插件与 token 消耗
          </p>
        </div>
        <RangeControls range={range} custom={custom} onRange={setRange} onCustom={setCustom} />
      </div>

      {loading ? (
        <StatePanel icon={<I.Loader size={18} />} text="正在加载使用统计..." />
      ) : error ? (
        <StatePanel icon={<I.CircleAlert size={18} />} text={error} />
      ) : !data || !hasData ? (
        <StatePanel icon={<I.Database size={18} />} text="当前时间范围暂无使用数据" />
      ) : (
        <div style={{ display: "grid", gap: 14 }}>
          <KpiGrid data={data} />
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(280px, 1fr)", gap: 14 }}>
            <ChartPanel title="调用与 token 趋势">
              <UsageBars points={data.timeseries} />
            </ChartPanel>
            <ChartPanel title="状态分布">
              <StatusBar data={data} />
            </ChartPanel>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 14 }}>
            <AgentRank rows={data.agents} />
            <SkillRank rows={data.skills} />
            <PluginRank rows={data.plugins} />
          </div>
        </div>
      )}
    </div>
  );
}

function RangeControls({
  range,
  custom,
  onRange,
  onCustom,
}: {
  range: RangeKey;
  custom: { start: string; end: string };
  onRange: (range: RangeKey) => void;
  onCustom: (value: { start: string; end: string }) => void;
}) {
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
      {[
        ["today", "今天"],
        ["7d", "7 天"],
        ["30d", "30 天"],
        ["custom", "自定义"],
      ].map(([key, label]) => (
        <Btn key={key} size="sm" variant={range === key ? "primary" : "secondary"} onClick={() => onRange(key as RangeKey)}>
          {label}
        </Btn>
      ))}
      {range === "custom" && (
        <>
          <input type="date" value={custom.start} onChange={(e) => onCustom({ ...custom, start: e.target.value })} style={dateInputStyle} />
          <input type="date" value={custom.end} onChange={(e) => onCustom({ ...custom, end: e.target.value })} style={dateInputStyle} />
        </>
      )}
    </div>
  );
}

function KpiGrid({ data }: { data: UsageSummary }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12 }}>
      <Kpi title="调用次数" value={formatNumber(data.overview.call_count)} />
      <Kpi title="活跃用户" value={formatNumber(data.overview.active_user_count)} />
      <Kpi title="总 Token" value={formatCompact(data.overview.total_tokens)} sub={`${formatCompact(data.overview.input_tokens)} 输入 / ${formatCompact(data.overview.output_tokens)} 输出`} />
      <Kpi title="错误 / 中断" value={`${data.overview.error_count} / ${data.overview.interrupted_count}`} sub={`平均耗时 ${formatDuration(data.overview.avg_duration_ms)}`} />
    </div>
  );
}

function Kpi({ title, value, sub }: { title: string; value: string; sub?: string }) {
  return (
    <div style={panelStyle}>
      <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{title}</div>
      <div style={{ marginTop: 8, fontSize: 24, fontWeight: 700, color: "var(--ink)" }}>{value}</div>
      {sub && <div style={{ marginTop: 6, fontSize: 12, color: "var(--ink-3)" }}>{sub}</div>}
    </div>
  );
}

function UsageBars({ points }: { points: UsageTimeseriesPoint[] }) {
  const max = Math.max(...points.map((p) => p.call_count), 1);
  return (
    <div style={{ height: 190, display: "flex", alignItems: "flex-end", gap: 6, paddingTop: 12 }}>
      {points.map((point) => (
        <div key={point.bucket} title={`${formatBucket(point.bucket)} · ${point.call_count} 次 · ${formatCompact(point.total_tokens)} token`} style={{ flex: 1, minWidth: 8, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <div style={{ width: "100%", height: `${Math.max(6, (point.call_count / max) * 150)}px`, background: "var(--accent)", borderRadius: "4px 4px 0 0", opacity: 0.78 }} />
          <span style={{ fontSize: 10, color: "var(--ink-3)", writingMode: points.length > 12 ? "vertical-rl" : "horizontal-tb" }}>{formatBucket(point.bucket)}</span>
        </div>
      ))}
    </div>
  );
}

function StatusBar({ data }: { data: UsageSummary }) {
  const total = Math.max(data.overview.call_count, 1);
  const rows = ["success", "interrupted", "error"].map((status) => ({
    status,
    count: data.status_breakdown.find((item) => item.status === status)?.count ?? 0,
  }));
  return (
    <div>
      <div style={{ display: "flex", height: 30, borderRadius: 999, overflow: "hidden", background: "var(--bg-3)", marginTop: 24 }}>
        {rows.map((row) => (
          <div key={row.status} style={{ width: `${(row.count / total) * 100}%`, background: statusColor(row.status) }} />
        ))}
      </div>
      <div style={{ display: "grid", gap: 10, marginTop: 20 }}>
        {rows.map((row) => (
          <div key={row.status} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: "var(--ink-2)" }}>
            <span>{statusLabel(row.status)}</span>
            <strong>{row.count}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function AgentRank({ rows }: { rows: UsageAgentRank[] }) {
  return (
    <RankPanel title="智能体排行">
      {rows.map((row) => (
        <div key={`${row.agent_id}-${row.agent_name}`} style={rankRowStyle}>
          <div style={{ minWidth: 0 }}>
            <div style={rankTitleStyle}>{row.agent_name}</div>
            <div style={rankMetaStyle}>{row.active_user_count} 用户 · {formatCompact(row.total_tokens)} token · {row.error_count} 错误</div>
          </div>
          <strong>{row.call_count}</strong>
        </div>
      ))}
    </RankPanel>
  );
}

function SkillRank({ rows }: { rows: UsageSkillRank[] }) {
  return (
    <RankPanel title="Skill 排行">
      {rows.map((row) => (
        <SimpleRank key={row.resource_name} name={row.resource_name} count={row.trigger_count} />
      ))}
    </RankPanel>
  );
}

function PluginRank({ rows }: { rows: UsagePluginRank[] }) {
  return (
    <RankPanel title="Plugin 排行">
      {rows.map((row) => (
        <SimpleRank key={`${row.plugin_name}-${row.resource_name}`} name={row.resource_name} count={row.trigger_count} />
      ))}
    </RankPanel>
  );
}

function RankPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={panelStyle}>
      <h2 style={panelTitleStyle}>{title}</h2>
      <div style={{ display: "grid", gap: 10, marginTop: 12 }}>{children}</div>
    </div>
  );
}

function SimpleRank({ name, count }: { name: string; count: number }) {
  return (
    <div style={rankRowStyle}>
      <div style={rankTitleStyle}>{name}</div>
      <strong>{count}</strong>
    </div>
  );
}

function ChartPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={panelStyle}>
      <h2 style={panelTitleStyle}>{title}</h2>
      {children}
    </div>
  );
}

function StatePanel({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div style={{ ...panelStyle, minHeight: 220, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, color: "var(--ink-3)" }}>
      {icon}
      <span>{text}</span>
    </div>
  );
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatCompact(value: number) {
  return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function formatDuration(value: number | null) {
  if (value == null) return "-";
  if (value < 1000) return `${Math.round(value)}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

function formatBucket(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit" }).format(date);
}

function statusLabel(status: string) {
  if (status === "success") return "成功";
  if (status === "interrupted") return "中断";
  if (status === "error") return "错误";
  return status;
}

function statusColor(status: string) {
  if (status === "success") return "var(--success)";
  if (status === "interrupted") return "var(--warning)";
  if (status === "error") return "var(--danger)";
  return "var(--ink-3)";
}

function formatError(error: unknown): string {
  return error instanceof Error ? error.message : "加载使用统计失败";
}

const panelStyle = {
  border: "1px solid var(--line)",
  borderRadius: 8,
  background: "var(--surface)",
  padding: 16,
  boxShadow: "var(--shadow-sm)",
} satisfies React.CSSProperties;

const panelTitleStyle = {
  margin: 0,
  fontSize: 15,
  fontWeight: 650,
  color: "var(--ink)",
} satisfies React.CSSProperties;

const rankRowStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: 12,
  alignItems: "center",
  minWidth: 0,
} satisfies React.CSSProperties;

const rankTitleStyle = {
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
  color: "var(--ink)",
  fontSize: 13,
} satisfies React.CSSProperties;

const rankMetaStyle = {
  marginTop: 3,
  color: "var(--ink-3)",
  fontSize: 12,
} satisfies React.CSSProperties;

const dateInputStyle = {
  height: 32,
  border: "1px solid var(--line)",
  borderRadius: 8,
  background: "var(--bg)",
  color: "var(--ink)",
  padding: "0 8px",
} satisfies React.CSSProperties;
```

- [ ] **Step 2: Run TypeScript build and fix any compile errors**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS. If `var(--warning)` is not defined in CSS, replace it with `#f59e0b` in `statusColor`.

- [ ] **Step 3: Commit frontend navigation and page**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/components/Sidebar.tsx frontend/src/App.tsx frontend/src/pages/UsageAnalyticsPage.tsx
git commit -m "feat: add usage analytics dashboard"
```

---

### Task 7: Full Verification and Cleanup

**Files:**
- Review all files changed in Tasks 1-6.

- [ ] **Step 1: Run backend usage and chat tests**

Run:

```bash
cd backend
uv run pytest tests/test_usage_models.py tests/test_usage_service.py tests/test_usage_api.py tests/test_chat_api.py tests/test_claude_runner.py -v
```

Expected: PASS.

- [ ] **Step 2: Run backend smoke tests around affected APIs**

Run:

```bash
cd backend
uv run pytest tests/test_agents_api.py tests/test_sessions_api.py tests/test_messages_api.py -v
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Inspect git diff**

Run:

```bash
git status --short
git diff --stat HEAD
```

Expected: only usage analytics implementation files are modified.

- [ ] **Step 5: Final commit if verification fixes changed files**

If Step 1-4 required fixes after previous commits, commit only those fixes:

```bash
git add backend/app backend/tests frontend/src
git commit -m "fix: stabilize usage analytics"
```

If no files changed, do not create an empty commit.

---

## Spec Coverage Self-Review

- Per-chat-call collection: Task 3.
- Two-table model: Task 1.
- Multiple skills/plugins per call: Task 2 and Task 3.
- Actual trigger semantics, not configured resources: Task 2.
- Admin-only API and dashboard: Task 4, Task 5, Task 6.
- Today/7d/30d/custom ranges: Task 4 and Task 6.
- Agent rank with calls, active users, token, errors: Task 4 and Task 6.
- Skill/plugin ranks with trigger counts only: Task 4 and Task 6.
- Token input/output/total plus raw SDK JSON: Task 1, Task 2, Task 3.
- Error/interrupted inclusion: Task 3 and Task 4.
- No prompt/answer storage and no detail table page: Task 2, Task 4, Task 6.
- Verification: Task 7.
