import asyncio
import json
from types import SimpleNamespace

from app.integrations.claude.runner import ChatRunSummary


def _running_route_client(monkeypatch, owned_session):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.routes import sessions as sessions_routes

    async def fake_get_owned_session(db, session_id, user):
        return owned_session

    app = FastAPI()
    app.include_router(sessions_routes.router)
    app.dependency_overrides[sessions_routes.current_user] = lambda: SimpleNamespace(
        id=1,
        username="alice",
    )
    app.dependency_overrides[sessions_routes.get_db] = lambda: None
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        for dependency in dependant.dependencies:
            name = getattr(dependency.call, "__name__", "")
            if name == "current_user":
                app.dependency_overrides[dependency.call] = lambda: SimpleNamespace(
                    id=1,
                    username="alice",
                )
            elif name == "get_db":
                app.dependency_overrides[dependency.call] = lambda: None
    monkeypatch.setattr(
        sessions_routes,
        "get_owned_session_svc",
        fake_get_owned_session,
    )
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_chat_sse_writes_back_session_id(logged_in_client, monkeypatch):
    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]
    monkeypatch.setenv("ANTHROPIC_PROVIDER_DEEPSEEK_AUTH_TOKEN", "title-token")

    async def fake_stream_chat(**kwargs):
        prompt = kwargs["prompt"]
        claude_session_id = kwargs["claude_session_id"]
        on_message = kwargs["on_message"]
        assert prompt == "你好"
        assert claude_session_id is None
        await on_message({"type": "assistant_text", "text": "你好呀"})
        await on_message({"type": "result", "session_id": "new-sid", "is_error": False, "stop_reason": None})
        return ChatRunSummary(
            session_id="new-sid",
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

    import app.modules.sessions.streaming as streaming_mod
    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)

    async def fake_generate_chat_completion(**kwargs):
        return "问候回复"

    monkeypatch.setattr(
        streaming_mod,
        "generate_chat_completion",
        fake_generate_chat_completion,
        raising=False,
    )

    body_bytes = b""
    async with c.stream(
        "POST", f"/api/sessions/{sid}/chat", json={"prompt": "你好"}
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        async for chunk in r.aiter_bytes():
            body_bytes += chunk
    body = body_bytes.decode("utf-8")

    # SSE 至少包含两条 data: 行
    data_lines = [
        json.loads(line[len("data: "):])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    types = [d["type"] for d in data_lines]
    assert "assistant_text" in types
    assert "result" in types

    # 数据库回写了 claude_session_id 与 title
    from app.db.session import async_session
    from app.models import ChatSession
    async with async_session() as s:
        cs = await s.get(ChatSession, sid)
        assert cs.claude_session_id == "new-sid"
        assert cs.title == "问候回复"  # 首条 prompt 通过大模型生成语义标题


async def test_chat_title_falls_back_when_semantic_generation_fails(
    logged_in_client,
    monkeypatch,
):
    """标题生成失败不应影响聊天完成，保留本地截断兜底。"""
    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]
    monkeypatch.setenv("ANTHROPIC_PROVIDER_DEEPSEEK_AUTH_TOKEN", "title-token")

    async def fake_stream_chat(**kwargs):
        await kwargs["on_message"](
            {"type": "result", "session_id": "fallback-sid", "is_error": False}
        )
        return ChatRunSummary(
            session_id="fallback-sid",
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

    async def broken_generate_chat_completion(**kwargs):
        raise RuntimeError("title api down")

    import app.modules.sessions.streaming as streaming_mod

    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(
        streaming_mod,
        "generate_chat_completion",
        broken_generate_chat_completion,
        raising=False,
    )

    prompt = "请帮我制定一份面向新员工的安全培训方案\n要求包含考核"
    async with c.stream("POST", f"/api/sessions/{sid}/chat", json={"prompt": prompt}) as r:
        async for _ in r.aiter_bytes():
            pass

    from app.db.session import async_session
    from app.models import ChatSession

    async with async_session() as s:
        cs = await s.get(ChatSession, sid)
        assert cs.title == prompt.splitlines()[0][:30]


async def test_chat_sse_passes_model_settings_to_runner(logged_in_client, monkeypatch):
    """请求体中的模型设置应传递给 Claude runner。"""
    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]
    recorded = {}

    async def fake_stream_chat(**kwargs):
        recorded.update(kwargs)
        await kwargs["on_message"]({"type": "assistant_text", "text": "ok"})
        return ChatRunSummary(
            session_id="new-sid",
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

    import app.modules.sessions.streaming as streaming_mod
    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)

    async with c.stream(
        "POST",
        f"/api/sessions/{sid}/chat",
        json={
            "prompt": "你好",
            "model": "deepseek-v4-pro",
            "thinking_level": "medium",
        },
    ) as r:
        assert r.status_code == 200
        async for _ in r.aiter_bytes():
            pass

    assert recorded["model"] == "deepseek-v4-pro"
    assert recorded["thinking_level"] == "medium"


async def test_chat_sse_records_last_run_state(logged_in_client, monkeypatch):
    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]

    async def fake_stream_chat(*, prompt, claude_session_id, user_workspace, agent, on_message, stop_event=None):
        await on_message({"type": "assistant_text", "text": "第一段"})
        return ChatRunSummary(
            session_id="new-sid",
            is_error=False,
            stop_reason="end_turn",
            usage=None,
            model_usage=None,
            duration_ms=None,
            duration_api_ms=None,
            total_cost_usd=None,
            interrupted=False,
            error_message=None,
        )

    import app.modules.sessions.streaming as streaming_mod
    from app.modules.sessions.run_state import RunStatus

    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)

    async with c.stream("POST", f"/api/sessions/{sid}/chat", json={"prompt": "你好"}) as response:
        async for _ in response.aiter_bytes():
            pass

    snapshot = streaming_mod.run_state_store.snapshot(sid)
    assert snapshot is not None
    assert snapshot.status == RunStatus.COMPLETED
    assert [event.payload for event in snapshot.events] == [
        {"type": "user_text", "text": "你好"},
        {"type": "assistant_text", "text": "第一段"},
    ]


