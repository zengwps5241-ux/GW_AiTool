"""组织架构管理 API 测试（自建三级架构）。

覆盖：
- CRUD（创建/查询/更新/删除）
- 树形查询
- 成员管理
- 批量导入（JSON + CSV）
- 防环校验、同父级同名去重、删除约束
- 权限（仅 admin/super；普通用户 403）
"""

import pytest


# ─── 权限 ────────────────────────────────────────────────────


async def test_organizations_forbidden_for_user(logged_in_client):
    """普通用户不能访问组织管理接口。"""
    res = await logged_in_client.get("/api/admin/organizations")
    assert res.status_code == 403


async def test_organizations_allowed_for_admin(admin_client):
    """admin 可以访问组织管理接口（空列表）。"""
    res = await admin_client.get("/api/admin/organizations")
    assert res.status_code == 200
    assert res.json() == []


async def test_organizations_allowed_for_super(super_client):
    """super 可以访问组织管理接口。"""
    res = await super_client.get("/api/admin/organizations")
    assert res.status_code == 200


# ─── CRUD ────────────────────────────────────────────────────


async def test_create_organization(admin_client):
    """创建公司根节点。"""
    res = await admin_client.post(
        "/api/admin/organizations",
        json={"name": "国科集团", "type": "company"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "国科集团"
    assert data["type"] == "company"
    assert data["parent_id"] is None
    assert data["id"] > 0


async def test_create_organization_with_parent(admin_client):
    """创建子部门，parent_id 引用父级。"""
    parent = await admin_client.post(
        "/api/admin/organizations",
        json={"name": "公司A", "type": "company"},
    )
    parent_id = parent.json()["id"]

    res = await admin_client.post(
        "/api/admin/organizations",
        json={"name": "研发部", "type": "department", "parent_id": parent_id},
    )
    assert res.status_code == 201
    assert res.json()["parent_id"] == parent_id


async def test_create_organization_invalid_parent(admin_client):
    """父级不存在应 400。"""
    res = await admin_client.post(
        "/api/admin/organizations",
        json={"name": "孤儿部门", "type": "department", "parent_id": 99999},
    )
    assert res.status_code == 400
    assert "父级" in res.json()["detail"]


async def test_create_organization_duplicate_name_same_parent(admin_client):
    """同父级下同名应 409/400 拒绝。"""
    await admin_client.post(
        "/api/admin/organizations", json={"name": "dup", "type": "company"}
    )
    res = await admin_client.post(
        "/api/admin/organizations", json={"name": "dup", "type": "company"}
    )
    assert res.status_code == 400
    assert "同名" in res.json()["detail"]


async def test_get_organization_not_found(admin_client):
    res = await admin_client.get("/api/admin/organizations/99999")
    assert res.status_code == 404


async def test_update_organization(admin_client):
    """更新名称/排序。"""
    created = await admin_client.post(
        "/api/admin/organizations", json={"name": "旧名", "type": "company"}
    )
    org_id = created.json()["id"]

    res = await admin_client.put(
        f"/api/admin/organizations/{org_id}",
        json={"name": "新名", "sort_order": 5},
    )
    assert res.status_code == 200
    assert res.json()["name"] == "新名"
    assert res.json()["sort_order"] == 5


async def test_update_organization_cycle_prevented(admin_client):
    """把节点挂到自身子节点下应被拒（防环）。"""
    a = await admin_client.post(
        "/api/admin/organizations", json={"name": "A", "type": "company"}
    )
    a_id = a.json()["id"]
    b = await admin_client.post(
        "/api/admin/organizations",
        json={"name": "B", "type": "department", "parent_id": a_id},
    )
    b_id = b.json()["id"]

    # 把 A 挂到 B 下 → 应形成环 A→B→A
    res = await admin_client.put(
        f"/api/admin/organizations/{a_id}",
        json={"parent_id": b_id},
    )
    assert res.status_code == 400
    assert "环" in res.json()["detail"]


async def test_delete_organization_with_children_rejected(admin_client):
    """有子节点时拒绝删除。"""
    parent = await admin_client.post(
        "/api/admin/organizations", json={"name": "父", "type": "company"}
    )
    pid = parent.json()["id"]
    await admin_client.post(
        "/api/admin/organizations",
        json={"name": "子", "type": "department", "parent_id": pid},
    )
    res = await admin_client.delete(f"/api/admin/organizations/{pid}")
    assert res.status_code == 400
    assert "子组织" in res.json()["detail"]


async def test_delete_organization_leaf(admin_client):
    """叶子节点可删除。"""
    created = await admin_client.post(
        "/api/admin/organizations", json={"name": "待删", "type": "company"}
    )
    org_id = created.json()["id"]
    res = await admin_client.delete(f"/api/admin/organizations/{org_id}")
    assert res.status_code == 204
    # 再查应 404
    res = await admin_client.get(f"/api/admin/organizations/{org_id}")
    assert res.status_code == 404


# ─── 树形查询 ────────────────────────────────────────────────


async def test_organization_tree(admin_client):
    """三级树形结构正确组装。"""
    company = await admin_client.post(
        "/api/admin/organizations", json={"name": "集团", "type": "company"}
    )
    cid = company.json()["id"]
    dept = await admin_client.post(
        "/api/admin/organizations",
        json={"name": "研发部", "type": "department", "parent_id": cid},
    )
    did = dept.json()["id"]
    await admin_client.post(
        "/api/admin/organizations",
        json={"name": "平台组", "type": "group", "parent_id": did},
    )

    res = await admin_client.get("/api/admin/organizations/tree")
    assert res.status_code == 200
    tree = res.json()
    assert len(tree) == 1
    root = tree[0]
    assert root["name"] == "集团"
    assert len(root["children"]) == 1
    assert root["children"][0]["name"] == "研发部"
    assert len(root["children"][0]["children"]) == 1
    assert root["children"][0]["children"][0]["name"] == "平台组"


# ─── 成员管理 ────────────────────────────────────────────────


async def test_member_management(admin_client):
    """添加/列出/移除成员。"""
    # 先建组织
    org = await admin_client.post(
        "/api/admin/organizations", json={"name": "市场部", "type": "department"}
    )
    org_id = org.json()["id"]

    # admin_client 登录的用户即 admin_user，查其 id
    me = await admin_client.get("/api/me")
    user_id = me.json()["id"]

    # 添加成员
    res = await admin_client.post(
        f"/api/admin/organizations/{org_id}/members",
        json={"user_id": user_id, "position_title": "市场经理", "is_primary": True},
    )
    assert res.status_code == 201
    assert res.json()["position_title"] == "市场经理"
    assert res.json()["is_primary"] is True

    # 列出成员
    res = await admin_client.get(f"/api/admin/organizations/{org_id}/members")
    assert res.status_code == 200
    members = res.json()
    assert len(members) == 1
    assert members[0]["user_id"] == user_id

    # 重复添加应 400
    res = await admin_client.post(
        f"/api/admin/organizations/{org_id}/members",
        json={"user_id": user_id},
    )
    assert res.status_code == 400

    # 移除成员
    res = await admin_client.delete(
        f"/api/admin/organizations/{org_id}/members/{user_id}"
    )
    assert res.status_code == 204

    # 再次列出应为空
    res = await admin_client.get(f"/api/admin/organizations/{org_id}/members")
    assert res.json() == []


async def test_add_member_org_not_found(admin_client):
    me = await admin_client.get("/api/me")
    user_id = me.json()["id"]
    res = await admin_client.post(
        "/api/admin/organizations/99999/members",
        json={"user_id": user_id},
    )
    assert res.status_code == 404


async def test_delete_organization_with_members_rejected(admin_client):
    """有成员时拒绝删除。"""
    org = await admin_client.post(
        "/api/admin/organizations", json={"name": "有成员的部门", "type": "department"}
    )
    org_id = org.json()["id"]
    me = await admin_client.get("/api/me")
    user_id = me.json()["id"]
    await admin_client.post(
        f"/api/admin/organizations/{org_id}/members",
        json={"user_id": user_id},
    )
    res = await admin_client.delete(f"/api/admin/organizations/{org_id}")
    assert res.status_code == 400
    assert "成员" in res.json()["detail"]


# ─── 批量导入 ────────────────────────────────────────────────


async def test_import_json(admin_client):
    """JSON 批量导入：公司→部门→小组三级。"""
    rows = [
        {"name": "国科集团", "type": "company"},
        {"name": "研发部", "type": "department", "parent_name": "国科集团"},
        {"name": "平台组", "type": "group", "parent_name": "研发部"},
        {"name": "市场部", "type": "department", "parent_name": "国科集团"},
    ]
    res = await admin_client.post("/api/admin/organizations/import", json=rows)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["result"]["total"] == 4
    assert data["result"]["created"] == 4
    assert data["result"]["skipped"] == 0
    assert data["result"]["errors"] == []

    # 校验树结构
    tree = (await admin_client.get("/api/admin/organizations/tree")).json()
    assert len(tree) == 1
    assert tree[0]["name"] == "国科集团"
    dept_names = {c["name"] for c in tree[0]["children"]}
    assert dept_names == {"研发部", "市场部"}


async def test_import_dedup(admin_client):
    """重复导入同父级同名应跳过（skipped）。"""
    rows = [{"name": "公司X", "type": "company"}]
    await admin_client.post("/api/admin/organizations/import", json=rows)
    res = await admin_client.post("/api/admin/organizations/import", json=rows)
    assert res.status_code == 200
    assert res.json()["result"]["created"] == 0
    assert res.json()["result"]["skipped"] == 1


async def test_import_csv(admin_client):
    """CSV 批量导入。"""
    csv_content = (
        "name,type,parent_name,head_user_username,position_title,is_primary,sort_order\n"
        "CSV公司,company,,, ,0\n"
        "CSV部门,department,CSV公司,,,0\n"
    )
    res = await admin_client.post(
        "/api/admin/organizations/import-csv",
        json={"content": csv_content, "content_type": "csv"},
    )
    assert res.status_code == 200
    assert res.json()["result"]["created"] == 2

    tree = (await admin_client.get("/api/admin/organizations/tree")).json()
    names = [t["name"] for t in tree]
    assert "CSV公司" in names


async def test_import_with_head_user(admin_client):
    """导入时通过 head_user_username 关联负责人 + 建立成员关系。"""
    me = await admin_client.get("/api/me")
    username = me.json()["username"]

    rows = [
        {
            "name": "带头公司",
            "type": "company",
            "head_user_username": username,
            "position_title": "负责人",
            "is_primary": True,
        }
    ]
    res = await admin_client.post("/api/admin/organizations/import", json=rows)
    assert res.status_code == 200
    assert res.json()["result"]["created"] == 1

    # 树中该节点应有 1 个成员（负责人）
    tree = (await admin_client.get("/api/admin/organizations/tree")).json()
    company = tree[0]
    assert company["head_user_id"] is not None
    assert len(company["members"]) == 1


async def test_import_invalid_head_user_skipped(admin_client):
    """负责人用户不存在时该行计入 errors。"""
    rows = [
        {"name": "公司Y", "type": "company", "head_user_username": "ghost_user"},
    ]
    res = await admin_client.post("/api/admin/organizations/import", json=rows)
    assert res.status_code == 200
    assert res.json()["result"]["created"] == 0
    assert len(res.json()["result"]["errors"]) == 1


async def test_import_csv_empty_rejected(admin_client):
    """空内容应 400。"""
    res = await admin_client.post(
        "/api/admin/organizations/import-csv",
        json={"content": "   ", "content_type": "csv"},
    )
    assert res.status_code == 400
