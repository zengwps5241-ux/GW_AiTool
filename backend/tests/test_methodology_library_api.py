"""团队空间「方法论库」测试（§2.6 / §6.3，admin 维护，用户只读）。

POST/PUT/DELETE 仅 admin/super；GET 所有登录用户只读。
端点为全局（非团队空间作用域）：/api/team-spaces/methodology-library。
"""

import pytest


async def test_list_empty(logged_in_client):
    """全新库 → 空列表（lifespan 种子在 ASGITransport 下不触发）。"""
    res = await logged_in_client.get("/api/team-spaces/methodology-library")
    assert res.status_code == 200
    assert res.json() == []


async def test_requires_login(client):
    res = await client.get("/api/team-spaces/methodology-library")
    assert res.status_code in (401, 403)


async def test_create_requires_admin(logged_in_client):
    """普通用户写 → 403（§3.2 管理种子数据仅 admin）。"""
    res = await logged_in_client.post(
        "/api/team-spaces/methodology-library",
        json={"category": "prompt_template", "title": "x", "content": "y"},
    )
    assert res.status_code == 403


async def test_admin_full_crud(admin_client):
    """admin 走完 增→查→改→查→删→查 全链路。"""
    # 增
    created = (
        await admin_client.post(
            "/api/team-spaces/methodology-library",
            json={
                "category": "methodology_rule",
                "title": "测试准则",
                "content": "# 准则\n第一条",
                "sort_order": 2,
            },
        )
    ).json()
    assert created["id"] > 0
    assert created["category"] == "methodology_rule"
    assert created["title"] == "测试准则"
    assert created["sort_order"] == 2
    assert created["created_by_name"]  # admin 创建者姓名已解析

    # 列表含
    items = (await admin_client.get("/api/team-spaces/methodology-library")).json()
    assert any(it["id"] == created["id"] for it in items)

    # 改
    updated = (
        await admin_client.put(
            f"/api/team-spaces/methodology-library/{created['id']}",
            json={"title": "改名准则", "sort_order": 5},
        )
    ).json()
    assert updated["title"] == "改名准则"
    assert updated["sort_order"] == 5
    assert updated["category"] == "methodology_rule"  # 未传不变

    # 详情
    detail = (
        await admin_client.get(
            f"/api/team-spaces/methodology-library/{created['id']}"
        )
    ).json()
    assert detail["title"] == "改名准则"

    # 删
    del_res = await admin_client.delete(
        f"/api/team-spaces/methodology-library/{created['id']}"
    )
    assert del_res.status_code == 204
    miss = await admin_client.get(
        f"/api/team-spaces/methodology-library/{created['id']}"
    )
    assert miss.status_code == 404


async def test_category_filter(admin_client):
    await admin_client.post(
        "/api/team-spaces/methodology-library",
        json={"category": "prompt_template", "title": "P1", "content": "c"},
    )
    await admin_client.post(
        "/api/team-spaces/methodology-library",
        json={"category": "canvas_schema", "title": "C1", "content": "c"},
    )
    all_items = (await admin_client.get("/api/team-spaces/methodology-library")).json()
    assert len(all_items) == 2
    only_prompt = (
        await admin_client.get(
            "/api/team-spaces/methodology-library?category=prompt_template"
        )
    ).json()
    assert len(only_prompt) == 1
    assert only_prompt[0]["category"] == "prompt_template"


async def test_get_unknown_404(admin_client):
    res = await admin_client.get("/api/team-spaces/methodology-library/99999")
    assert res.status_code == 404


async def test_update_unknown_404(admin_client):
    res = await admin_client.put(
        "/api/team-spaces/methodology-library/99999",
        json={"title": "x"},
    )
    assert res.status_code == 404


async def test_delete_unknown_404(admin_client):
    res = await admin_client.delete("/api/team-spaces/methodology-library/99999")
    assert res.status_code == 404


async def test_delete_requires_admin(other_logged_in_client, admin_client):
    """普通用户（独立 bob）不能删 admin 创建的条目。

    注：admin_client 与 logged_in_client 共用同一 client（admin 登录覆盖），
    故非 admin 身份须用独立的 other_logged_in_client（bob）。
    """
    created = (
        await admin_client.post(
            "/api/team-spaces/methodology-library",
            json={"category": "prompt_template", "title": "t", "content": "c"},
        )
    ).json()
    res = await other_logged_in_client.delete(
        f"/api/team-spaces/methodology-library/{created['id']}"
    )
    assert res.status_code == 403


async def test_seed_default_idempotent(db_session):
    """服务层种子：首次插 3 条，二次调用幂等（表非空则跳过）。"""
    from app.modules.team_spaces.service import (
        list_methodology,
        seed_default_methodology,
    )

    await seed_default_methodology(db_session)
    items = await list_methodology(db_session)
    assert len(items) == 3
    categories = {it.category for it in items}
    assert categories == {"prompt_template", "canvas_schema", "methodology_rule"}

    # 再次调用不应翻倍
    await seed_default_methodology(db_session)
    items2 = await list_methodology(db_session)
    assert len(items2) == 3
