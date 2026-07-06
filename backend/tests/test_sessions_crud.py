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


async def test_session_isolation_between_users(client, monkeypatch, app_env):
    """两个企微用户之间的会话隔离。"""
    from unittest.mock import patch, AsyncMock
    from app.modules.auth import wechat_work

    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")
    monkeypatch.setenv("WECHAT_WORK_LOGIN_MODE", "sso")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    # alice 企微登录
    with patch("app.api.routes.auth.secrets.token_urlsafe", return_value="alice_state"):
        await client.get("/api/auth/wechat-work/authorize", follow_redirects=False)
    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "get_user_id_by_code", new=AsyncMock(return_value="alice")), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": "alice", "name": "Alice", "department": [], "position": None,
             "mobile": None, "email": None, "avatar": None,
         })), \
         patch.object(wechat_work, "get_department_list", new=AsyncMock(return_value=[])):
        await client.get("/api/auth/wechat-work/callback?code=c1&state=alice_state", follow_redirects=False)

    # alice 创建会话
    sid = (await client.post("/api/sessions", json={})).json()["id"]

    # 切换到 bob
    await client.post("/api/auth/logout")

    # bob 企微登录
    with patch("app.api.routes.auth.secrets.token_urlsafe", return_value="bob_state"):
        await client.get("/api/auth/wechat-work/authorize", follow_redirects=False)
    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "get_user_id_by_code", new=AsyncMock(return_value="bob")), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": "bob", "name": "Bob", "department": [], "position": None,
             "mobile": None, "email": None, "avatar": None,
         })), \
         patch.object(wechat_work, "get_department_list", new=AsyncMock(return_value=[])):
        await client.get("/api/auth/wechat-work/callback?code=c2&state=bob_state", follow_redirects=False)

    # bob 看不到 alice 的会话
    assert (await client.get("/api/sessions")).json() == []
    # 也不能改/删
    assert (await client.patch(f"/api/sessions/{sid}", json={"title": "x"})).status_code == 404
    assert (await client.delete(f"/api/sessions/{sid}")).status_code == 404


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
    assert calls[0][1].endswith("user_workspaces/alice")


async def test_unauthenticated_blocked(client):
    assert (await client.get("/api/sessions")).status_code == 401
    assert (await client.post("/api/sessions", json={})).status_code == 401