async def test_running_endpoint_returns_last_run_events(app_env, monkeypatch):
    sid = "sid-running"

    import app.modules.sessions.streaming as streaming_mod
    from app.modules.sessions.run_state import RunEvent

    streaming_mod.run_state_store.start(sid, "run-running")
    streaming_mod.run_state_store.append_event(
        sid,
        RunEvent(type="user_text", payload={"type": "user_text", "text": "你好"}),
        run_id="run-running",
    )
    streaming_mod.run_state_store.append_event(
        sid,
        RunEvent(type="assistant_text", payload={"type": "assistant_text", "text": "你好呀"}),
        run_id="run-running",
    )

    async with _running_route_client(
        monkeypatch,
        SimpleNamespace(id=sid, user_id=1),
    ) as c:
        response = await c.get(f"/api/sessions/{sid}/running")
    assert response.status_code == 200
    data = response.json()
    assert data["running"] is True
    assert data["run_id"] == "run-running"
    assert data["latest_seq"] == 2
    assert [item["event"]["type"] for item in data["events"]] == [
        "user_text",
        "assistant_text",
    ]


async def test_running_endpoint_unknown_session_returns_404(app_env, monkeypatch):
    async with _running_route_client(monkeypatch, None) as c:
        response = await c.get("/api/sessions/does-not-exist/running")
    assert response.status_code == 404


async def test_running_stream_replays_after_seq(app_env, monkeypatch):
    sid = "sid-running-stream"

    import app.modules.sessions.streaming as streaming_mod
    from app.modules.sessions.run_state import RunEvent, RunStatus

    streaming_mod.run_state_store.start(sid, "run-finished")
    streaming_mod.run_state_store.append_event(
        sid,
        RunEvent(type="user_text", payload={"type": "user_text", "text": "第一条"}),
        run_id="run-finished",
    )
    streaming_mod.run_state_store.append_event(
        sid,
        RunEvent(type="assistant_text", payload={"type": "assistant_text", "text": "第二条"}),
        run_id="run-finished",
    )
    streaming_mod.run_state_store.finish(sid, RunStatus.COMPLETED, run_id="run-finished")

    body_bytes = b""
    async with _running_route_client(
        monkeypatch,
        SimpleNamespace(id=sid, user_id=1),
    ) as c:
        async with c.stream("GET", f"/api/sessions/{sid}/running/stream?after_seq=1") as response:
            assert response.status_code == 200
            async for chunk in response.aiter_bytes():
                body_bytes += chunk

    data_lines = [
        json.loads(line[len("data: "):])
        for line in body_bytes.decode("utf-8").splitlines()
        if line.startswith("data: ")
    ]
    assert data_lines == [
        {"seq": 2, "event": {"type": "assistant_text", "text": "第二条"}},
    ]


