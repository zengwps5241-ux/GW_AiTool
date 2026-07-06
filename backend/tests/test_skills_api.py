import pytest


async def test_skills_endpoint_returns_list(logged_in_client, monkeypatch, tmp_path):
    c = logged_in_client
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_dir = skills_dir / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo desc\n---\n", encoding="utf-8"
    )
    monkeypatch.setattr("app.modules.catalog.skills._skills_dir", lambda: skills_dir)
    r = await c.get("/api/skills")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "demo-skill"
    assert data[0]["category"] == "默认"


async def test_skills_endpoint_returns_category(logged_in_client, monkeypatch, tmp_path):
    c = logged_in_client
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_dir = skills_dir / "cat-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: cat-skill\n---\n", encoding="utf-8")
    monkeypatch.setattr("app.modules.catalog.skills._skills_dir", lambda: skills_dir)

    # 创建分类和绑定
    from app.db.session import async_session
    from app.models import Category, SkillBinding
    async with async_session() as session:
        cat = Category(name="测试分类")
        session.add(cat)
        await session.commit()
        await session.refresh(cat)
        session.add(SkillBinding(skill_name="cat-skill", category_id=cat.id))
        await session.commit()

    r = await c.get("/api/skills")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["category"] == "测试分类"