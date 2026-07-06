import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_team_space_models_create_owner_member(db_session, test_user):
    from app.models import TeamSpace, TeamSpaceMember

    space = TeamSpace(
        name="客户试点资料",
        description="试点材料",
        owner_user_id=test_user.id,
        created_by_user_id=test_user.id,
    )
    db_session.add(space)
    await db_session.flush()
    db_session.add(
        TeamSpaceMember(
            space_id=space.id,
            user_id=test_user.id,
            role="editor",
            added_by_user_id=test_user.id,
        )
    )
    await db_session.commit()

    saved = (await db_session.execute(select(TeamSpace))).scalar_one()
    member = (await db_session.execute(select(TeamSpaceMember))).scalar_one()
    assert saved.name == "客户试点资料"
    assert saved.owner_user_id == test_user.id
    assert member.role == "editor"


@pytest.mark.asyncio
async def test_create_space_auto_adds_owner_editor(logged_in_client):
    r = await logged_in_client.post("/api/team-spaces", json={"name": "客户试点资料", "description": "试点"})
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "客户试点资料"
    assert data["member_role"] == "editor"
    assert data["is_owner"] is True
    assert data["can_write"] is True


@pytest.mark.asyncio
async def test_list_detail_and_members_for_team_spaces(logged_in_client):
    created = await logged_in_client.post(
        "/api/team-spaces",
        json={"name": "客户试点资料", "description": "试点"},
    )
    assert created.status_code == 200
    space_id = created.json()["id"]

    listed = await logged_in_client.get("/api/team-spaces")
    assert listed.status_code == 200
    items = listed.json()
    assert [item["id"] for item in items] == [space_id]
    assert items[0]["name"] == "客户试点资料"
    assert items[0]["member_role"] == "editor"

    detail = await logged_in_client.get(f"/api/team-spaces/{space_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == space_id
    assert detail.json()["can_write"] is True

    members = await logged_in_client.get(f"/api/team-spaces/{space_id}/members")
    assert members.status_code == 200
    member_items = members.json()
    assert len(member_items) == 1
    assert member_items[0]["role"] == "editor"
    assert member_items[0]["is_owner"] is True


@pytest.mark.asyncio
async def test_owner_searches_team_member_candidates_by_name(logged_in_client, other_logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "共享材料"})
    space_id = created.json()["id"]

    searched = await logged_in_client.get(
        f"/api/team-spaces/{space_id}/members/search",
        params={"keyword": "Bo"},
    )

    assert searched.status_code == 200
    items = searched.json()
    assert len(items) == 1
    assert items[0]["username"] == "bob"
    assert items[0]["display_name"] == "Bob"
    assert items[0]["is_member"] is False


@pytest.mark.asyncio
async def test_non_owner_cannot_search_team_member_candidates(logged_in_client, other_logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "共享材料"})
    space_id = created.json()["id"]
    me = (await other_logged_in_client.get("/api/me")).json()
    await logged_in_client.post(
        f"/api/team-spaces/{space_id}/members",
        json={"user_id": me["id"], "role": "reader"},
    )

    searched = await other_logged_in_client.get(
        f"/api/team-spaces/{space_id}/members/search",
        params={"keyword": "Ali"},
    )

    assert searched.status_code == 403


@pytest.mark.asyncio
async def test_owner_updates_team_member_role(logged_in_client, other_logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "共享材料"})
    space_id = created.json()["id"]
    other_user = (await other_logged_in_client.get("/api/me")).json()
    added = await logged_in_client.post(
        f"/api/team-spaces/{space_id}/members",
        json={"user_id": other_user["id"], "role": "reader"},
    )
    member_id = added.json()["id"]

    updated = await logged_in_client.patch(
        f"/api/team-spaces/{space_id}/members/{member_id}",
        json={"role": "editor"},
    )

    assert updated.status_code == 200
    assert updated.json()["role"] == "editor"
    members = (await logged_in_client.get(f"/api/team-spaces/{space_id}/members")).json()
    bob = next(member for member in members if member["user_id"] == other_user["id"])
    assert bob["role"] == "editor"


@pytest.mark.asyncio
async def test_owner_cannot_downgrade_self_by_readding_member(logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "共享材料"})
    space_id = created.json()["id"]
    owner_id = created.json()["owner_user_id"]

    updated = await logged_in_client.post(
        f"/api/team-spaces/{space_id}/members",
        json={"user_id": owner_id, "role": "reader"},
    )

    assert updated.status_code == 400
    members = (await logged_in_client.get(f"/api/team-spaces/{space_id}/members")).json()
    owner = next(member for member in members if member["user_id"] == owner_id)
    assert owner["role"] == "editor"


