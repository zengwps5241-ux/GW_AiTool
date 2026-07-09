"""项目管理 API 测试（M1.3.6 / M1.3.7 / M1.3.8）。

覆盖：
- 创建项目（自动生成 Agent + 创建者成为 Owner）
- 列表/详情的项目级隔离（require_project_member / owner）
- admin 越权访问
- 成员管理（邀请/移除 deputy、单 Owner 不变式、deputy 不可管理）
- 部门授权（授权后部门成员自动获得访问权；撤销后失效）
- 删除项目（级联清理 + 删除项目 Agent）
"""

import pytest


# ─── 辅助 ──────────────────────────────────────────────────────


async def _me(client):
    return (await client.get("/api/me")).json()["id"]


async def _customer(client, name="测试客户"):
    return (
        (await client.post("/api/customers", json={"name": name})).json()["id"]
    )


async def _project(client, customer_id, name="测试项目", **extra):
    payload = {"customer_id": customer_id, "name": name, **extra}
    return (await client.post("/api/projects", json=payload)).json()


# ─── 创建 + 自动 Agent + Owner ────────────────────────────────


async def test_create_project_auto_owner_and_agent(logged_in_client, db_session):
    """创建项目 → 创建者是 Owner，自动生成 Agent 并绑定标准 Skill/Plugin。"""
    from app.models import Agent

    cid = await _customer(logged_in_client)
    proj = await _project(logged_in_client, cid, "数字化转型项目")
    assert proj["owner_id"] == await _me(logged_in_client)
    assert proj["my_role"] == "owner"
    assert proj["agent_id"] is not None
    assert proj["customer_name"] == "测试客户"
    assert proj["member_count"] == 1

    # 校验 Agent 行
    agent = await db_session.get(Agent, proj["agent_id"])
    assert agent is not None
    assert agent.name == "数字化转型项目 Agent"
    assert agent.code == f"consultant_{proj['id']}"
    assert "consultant-hypothesis-map" in agent.skills
    assert "consultant-router" in agent.plugins


async def test_create_project_invalid_customer(logged_in_client):
    """客户不存在 → 400。"""
    res = await logged_in_client.post(
        "/api/projects", json={"customer_id": 99999, "name": "孤儿项目"}
    )
    assert res.status_code == 400
    assert "客户" in res.json()["detail"]


# ─── 列表 / 详情 隔离 ─────────────────────────────────────────


async def test_list_projects_isolation(logged_in_client, other_logged_in_client):
    """普通用户只看到自己可访问的项目。"""
    cid = await _customer(logged_in_client)
    await _project(logged_in_client, cid, "我的项目")

    # bob 视角：看不到 alice 的项目
    res = await other_logged_in_client.get("/api/projects")
    assert res.status_code == 200
    assert res.json() == []

    # bob 自己建一个 → 只看到自己的
    cid2 = await _customer(other_logged_in_client, "bob客户")
    await _project(other_logged_in_client, cid2, "bob项目")
    res = await other_logged_in_client.get("/api/projects")
    names = [p["name"] for p in res.json()]
    assert names == ["bob项目"]


async def test_get_project_forbidden_non_member(
    logged_in_client, other_logged_in_client
):
    """非成员访问他人项目 → 403。"""
    cid = await _customer(logged_in_client)
    proj = await _project(logged_in_client, cid, "私密项目")

    res = await other_logged_in_client.get(f"/api/projects/{proj['id']}")
    assert res.status_code == 403


async def test_get_project_admin_bypass(admin_client, other_logged_in_client):
    """admin 可访问任意项目（即便不是成员）。"""
    cid = await _customer(other_logged_in_client)
    proj = await _project(other_logged_in_client, cid, "bob的项目")

    res = await admin_client.get(f"/api/projects/{proj['id']}")
    assert res.status_code == 200
    assert res.json()["my_role"] == "admin"


async def test_get_project_not_found(logged_in_client):
    res = await logged_in_client.get("/api/projects/99999")
    assert res.status_code == 404


# ─── 更新权限 ──────────────────────────────────────────────────