async def test_running_stream_resets_stale_after_seq_for_new_run(app_env, monkeypatch):
    sid = "sid-running-new-run"

    import app.modules.sessions.streaming as streaming_mod
    from app.modules.sessions.run_state import RunEvent, RunStatus

    streaming_mod.run_state_store.start(sid, "old-run")
    for index in range(10):
        streaming_mod.run_state_store.append_event(
            sid,
            RunEvent(
                type="assistant_text",
                payload={"type": "assistant_text", "text": f"旧事件 {index}"},
            ),
            run_id="old-run",
        )
    streaming_mod.run_state_store.finish(sid, RunStatus.COMPLETED, run_id="old-run")

    streaming_mod.run_state_store.start(sid, "new-run")
    streaming_mod.run_state_store.append_event(
        sid,
        RunEvent(type="user_text", payload={"type": "user_text", "text": "新问题"}),
        run_id="new-run",
    )
    streaming_mod.run_state_store.append_event(
        sid,
        RunEvent(
            type="assistant_text",
            payload={"type": "assistant_text", "text": "新回答"},
        ),
        run_id="new-run",
    )
    streaming_mod.run_state_store.finish(sid, RunStatus.COMPLETED, run_id="new-run")

    body_bytes = b""
    async with _running_route_client(
        monkeypatch,
        SimpleNamespace(id=sid, user_id=1),
    ) as c:
        async with c.stream("GET", f"/api/sessions/{sid}/running/stream?after_seq=10") as response:
            assert response.status_code == 200
            async for chunk in response.aiter_bytes():
                body_bytes += chunk

    data_lines = [
        json.loads(line[len("data: "):])
        for line in body_bytes.decode("utf-8").splitlines()
        if line.startswith("data: ")
    ]
    assert data_lines == [
        {"seq": 1, "event": {"type": "user_text", "text": "新问题"}},
        {"seq": 2, "event": {"type": "assistant_text", "text": "新回答"}},
    ]


async def test_chat_sse_records_non_fatal_summary_error_message(logged_in_client, monkeypatch):
    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]

    async def fake_stream_chat(*, prompt, claude_session_id, user_workspace, agent, on_message, stop_event=None):
        return ChatRunSummary(
            session_id="new-sid",
            is_error=False,
            stop_reason="end_turn",
            usage=None,
            model_usage=None,
            duration_ms=None,
            duration_api_ms=None,
            total_cost_usd=None,
            interrupted=False,
            error_message="non-fatal",
        )

    import app.modules.sessions.streaming as streaming_mod
    from app.modules.sessions.run_state import RunStatus

    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)

    async with c.stream("POST", f"/api/sessions/{sid}/chat", json={"prompt": "你好"}) as response:
        async for _ in response.aiter_bytes():
            pass

    snapshot = streaming_mod.run_state_store.snapshot(sid)
    assert snapshot is not None
    assert snapshot.status == RunStatus.COMPLETED
    assert snapshot.error_message == "non-fatal"


async def test_chat_sse_records_failed_run_state(logged_in_client, monkeypatch):
    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]

    async def fake_stream_chat(**kwargs):
        raise RuntimeError("claude exploded")

    import app.modules.sessions.streaming as streaming_mod
    from app.modules.sessions.run_state import RunStatus

    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)

    async with c.stream("POST", f"/api/sessions/{sid}/chat", json={"prompt": "敏感内容"}) as response:
        async for _ in response.aiter_bytes():
            pass

    snapshot = streaming_mod.run_state_store.snapshot(sid)
    assert snapshot is not None
    assert snapshot.status == RunStatus.FAILED
    assert snapshot.events[-1].type == "error"
    assert snapshot.events[-1].message == "claude exploded"


