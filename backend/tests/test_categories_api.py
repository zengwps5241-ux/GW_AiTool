import pytest


async def test_list_categories(admin_client):
    r = await admin_client.get("/api/admin/categories")
    assert r.status_code == 200
    data = r.json()
    # 迁移已插入默认分类
    assert len(data) >= 1
    assert any(c["name"] == "默认" for c in data)


async def test_create_category(admin_client):
    r = await admin_client.post("/api/admin/categories", json={"name": "数据分析"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "数据分析"
    assert "id" in data


async def test_create_duplicate_category(admin_client):
    await admin_client.post("/api/admin/categories", json={"name": "重复分类"})
    r = await admin_client.post("/api/admin/categories", json={"name": "重复分类"})
    assert r.status_code == 409


async def test_rename_category(admin_client):
    r = await admin_client.post("/api/admin/categories", json={"name": "待改名"})
    cat_id = r.json()["id"]

    r = await admin_client.patch(
        f"/api/admin/categories/{cat_id}", json={"name": "已改名"}
    )
    assert r.status_code == 200
    assert r.json()["name"] == "已改名"


async def test_delete_category_moves_bindings(admin_client, monkeypatch, tmp_path):
    # 创建分类
    r = await admin_client.post("/api/admin/categories", json={"name": "将被删除"})
    cat_id = r.json()["id"]

    # 获取默认分类 id
    r = await admin_client.get("/api/admin/categories")
    default_id = next(c["id"] for c in r.json() if c["name"] == "默认")

    # 创建一个技能目录
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_dir = skills_dir / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: test-skill\n---\n", encoding="utf-8")
    monkeypatch.setattr("app.modules.catalog.skills._skills_dir", lambda: skills_dir)

    # 绑定技能到将被删除的分类
    from app.db.session import async_session
    from app.models import SkillBinding
    async with async_session() as session:
        session.add(SkillBinding(skill_name="test-skill", category_id=cat_id))
        await session.commit()

    # 删除分类
    r = await admin_client.delete(f"/api/admin/categories/{cat_id}")
    assert r.status_code == 204

    # 验证绑定已移到默认分类
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(SkillBinding).where(SkillBinding.skill_name == "test-skill")
        )
        binding = result.scalar_one()
        assert binding.category_id == default_id


async def test_delete_default_category_fails(admin_client):
    r = await admin_client.get("/api/admin/categories")
    default_id = next(c["id"] for c in r.json() if c["name"] == "默认")

    r = await admin_client.delete(f"/api/admin/categories/{default_id}")
    assert r.status_code == 400


async def test_delete_nonexistent_category(admin_client):
    r = await admin_client.delete("/api/admin/categories/99999")
    assert r.status_code == 404


async def test_categories_require_admin(logged_in_client):
    r = await logged_in_client.get("/api/admin/categories")
    assert r.status_code == 403
