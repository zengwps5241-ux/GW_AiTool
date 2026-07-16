async def test_create_list_rename_delete(logged_in_client):
    c = logged_in_client

    # 起初列表为空
    res = await c.get("/api/sessions")
    assert res.status_code == 200
    assert res.json() == []

    # 创建一个
    res = await c.post("/api/sessions", json={})
    assert res.status_code == 200
    sid = res.json()["id"]
    assert res.json()["title"] == "新会话"

    # 列表中能看到
    res = await c.get("/api/sessions")
    assert len(res.json()) == 1
    assert res.json()[0]["id"] == sid

    # 重命名
    res = await c.patch(f"/api/sessions/{sid}", json={"title": "我的对话"})
    assert res.status_code == 200
    assert res.json()["title"] == "我的对话"

    # 删除
    res = await c.delete(f"/api/sessions/{sid}")
    assert res.status_code == 204

    # 列表为空
    res = await c.get("/api/sessions")
    assert res.json() == []


async def test_session_isolation_between_users(logged_in_client, other_logged_in_client):
    """两个自建登录用户之间的会话隔离（V2.2 认证重构后改用自建注册登录）。"""
    alice = logged_in_client
    bob = other_logged_in_client

    # alice 创建会话
    sid = (await alice.post("/api/sessions", json={})).json()["id"]
    assert [s["id"] for s in (await alice.get("/api/sessions")).json()] == [sid]

    # bob 看不到 alice 的会话
    assert (await bob.get("/api/sessions")).json() == []
    # 也不能改/删（归属校验返回 404）
    assert (await bob.patch(f"/api/sessions/{sid}", json={"title": "x"})).status_code == 404
    assert (await bob.delete(f"/api/sessions/{sid}")).status_code == 404


async def test_delete_triggers_remove_session(logged_in_client, monkeypatch):
    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]

    # 给会话写一个 fake claude_session_id
    from app.db.session import async_session
    from app.models import ChatSession
    async with async_session() as s:
        cs = await s.get(ChatSession, sid)
        cs.claude_session_id = "fake-sid"
        await s.commit()

    calls = []
    from app.api.routes import sessions as routes

    async def fake_remove(sid_, ws, *, agent=None):
        calls.append((sid_, str(ws)))

    monkeypatch.setattr(routes, "remove_session", fake_remove)

    res = await c.delete(f"/api/sessions/{sid}")
    assert res.status_code == 204
    assert calls and calls[0][0] == "fake-sid"
    # 路径分隔符跨平台统一为 POSIX 再断言后缀（Windows 为反斜杠）。
    assert calls[0][1].replace("\\", "/").endswith("user_workspaces/alice")


async def test_unauthenticated_blocked(client):
    assert (await client.get("/api/sessions")).status_code == 401
    assert (await client.post("/api/sessions", json={})).status_code == 401