async def test_chat_sse_ignores_stale_first_run_events(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.modules.sessions.run_state import RunStatus

    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def fake_stream_chat(*, prompt, claude_session_id, user_workspace, agent, on_message, stop_event=None):
        if prompt == "第一轮":
            first_started.set()
            await release_first.wait()
            await on_message({"type": "assistant_text", "text": "迟到第一轮"})
            return ChatRunSummary(
                session_id="old-sid",
                is_error=True,
                stop_reason="error",
                usage=None,
                model_usage=None,
                duration_ms=None,
                duration_api_ms=None,
                total_cost_usd=None,
                interrupted=False,
                error_message="old failed",
            )

        await on_message({"type": "assistant_text", "text": "第二轮"})
        return ChatRunSummary(
            session_id="new-sid",
            is_error=False,
            stop_reason="end_turn",
            usage=None,
            model_usage=None,
            duration_ms=None,
            duration_api_ms=None,
            total_cost_usd=None,
            interrupted=False,
            error_message=None,
        )

    import app.modules.sessions.streaming as streaming_mod

    async def fake_persist_usage_event(**kwargs):
        return None

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, model, session_id):
            return SimpleNamespace(
                claude_session_id=None,
                title="",
                updated_at=None,
            )

        async def commit(self):
            pass

    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(streaming_mod, "async_session", lambda: FakeSession())
    monkeypatch.setattr(streaming_mod, "persist_usage_event", fake_persist_usage_event)
    monkeypatch.setattr(streaming_mod, "user_workspace", lambda username: tmp_path)

    chat = SimpleNamespace(id="sid-race", claude_session_id=None)
    user = SimpleNamespace(username="race-user")

    first_response = await streaming_mod.stream_session_chat(chat, user, "第一轮")
    await asyncio.wait_for(first_started.wait(), timeout=1)

    second_response = await streaming_mod.stream_session_chat(chat, user, "第二轮")
    async for _ in second_response.body_iterator:
        pass

    release_first.set()
    async for _ in first_response.body_iterator:
        pass

    snapshot = streaming_mod.run_state_store.snapshot("sid-race")
    assert snapshot is not None
    assert snapshot.status == RunStatus.COMPLETED
    assert [event.payload for event in snapshot.events] == [
        {"type": "user_text", "text": "第二轮"},
        {"type": "assistant_text", "text": "第二轮"},
    ]
    assert snapshot.error_message is None


async def test_chat_sse_skips_stale_run_metadata_write(app_env, monkeypatch):
    """旧 run 晚完成时不能覆盖新 run 已写入的 Claude session id。"""
    from app.db.session import async_session
    from app.models import ChatSession, User

    async with async_session() as session:
        user = User(username="race-metadata-user", password_hash="x", role="user")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        chat = ChatSession(id="sid-metadata-race", user_id=user.id, title="旧标题")
        session.add(chat)
        await session.commit()
        await session.refresh(chat)

    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def fake_stream_chat(*, prompt, claude_session_id, user_workspace, agent, on_message, stop_event=None):
        if prompt == "第一轮":
            first_started.set()
            await release_first.wait()
            return ChatRunSummary(
                session_id="first-sid",
                is_error=False,
                stop_reason="end_turn",
                usage=None,
                model_usage=None,
                duration_ms=None,
                duration_api_ms=None,
                total_cost_usd=None,
                interrupted=False,
                error_message=None,
            )

        return ChatRunSummary(
            session_id="second-sid",
            is_error=False,
            stop_reason="end_turn",
            usage=None,
            model_usage=None,
            duration_ms=None,
            duration_api_ms=None,
            total_cost_usd=None,
            interrupted=False,
            error_message=None,
        )

    import app.modules.sessions.streaming as streaming_mod

    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)

    first_response = await streaming_mod.stream_session_chat(chat, user, "第一轮")
    await asyncio.wait_for(first_started.wait(), timeout=1)

    second_response = await streaming_mod.stream_session_chat(chat, user, "第二轮")
    async for _ in second_response.body_iterator:
        pass

    async with async_session() as session:
        refreshed = await session.get(ChatSession, "sid-metadata-race")
        assert refreshed.claude_session_id == "second-sid"

    release_first.set()
    async for _ in first_response.body_iterator:
        pass

    async with async_session() as session:
        refreshed = await session.get(ChatSession, "sid-metadata-race")
        assert refreshed.claude_session_id == "second-sid"


