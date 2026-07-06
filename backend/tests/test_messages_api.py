import pytest


async def test_messages_empty_for_new_session(logged_in_client):
    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]
    res = await c.get(f"/api/sessions/{sid}/messages")
    assert res.status_code == 200
    assert res.json() == []


async def test_messages_calls_load_history(logged_in_client, monkeypatch):
    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]

    # 直接在 DB 把 claude_session_id 改成有值
    from app.db.session import async_session
    from app.models import ChatSession
    async with async_session() as s:
        cs = await s.get(ChatSession, sid)
        cs.claude_session_id = "fake-sid"
        await s.commit()

    captured = {}
    async def fake_load(sid_arg, ws, *, agent=None):
        captured["sid"] = sid_arg
        captured["ws"] = str(ws)
        return [{"type": "assistant_text", "text": "hi"}]

    from app.api.routes import sessions as routes
    monkeypatch.setattr(routes, "load_history", fake_load)

    res = await c.get(f"/api/sessions/{sid}/messages")
    assert res.status_code == 200
    assert res.json() == [{"type": "assistant_text", "text": "hi"}]
    assert captured["sid"] == "fake-sid"
    assert captured["ws"].endswith("user_workspaces/alice")
