import pytest


async def _create_agent_record(name: str, code: str, skills: str = "") -> int:
    from app.db.session import async_session
    from app.models import Agent

    async with async_session() as session:
        agent = Agent(name=name, code=code, skills=skills)
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        return agent.id


async def test_create_session_without_agent(logged_in_client):
    c = logged_in_client
    r = await c.post("/api/sessions", json={"title": "测试会话"})
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "测试会话"
    assert data["agent_id"] is None
    assert data["agent_name"] is None


async def test_create_session_with_agent(logged_in_client):
    c = logged_in_client
    agent_id = await _create_agent_record("测试智能体", "test-agent", "a,b")

    # 创建会话时绑定智能体
    r = await c.post("/api/sessions", json={"title": "带智能体会话", "agent_id": agent_id})
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "带智能体会话"
    assert data["agent_id"] == agent_id
    assert data["agent_name"] == "测试智能体"


async def test_list_sessions_includes_agent_name(logged_in_client):
    c = logged_in_client
    agent_id = await _create_agent_record("列表智能体", "list-agent")

    await c.post("/api/sessions", json={"title": "列表测试", "agent_id": agent_id})

    r = await c.get("/api/sessions")
    assert r.status_code == 200
    sessions = r.json()
    sess = next((s for s in sessions if s["title"] == "列表测试"), None)
    assert sess is not None
    assert sess["agent_id"] == agent_id
    assert sess["agent_name"] == "列表智能体"