async def test_update_project_owner(logged_in_client):
    cid = await _customer(logged_in_client)
    proj = await _project(logged_in_client, cid, "原名")
    res = await logged_in_client.put(
        f"/api/projects/{proj['id']}",
        json={"name": "改名", "status": "paused"},
    )
    assert res.status_code == 200
    assert res.json()["name"] == "改名"
    assert res.json()["status"] == "paused"


async def test_update_project_forbidden_non_member(
    logged_in_client, other_logged_in_client
):
    """非成员不能更新 → 403。"""
    cid = await _customer(logged_in_client)
    proj = await _project(logged_in_client, cid, "x")
    res = await other_logged_in_client.put(
        f"/api/projects/{proj['id']}", json={"name": "乱改"}
    )
    assert res.status_code == 403


# ─── 成员管理 ──────────────────────────────────────────────────


async def test_member_lifecycle(logged_in_client, other_logged_in_client):
    """Owner 邀请 deputy → deputy 可访问 → 移除后失效。"""
    cid = await _customer(logged_in_client)
    proj = await _project(logged_in_client, cid, "协作项目")
    pid = proj["id"]
    bob_id = await _me(other_logged_in_client)

    # 邀请 bob 为 deputy
    res = await logged_in_client.post(
        f"/api/projects/{pid}/members", json={"user_id": bob_id, "role": "deputy"}
    )
    assert res.status_code == 201
    assert res.json()["role"] == "deputy"

    # 成员列表含 owner + deputy
    members = (await logged_in_client.get(f"/api/projects/{pid}/members")).json()
    roles = {m["user_id"]: m["role"] for m in members}
    assert roles[await _me(logged_in_client)] == "owner"
    assert roles[bob_id] == "deputy"

    # bob 现在可访问项目，my_role=deputy
    res = await other_logged_in_client.get(f"/api/projects/{pid}")
    assert res.status_code == 200
    assert res.json()["my_role"] == "deputy"

    # 重复添加 → 400
    res = await logged_in_client.post(
        f"/api/projects/{pid}/members", json={"user_id": bob_id}
    )
    assert res.status_code == 400

    # 移除 bob
    res = await logged_in_client.delete(f"/api/projects/{pid}/members/{bob_id}")
    assert res.status_code == 204
    # bob 失去访问
    assert (
        await other_logged_in_client.get(f"/api/projects/{pid}")
    ).status_code == 403


async def test_add_member_cannot_add_owner(logged_in_client, other_logged_in_client):
    """保持单 Owner：不能新增 Owner。"""
    cid = await _customer(logged_in_client)
    proj = await _project(logged_in_client, cid)
    bob_id = await _me(other_logged_in_client)
    res = await logged_in_client.post(
        f"/api/projects/{proj['id']}/members",
        json={"user_id": bob_id, "role": "owner"},
    )
    assert res.status_code == 400


async def test_cannot_remove_owner(logged_in_client):
    """不能移除项目 Owner。"""
    cid = await _customer(logged_in_client)
    proj = await _project(logged_in_client, cid)
    me = await _me(logged_in_client)
    res = await logged_in_client.delete(f"/api/projects/{proj['id']}/members/{me}")
    assert res.status_code == 400
    assert "Owner" in res.json()["detail"]


async def test_deputy_cannot_manage_members(
    logged_in_client, other_logged_in_client
):
    """deputy 不能邀请/移除成员 → 403。"""
    cid = await _customer(logged_in_client)
    proj = await _project(logged_in_client, cid)
    pid = proj["id"]
    bob_id = await _me(other_logged_in_client)
    await logged_in_client.post(
        f"/api/projects/{pid}/members", json={"user_id": bob_id}
    )

    # bob（deputy）尝试邀请自己（已在内）或改成员 → 应 403
    res = await other_logged_in_client.post(
        f"/api/projects/{pid}/members", json={"user_id": bob_id}
    )
    assert res.status_code == 403


async def test_add_member_user_not_found(logged_in_client):
    cid = await _customer(logged_in_client)
    proj = await _project(logged_in_client, cid)
    res = await logged_in_client.post(
        f"/api/projects/{proj['id']}/members", json={"user_id": 99999}
    )
    assert res.status_code == 400
    assert "用户" in res.json()["detail"]


# ─── 部门授权 ──────────────────────────────────────────────────