@pytest.mark.asyncio
async def test_owner_removes_team_member(logged_in_client, other_logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "共享材料"})
    space_id = created.json()["id"]
    other_user = (await other_logged_in_client.get("/api/me")).json()
    added = await logged_in_client.post(
        f"/api/team-spaces/{space_id}/members",
        json={"user_id": other_user["id"], "role": "reader"},
    )

    removed = await logged_in_client.delete(
        f"/api/team-spaces/{space_id}/members/{added.json()['id']}",
    )

    assert removed.status_code == 204
    members = (await logged_in_client.get(f"/api/team-spaces/{space_id}/members")).json()
    assert [member["user_id"] for member in members] == [created.json()["owner_user_id"]]
    detail = await other_logged_in_client.get(f"/api/team-spaces/{space_id}")
    assert detail.status_code == 404


@pytest.mark.asyncio
async def test_owner_transfers_team_space_ownership(logged_in_client, other_logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "共享材料"})
    space_id = created.json()["id"]
    old_owner_id = created.json()["owner_user_id"]
    other_user = (await other_logged_in_client.get("/api/me")).json()
    await logged_in_client.post(
        f"/api/team-spaces/{space_id}/members",
        json={"user_id": other_user["id"], "role": "reader"},
    )

    transferred = await logged_in_client.post(
        f"/api/team-spaces/{space_id}/owner",
        json={"user_id": other_user["id"]},
    )

    assert transferred.status_code == 200
    assert transferred.json()["owner_user_id"] == other_user["id"]
    assert transferred.json()["is_owner"] is False
    new_owner_view = await other_logged_in_client.get(f"/api/team-spaces/{space_id}")
    assert new_owner_view.status_code == 200
    assert new_owner_view.json()["is_owner"] is True
    assert new_owner_view.json()["member_role"] == "editor"
    members = (await other_logged_in_client.get(f"/api/team-spaces/{space_id}/members")).json()
    assert {member["user_id"] for member in members} == {old_owner_id, other_user["id"]}


@pytest.mark.asyncio
async def test_team_member_can_leave_but_owner_cannot(logged_in_client, other_logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "共享材料"})
    space_id = created.json()["id"]
    other_user = (await other_logged_in_client.get("/api/me")).json()
    await logged_in_client.post(
        f"/api/team-spaces/{space_id}/members",
        json={"user_id": other_user["id"], "role": "reader"},
    )

    owner_leave = await logged_in_client.post(f"/api/team-spaces/{space_id}/leave")
    member_leave = await other_logged_in_client.post(f"/api/team-spaces/{space_id}/leave")

    assert owner_leave.status_code == 400
    assert member_leave.status_code == 204
    members = (await logged_in_client.get(f"/api/team-spaces/{space_id}/members")).json()
    assert [member["user_id"] for member in members] == [created.json()["owner_user_id"]]


@pytest.mark.asyncio
async def test_non_owner_cannot_manage_team_members(logged_in_client, other_logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "共享材料"})
    space_id = created.json()["id"]
    other_user = (await other_logged_in_client.get("/api/me")).json()
    added = await logged_in_client.post(
        f"/api/team-spaces/{space_id}/members",
        json={"user_id": other_user["id"], "role": "reader"},
    )
    member_id = added.json()["id"]

    update = await other_logged_in_client.patch(
        f"/api/team-spaces/{space_id}/members/{member_id}",
        json={"role": "editor"},
    )
    remove = await other_logged_in_client.delete(f"/api/team-spaces/{space_id}/members/{member_id}")
    transfer = await other_logged_in_client.post(
        f"/api/team-spaces/{space_id}/owner",
        json={"user_id": other_user["id"]},
    )

    assert update.status_code == 403
    assert remove.status_code == 403
    assert transfer.status_code == 403


@pytest.mark.asyncio
async def test_reader_cannot_lock_team_space(logged_in_client, other_logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "共享材料"})
    space_id = created.json()["id"]
    me = (await other_logged_in_client.get("/api/me")).json()
    add = await logged_in_client.post(
        f"/api/team-spaces/{space_id}/members",
        json={"user_id": me["id"], "role": "reader"},
    )
    assert add.status_code == 200

    locked = await other_logged_in_client.post(f"/api/team-spaces/{space_id}/lock", json={"note": "整理"})

    assert locked.status_code == 403
    assert "只读成员" in locked.json()["detail"]