async def test_chat_sse_blocks_new_run_during_current_metadata_commit(monkeypatch, tmp_path):
    """旧 run 已通过当前性校验后，新 run 不能插入到提交窗口内。"""
    from types import SimpleNamespace

    import app.modules.sessions.streaming as streaming_mod

    record = SimpleNamespace(claude_session_id=None, title="旧标题", updated_at=None)
    first_get_entered = asyncio.Event()
    release_first_get = asyncio.Event()
    get_calls = 0

    async def fake_stream_chat(*, prompt, claude_session_id, user_workspace, agent, on_message, stop_event=None):
        return ChatRunSummary(
            session_id="first-sid" if prompt == "第一轮" else "second-sid",
            is_error=False,
            stop_reason="end_turn",
            usage=None,
            model_usage=None,
            duration_ms=None,
            duration_api_ms=None,
            total_cost_usd=None,
            interrupted=False,
            error_message=None,
        )

    async def fake_persist_usage_event(**kwargs):
        return None

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, model, session_id):
            nonlocal get_calls
            get_calls += 1
            if get_calls == 1:
                first_get_entered.set()
                await release_first_get.wait()
            return record

        async def commit(self):
            pass

    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(streaming_mod, "async_session", lambda: FakeSession())
    monkeypatch.setattr(streaming_mod, "persist_usage_event", fake_persist_usage_event)
    monkeypatch.setattr(streaming_mod, "user_workspace", lambda username: tmp_path)

    chat = SimpleNamespace(id="sid-metadata-window", claude_session_id=None)
    user = SimpleNamespace(username="metadata-window-user")

    first_response = await streaming_mod.stream_session_chat(chat, user, "第一轮")
    await asyncio.wait_for(first_get_entered.wait(), timeout=1)

    second_response_task = asyncio.create_task(
        streaming_mod.stream_session_chat(chat, user, "第二轮")
    )
    await asyncio.sleep(0)

    release_first_get.set()
    async for _ in first_response.body_iterator:
        pass

    second_response = await asyncio.wait_for(second_response_task, timeout=1)
    async for _ in second_response.body_iterator:
        pass

    assert record.claude_session_id == "second-sid"


async def test_chat_uses_existing_session_id(logged_in_client, monkeypatch):
    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]

    # 预置 claude_session_id
    from app.db.session import async_session
    from app.models import ChatSession
    async with async_session() as s:
        cs = await s.get(ChatSession, sid)
        cs.claude_session_id = "existing"
        cs.title = "已有标题"
        await s.commit()

    captured = {}
    async def fake_stream_chat(*, prompt, claude_session_id, user_workspace, agent, on_message, stop_event=None):
        captured["claude_session_id"] = claude_session_id
        await on_message({"type": "result", "session_id": "existing", "is_error": False, "stop_reason": None})
        return ChatRunSummary(
            session_id="existing",
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

    import app.modules.sessions.streaming as streaming_mod
    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)

    async with c.stream(
        "POST", f"/api/sessions/{sid}/chat", json={"prompt": "再问一句"}
    ) as r:
        async for _ in r.aiter_bytes():
            pass

    assert captured["claude_session_id"] == "existing"
    async with async_session() as s:
        cs = await s.get(ChatSession, sid)
        assert cs.title == "已有标题"  # 非首条消息不改标题


async def test_chat_on_unknown_session_returns_404(logged_in_client):
    c = logged_in_client
    async with c.stream(
        "POST", "/api/sessions/does-not-exist/chat", json={"prompt": "x"}
    ) as r:
        assert r.status_code == 404