async def test_department_access_grants_membership(
    logged_in_client, other_logged_in_client, db_session
):
    """授权部门后，部门成员自动获得项目访问权（deputy 级）。"""
    from app.models import Organization, UserOrganization

    cid = await _customer(logged_in_client)
    proj = await _project(logged_in_client, cid, "部门协作项目")
    pid = proj["id"]
    bob_id = await _me(other_logged_in_client)

    # 直接在 DB 建组织并把 bob 挂进去
    org = Organization(name="交付二部", type="department")
    db_session.add(org)
    await db_session.flush()
    db_session.add(UserOrganization(user_id=bob_id, organization_id=org.id))
    await db_session.commit()
    org_id = org.id

    # 授权前 bob 不能访问
    assert (
        await other_logged_in_client.get(f"/api/projects/{pid}")
    ).status_code == 403

    # Owner 授权该部门
    res = await logged_in_client.post(
        f"/api/projects/{pid}/department-access",
        json={"organization_id": org_id},
    )
    assert res.status_code == 201
    assert res.json()["organization_name"] == "交付二部"

    # bob 现在可访问，my_role=deputy
    res = await other_logged_in_client.get(f"/api/projects/{pid}")
    assert res.status_code == 200
    assert res.json()["my_role"] == "deputy"

    # 部门授权列表含该部门
    grants = (
        await logged_in_client.get(f"/api/projects/{pid}/department-access")
    ).json()
    assert any(g["organization_id"] == org_id for g in grants)

    # 重复授权 → 400
    res = await logged_in_client.post(
        f"/api/projects/{pid}/department-access",
        json={"organization_id": org_id},
    )
    assert res.status_code == 400

    # 撤销 → bob 失去访问
    res = await logged_in_client.delete(
        f"/api/projects/{pid}/department-access/{org_id}"
    )
    assert res.status_code == 204
    assert (
        await other_logged_in_client.get(f"/api/projects/{pid}")
    ).status_code == 403


async def test_grant_dept_access_org_not_found(logged_in_client):
    cid = await _customer(logged_in_client)
    proj = await _project(logged_in_client, cid)
    res = await logged_in_client.post(
        f"/api/projects/{proj['id']}/department-access",
        json={"organization_id": 99999},
    )
    assert res.status_code == 400
    assert "组织" in res.json()["detail"]


async def test_dept_access_owner_only(logged_in_client, other_logged_in_client):
    """deputy 不能授权部门 → 403。"""
    cid = await _customer(logged_in_client)
    proj = await _project(logged_in_client, cid)
    pid = proj["id"]
    bob_id = await _me(other_logged_in_client)
    await logged_in_client.post(
        f"/api/projects/{pid}/members", json={"user_id": bob_id}
    )
    res = await other_logged_in_client.post(
        f"/api/projects/{pid}/department-access",
        json={"organization_id": 1},
    )
    assert res.status_code == 403


# ─── 删除 ──────────────────────────────────────────────────────


async def test_delete_project_owner(logged_in_client, db_session):
    """Owner 删除项目 → 项目、成员、项目 Agent 一并清除。"""
    from app.models import Agent, ProjectMember

    cid = await _customer(logged_in_client)
    proj = await _project(logged_in_client, cid, "要删的项目")
    pid = proj["id"]
    agent_id = proj["agent_id"]

    res = await logged_in_client.delete(f"/api/projects/{pid}")
    assert res.status_code == 204

    # 项目不再可见
    assert (await logged_in_client.get(f"/api/projects/{pid}")).status_code == 404
    # Agent 已删
    assert await db_session.get(Agent, agent_id) is None
    # 成员记录已级联清除
    members = (
        await db_session.execute(
            ProjectMember.__table__.select().where(
                ProjectMember.project_id == pid
            )
        )
    ).all()
    assert members == []


async def test_delete_project_deputy_forbidden(
    logged_in_client, other_logged_in_client
):
    """deputy 不能删除项目 → 403。"""
    cid = await _customer(logged_in_client)
    proj = await _project(logged_in_client, cid)
    pid = proj["id"]
    bob_id = await _me(other_logged_in_client)
    await logged_in_client.post(
        f"/api/projects/{pid}/members", json={"user_id": bob_id}
    )
    res = await other_logged_in_client.delete(f"/api/projects/{pid}")
    assert res.status_code == 403
