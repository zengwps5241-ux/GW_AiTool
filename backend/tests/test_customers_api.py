"""客户管理 API 测试（M1.3.5）。

覆盖：
- 创建（任何已登录用户）
- 列表可见性（admin 全部；普通用户按「自建 ∪ 可访问项目」过滤；跨用户隔离）
- 详情访问（无权限 → 404）
- 更新 / 删除权限（admin 或创建者）
- 删除约束（存在项目时拒绝）
"""

import pytest


# ─── 创建 ──────────────────────────────────────────────────────


async def test_create_customer_as_user(logged_in_client):
    """任何已登录用户可创建客户。"""
    res = await logged_in_client.post(
        "/api/customers",
        json={"name": "中石油", "industry": "能源", "scale": "大型", "region": "北京"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "中石油"
    assert data["industry"] == "能源"
    assert data["scale"] == "大型"
    assert data["id"] > 0
    assert data["project_count"] == 0


async def test_create_customer_invalid_scale(logged_in_client):
    """非法 scale 应 422。"""
    res = await logged_in_client.post(
        "/api/customers", json={"name": "X", "scale": "巨型"}
    )
    assert res.status_code == 422


# ─── 列表可见性 ────────────────────────────────────────────────


async def _create_customer(client, name):
    res = await client.post("/api/customers", json={"name": name})
    assert res.status_code == 201
    return res.json()["id"]


async def _create_project(client, customer_id, name):
    res = await client.post(
        "/api/projects", json={"customer_id": customer_id, "name": name}
    )
    assert res.status_code == 201
    return res.json()["id"]


async def test_list_customers_admin_all(admin_client, other_logged_in_client):
    """admin 看全部客户（含他人创建的）。"""
    await _create_customer(admin_client, "客户A")
    # 另一用户创建一个
    await _create_customer(other_logged_in_client, "客户B")

    res = await admin_client.get("/api/customers")
    assert res.status_code == 200
    names = {c["name"] for c in res.json()}
    assert "客户A" in names
    assert "客户B" in names


async def test_list_customers_user_isolation(logged_in_client, other_logged_in_client):
    """普通用户只能看到自己创建的 / 可访问项目的客户；看不到他人的。"""
    await _create_customer(logged_in_client, "我的客户")
    await _create_customer(other_logged_in_client, "别人的客户")

    res = await logged_in_client.get("/api/customers")
    assert res.status_code == 200
    names = {c["name"] for c in res.json()}
    assert "我的客户" in names
    assert "别人的客户" not in names


async def test_list_customers_empty_for_new_user(other_logged_in_client):
    """全新普通用户（无客户无项目）列表为空。"""
    res = await other_logged_in_client.get("/api/customers")
    assert res.status_code == 200
    assert res.json() == []


# ─── 详情访问 ──────────────────────────────────────────────────


async def test_get_customer_creator(logged_in_client):
    """创建者可查看自己的客户。"""
    cid = await _create_customer(logged_in_client, "查得到")
    res = await logged_in_client.get(f"/api/customers/{cid}")
    assert res.status_code == 200
    assert res.json()["name"] == "查得到"


async def test_get_customer_no_access_404(logged_in_client, other_logged_in_client):
    """他人创建且无项目的客户 → 无权限 → 404。"""
    cid = await _create_customer(other_logged_in_client, "私密客户")
    res = await logged_in_client.get(f"/api/customers/{cid}")
    assert res.status_code == 404


async def test_get_customer_admin_any(admin_client, other_logged_in_client):
    """admin 可查看任意客户。"""
    cid = await _create_customer(other_logged_in_client, "任意客户")
    res = await admin_client.get(f"/api/customers/{cid}")
    assert res.status_code == 200


async def test_get_customer_not_found(logged_in_client):
    res = await logged_in_client.get("/api/customers/99999")
    assert res.status_code == 404


# ─── 更新 ──────────────────────────────────────────────────────


async def test_update_customer_creator(logged_in_client):
    """创建者可更新。"""
    cid = await _create_customer(logged_in_client, "旧名")
    res = await logged_in_client.put(
        f"/api/customers/{cid}", json={"name": "新名", "industry": "金融"}
    )
    assert res.status_code == 200
    assert res.json()["name"] == "新名"
    assert res.json()["industry"] == "金融"


async def test_update_customer_forbidden_non_creator(
    logged_in_client, other_logged_in_client
):
    """非创建者非 admin → 403。"""
    cid = await _create_customer(other_logged_in_client, "别人的")
    res = await logged_in_client.put(f"/api/customers/{cid}", json={"name": "改掉"})
    assert res.status_code == 403


async def test_update_customer_admin(admin_client, other_logged_in_client):
    """admin 可更新任意客户。"""
    cid = await _create_customer(other_logged_in_client, "原名")
    res = await admin_client.put(f"/api/customers/{cid}", json={"name": "管理员改的"})
    assert res.status_code == 200
    assert res.json()["name"] == "管理员改的"


async def test_update_customer_not_found(admin_client):
    res = await admin_client.put("/api/customers/99999", json={"name": "x"})
    assert res.status_code == 404


# ─── 删除 ──────────────────────────────────────────────────────


async def test_delete_customer_creator_empty(logged_in_client):
    """创建者可删除无项目的客户。"""
    cid = await _create_customer(logged_in_client, "待删")
    res = await logged_in_client.delete(f"/api/customers/{cid}")
    assert res.status_code == 204
    # 再查 404
    assert (await logged_in_client.get(f"/api/customers/{cid}")).status_code == 404


async def test_delete_customer_with_project_rejected(logged_in_client):
    """存在项目时拒绝删除。"""
    cid = await _create_customer(logged_in_client, "有项目的客户")
    await _create_project(logged_in_client, cid, "项目1")
    res = await logged_in_client.delete(f"/api/customers/{cid}")
    assert res.status_code == 400
    assert "项目" in res.json()["detail"]


async def test_delete_customer_forbidden_non_creator(
    logged_in_client, other_logged_in_client
):
    """非创建者非 admin → 403。"""
    cid = await _create_customer(other_logged_in_client, "别人的")
    res = await logged_in_client.delete(f"/api/customers/{cid}")
    assert res.status_code == 403