async def test_chat_stream_exception_is_logged(monkeypatch, tmp_path, caplog):
    import logging
    from types import SimpleNamespace

    import app.modules.sessions.streaming as streaming_mod

    async def fake_stream_chat(**kwargs):
        raise RuntimeError("claude exploded")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, model, session_id):
            return SimpleNamespace(
                claude_session_id=None,
                title="",
                updated_at=None,
            )

        async def commit(self):
            pass

    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(streaming_mod, "async_session", lambda: FakeSession())
    monkeypatch.setattr(streaming_mod, "user_workspace", lambda username: tmp_path)

    with caplog.at_level(logging.ERROR, logger=streaming_mod.__name__):
        body_bytes = b""
        response = await streaming_mod.stream_session_chat(
            SimpleNamespace(id="session-1", claude_session_id=None),
            SimpleNamespace(username="alice"),
            "hello",
        )
        async for chunk in response.body_iterator:
            body_bytes += chunk.encode("utf-8") if isinstance(chunk, str) else chunk

    assert "claude exploded" in body_bytes.decode("utf-8")
    assert any(
        record.levelno == logging.ERROR
        and record.exc_info
        and "Claude stream failed" in record.getMessage()
        for record in caplog.records
    )
    assert "hello" not in caplog.text


async def test_chat_sse_persists_usage_event(logged_in_client, monkeypatch):
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
    from sqlalchemy.orm import selectinload

    async with async_session() as session:
        event = (await session.execute(
            select(UsageEvent).options(selectinload(UsageEvent.resources))
        )).scalar_one()
        assert event.session_id == sid
        assert event.agent_name == "统计助手"
        assert event.input_tokens == 11
        assert event.output_tokens == 22
        assert event.total_tokens == 33
        assert event.status == "success"
        assert event.resources[0].resource_name == "demo-skill"


async def test_chat_sse_persists_usage_when_client_disconnects(app_env, monkeypatch):
    """客户端断开 SSE 后，已完成的 Claude 调用仍应落 usage。"""
    from app.db.session import async_session
    from app.models import ChatSession, UsageEvent, User
    from sqlalchemy import select

    async with async_session() as session:
        user = User(username="disconnect-user", password_hash="x", role="user")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        chat = ChatSession(id="sid-disconnect", user_id=user.id, title="t")
        session.add(chat)
        await session.commit()
        await session.refresh(chat)

    async def fake_stream_chat(*, prompt, claude_session_id, user_workspace, agent, on_message, stop_event=None):
        await on_message({"type": "assistant_text", "text": "第一段"})
        return ChatRunSummary(
            session_id="new-disconnect-sid",
            is_error=False,
            stop_reason="end_turn",
            usage={"input_tokens": 3, "output_tokens": 4},
            model_usage=None,
            duration_ms=50,
            duration_api_ms=40,
            total_cost_usd=None,
            interrupted=False,
            error_message=None,
        )

    import app.modules.sessions.streaming as streaming_mod
    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)

    response = await streaming_mod.stream_session_chat(chat, user, "断开测试")
    first_chunk = await anext(response.body_iterator)
    assert "第一段" in (first_chunk.decode("utf-8") if isinstance(first_chunk, bytes) else first_chunk)
    await response.body_iterator.aclose()

    event = None
    refreshed = None
    for _ in range(20):
        async with async_session() as session:
            event = (await session.execute(select(UsageEvent))).scalar_one_or_none()
            refreshed = await session.get(ChatSession, "sid-disconnect")
        if event is not None and refreshed and refreshed.claude_session_id == "new-disconnect-sid":
            break
        await asyncio.sleep(0.05)

    assert event is not None
    assert refreshed is not None
    assert event.session_id == "sid-disconnect"
    assert event.total_tokens == 7
    assert refreshed.claude_session_id == "new-disconnect-sid"


