import pytest


@pytest.mark.asyncio
async def test_team_session_visibility_depends_on_shared_flag(logged_in_client, other_logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "团队资料"})
    space_id = created.json()["id"]
    other = (await other_logged_in_client.get("/api/me")).json()
    await logged_in_client.post(f"/api/team-spaces/{space_id}/members", json={"user_id": other["id"], "role": "editor"})

    private_session = await logged_in_client.post(
        "/api/sessions",
        json={"agent_id": None, "workspace_kind": "team", "team_space_id": space_id},
    )
    assert private_session.status_code == 200
    shared_session = await logged_in_client.post(
        "/api/sessions",
        json={
            "agent_id": None,
            "workspace_kind": "team",
            "team_space_id": space_id,
            "is_shared": True,
        },
    )
    assert shared_session.status_code == 200

    listed = await other_logged_in_client.get(f"/api/sessions?workspace_kind=team&team_space_id={space_id}")
    mine_only = await other_logged_in_client.get(
        f"/api/sessions?workspace_kind=team&team_space_id={space_id}&mine_only=true",
    )

    assert listed.status_code == 200
    assert mine_only.status_code == 200
    ids = [item["id"] for item in listed.json()]
    assert private_session.json()["id"] not in ids
    assert shared_session.json()["id"] in ids
    assert mine_only.json() == []
    assert shared_session.json()["is_shared"] is True


@pytest.mark.asyncio
async def test_all_workspace_sessions_include_shared_team_sessions(logged_in_client, other_logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "团队资料"})
    space_id = created.json()["id"]
    other = (await other_logged_in_client.get("/api/me")).json()
    await logged_in_client.post(f"/api/team-spaces/{space_id}/members", json={"user_id": other["id"], "role": "editor"})
    personal = await other_logged_in_client.post(
        "/api/sessions",
        json={"agent_id": None, "workspace_kind": "personal", "title": "自己的个人会话"},
    )
    shared_team = await logged_in_client.post(
        "/api/sessions",
        json={
            "agent_id": None,
            "workspace_kind": "team",
            "team_space_id": space_id,
            "is_shared": True,
            "title": "共享团队会话",
        },
    )
    private_team = await logged_in_client.post(
        "/api/sessions",
        json={
            "agent_id": None,
            "workspace_kind": "team",
            "team_space_id": space_id,
            "title": "未共享团队会话",
        },
    )

    listed = await other_logged_in_client.get("/api/sessions?workspace_kind=all&limit=20")

    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()]
    assert personal.json()["id"] in ids
    assert shared_team.json()["id"] in ids
    assert private_team.json()["id"] not in ids


@pytest.mark.asyncio
async def test_sessions_support_pagination_and_agent_filter(logged_in_client):
    from app.db.session import async_session
    from app.models import Agent

    async with async_session() as session:
        agent = Agent(name="数据分析", code="data", system_prompt="x")
        other_agent = Agent(name="写作助手", code="writer", system_prompt="x")
        session.add_all([agent, other_agent])
        await session.commit()
        await session.refresh(agent)
        await session.refresh(other_agent)

    for idx in range(12):
        agent_id = agent.id if idx % 2 == 0 else other_agent.id
        created = await logged_in_client.post(
            "/api/sessions",
            json={"agent_id": agent_id, "workspace_kind": "personal", "title": f"会话 {idx}"},
        )
        assert created.status_code == 200

    first_page = await logged_in_client.get("/api/sessions?limit=10&offset=0")
    second_page = await logged_in_client.get("/api/sessions?limit=10&offset=10")
    filtered = await logged_in_client.get(f"/api/sessions?agent_id={agent.id}&limit=10")
    all_workspaces = await logged_in_client.get("/api/sessions?workspace_kind=all&limit=20")

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert filtered.status_code == 200
    assert all_workspaces.status_code == 200
    assert len(first_page.json()) == 10
    assert len(second_page.json()) == 2
    assert {item["agent_id"] for item in filtered.json()} == {agent.id}
    assert len(all_workspaces.json()) == 12