async def test_chat_disconnect_keeps_active_stop_until_runner_finishes(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import app.modules.sessions.streaming as streaming_mod

    started = asyncio.Event()
    captured_stop_event = None

    async def fake_stream_chat(*, prompt, claude_session_id, user_workspace, agent, on_message, stop_event=None):
        nonlocal captured_stop_event
        captured_stop_event = stop_event
        await on_message({"type": "assistant_text", "text": "第一段"})
        started.set()
        await stop_event.wait()
        return ChatRunSummary(
            session_id="stopped-sid",
            is_error=False,
            stop_reason="stop",
            usage=None,
            model_usage=None,
            duration_ms=None,
            duration_api_ms=None,
            total_cost_usd=None,
            interrupted=True,
            error_message=None,
        )

    async def fake_persist_usage_event(**kwargs):
        return None

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, model, session_id):
            return SimpleNamespace(
                claude_session_id=None,
                title="",
                updated_at=None,
            )

        async def commit(self):
            pass

    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(streaming_mod, "async_session", lambda: FakeSession())
    monkeypatch.setattr(streaming_mod, "persist_usage_event", fake_persist_usage_event)
    monkeypatch.setattr(streaming_mod, "user_workspace", lambda username: tmp_path)

    response = await streaming_mod.stream_session_chat(
        SimpleNamespace(id="sid-disconnect-stop", claude_session_id=None),
        SimpleNamespace(username="stop-user"),
        "断开测试",
    )
    await anext(response.body_iterator)
    await asyncio.wait_for(started.wait(), timeout=1)

    close_task = asyncio.create_task(response.body_iterator.aclose())
    await asyncio.sleep(0)

    try:
        result = await streaming_mod.stop_session("sid-disconnect-stop")
        assert result == {"stopped": True}
    finally:
        if captured_stop_event is not None and not captured_stop_event.is_set():
            captured_stop_event.set()
        await asyncio.wait_for(close_task, timeout=1)


async def test_chat_runner_continues_when_sse_consumer_is_cancelled(monkeypatch, tmp_path):
    """SSE 消费任务被取消时，后台 Claude runner 仍应继续完成。"""
    from types import SimpleNamespace

    from app.modules.sessions.run_state import RunStatus

    import app.modules.sessions.streaming as streaming_mod

    first_chunk_sent = asyncio.Event()
    release_runner = asyncio.Event()

    async def fake_stream_chat(*, prompt, claude_session_id, user_workspace, agent, on_message, stop_event=None):
        await on_message({"type": "assistant_text", "text": "第一段"})
        first_chunk_sent.set()
        await release_runner.wait()
        await on_message({"type": "assistant_text", "text": "第二段"})
        return ChatRunSummary(
            session_id="completed-after-disconnect",
            is_error=False,
            stop_reason="end_turn",
            usage=None,
            model_usage=None,
            duration_ms=None,
            duration_api_ms=None,
            total_cost_usd=None,
            interrupted=False,
            error_message=None,
        )

    async def fake_persist_usage_event(**kwargs):
        return None

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, model, session_id):
            return SimpleNamespace(claude_session_id=None, title="", updated_at=None)

        async def commit(self):
            pass

    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(streaming_mod, "async_session", lambda: FakeSession())
    monkeypatch.setattr(streaming_mod, "persist_usage_event", fake_persist_usage_event)
    monkeypatch.setattr(streaming_mod, "user_workspace", lambda username: tmp_path)

    response = await streaming_mod.stream_session_chat(
        SimpleNamespace(id="sid-cancelled-consumer", claude_session_id=None),
        SimpleNamespace(username="cancel-user"),
        "断开测试",
    )

    async def consume_stream():
        async for _ in response.body_iterator:
            await first_chunk_sent.wait()

    consumer = asyncio.create_task(consume_stream())
    await asyncio.wait_for(first_chunk_sent.wait(), timeout=1)
    consumer.cancel()
    try:
        await asyncio.wait_for(consumer, timeout=0.1)
    except asyncio.CancelledError:
        pass
    except TimeoutError as exc:
        raise AssertionError("SSE 消费者取消不应等待后台 runner 完成") from exc

    snapshot = streaming_mod.run_state_store.snapshot("sid-cancelled-consumer")
    assert snapshot is not None
    assert snapshot.status == RunStatus.RUNNING

    release_runner.set()
    for _ in range(20):
        snapshot = streaming_mod.run_state_store.snapshot("sid-cancelled-consumer")
        if snapshot is not None and snapshot.status == RunStatus.COMPLETED:
            break
        await asyncio.sleep(0.05)

    snapshot = streaming_mod.run_state_store.snapshot("sid-cancelled-consumer")
    assert snapshot is not None
    assert snapshot.status == RunStatus.COMPLETED
    assert [event.payload for event in snapshot.events] == [
        {"type": "user_text", "text": "断开测试"},
        {"type": "assistant_text", "text": "第一段"},
        {"type": "assistant_text", "text": "第二段"},
    ]


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
