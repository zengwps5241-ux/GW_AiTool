"""管理员技能 API 测试。"""

import io
import zipfile

from sqlalchemy import select


async def _get_default_category_id(admin_client):
    """获取默认分类的 ID。"""
    r = await admin_client.get("/api/admin/categories")
    return next(c["id"] for c in r.json() if c["name"] == "默认")


async def test_upload_skill_zip(admin_client, tmp_path, monkeypatch):
    """上传有效的技能 zip 包。"""
    c = admin_client
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    default_cat_id = await _get_default_category_id(c)

    # 构建一个有效的技能 zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "test-skill/SKILL.md",
            "---\nname: test-skill\ndescription: test desc\n---\n",
        )
    buf.seek(0)
    r = await c.post(
        "/api/admin/skills/upload",
        data={"category_id": default_cat_id},
        files={"file": ("test.zip", buf, "application/zip")},
    )
    assert r.status_code == 200
    assert (skills_dir / "test-skill" / "SKILL.md").exists()


async def test_update_skill_category(admin_client, tmp_path, monkeypatch):
    """修改已上传技能的分类绑定。"""
    c = admin_client
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    default_cat_id = await _get_default_category_id(c)
    r = await c.post("/api/admin/categories", json={"name": "新技能分类"})
    target_cat_id = r.json()["id"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "move-skill/SKILL.md",
            "---\nname: move-skill\ndescription: test desc\n---\n",
        )
    buf.seek(0)
    await c.post(
        "/api/admin/skills/upload",
        data={"category_id": default_cat_id},
        files={"file": ("move.zip", buf, "application/zip")},
    )

    r = await c.patch(
        "/api/admin/skills/move-skill/category",
        json={"category_id": target_cat_id},
    )
    assert r.status_code == 200
    assert r.json()["category_id"] == target_cat_id

    from app.db.session import async_session
    from app.models import SkillBinding

    async with async_session() as session:
        result = await session.execute(
            select(SkillBinding).where(SkillBinding.skill_name == "move-skill")
        )
        binding = result.scalar_one()
        assert binding.category_id == target_cat_id


async def test_upload_flat_skill_zip_uses_zip_name(admin_client, tmp_path, monkeypatch):
    """根目录直接包含 SKILL.md 时，用 zip 文件名作为技能名。"""
    c = admin_client
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    default_cat_id = await _get_default_category_id(c)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "SKILL.md",
            "---\nname: inner-name\ndescription: test desc\n---\n",
        )
        zf.writestr("README.md", "# readme")
    buf.seek(0)
    r = await c.post(
        "/api/admin/skills/upload",
        data={"category_id": default_cat_id},
        files={"file": ("flat-skill.zip", buf, "application/zip")},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "flat-skill"
    skill_md = skills_dir / "flat-skill" / "SKILL.md"
    assert skill_md.exists()
    assert "name: flat-skill" in skill_md.read_text(encoding="utf-8")
    assert (skills_dir / "flat-skill" / "README.md").exists()


async def test_upload_skill_zip_non_zip_rejected(admin_client):
    """上传非 zip 文件应返回 422。"""
    c = admin_client
    default_cat_id = await _get_default_category_id(c)
    buf = io.BytesIO(b"not a zip")
    r = await c.post(
        "/api/admin/skills/upload",
        data={"category_id": default_cat_id},
        files={"file": ("test.txt", buf, "text/plain")},
    )
    assert r.status_code == 422
    assert "zip" in r.json()["detail"].lower()


async def test_upload_skill_zip_missing_skill_md(admin_client, tmp_path, monkeypatch):
    """zip 包缺少 SKILL.md 应返回 422。"""
    c = admin_client
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    default_cat_id = await _get_default_category_id(c)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("test-skill/README.md", "# readme")
    buf.seek(0)
    r = await c.post(
        "/api/admin/skills/upload",
        data={"category_id": default_cat_id},
        files={"file": ("test.zip", buf, "application/zip")},
    )
    assert r.status_code == 422
    assert "SKILL.md" in r.json()["detail"]


async def test_upload_skill_zip_path_traversal_rejected(admin_client, tmp_path, monkeypatch):
    """zip 包包含路径穿越应返回 422。"""
    c = admin_client
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    default_cat_id = await _get_default_category_id(c)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "../../../etc/passwd",
            "root:x:0:0:root:/root:/bin/bash",
        )
    buf.seek(0)
    r = await c.post(
        "/api/admin/skills/upload",
        data={"category_id": default_cat_id},
        files={"file": ("test.zip", buf, "application/zip")},
    )
    assert r.status_code == 422


async def test_admin_skills_requires_admin_role(logged_in_client):
    """普通用户访问管理员 API 应返回 403。"""
    r = await logged_in_client.get("/api/admin/skills/test-skill/files")
    assert r.status_code == 403


async def test_upload_skill_zip_missing_description_rejected(admin_client, tmp_path, monkeypatch):
    """SKILL.md 缺少 description 字段应返回 422。"""
    c = admin_client
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    default_cat_id = await _get_default_category_id(c)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "test-skill/SKILL.md",
            "---\nname: test-skill\n---\n",
        )
    buf.seek(0)
    r = await c.post(
        "/api/admin/skills/upload",
        data={"category_id": default_cat_id},
        files={"file": ("test.zip", buf, "application/zip")},
    )
    assert r.status_code == 422
    assert "description" in r.json()["detail"]


async def test_upload_skill_zip_illegal_name_rejected(admin_client, tmp_path, monkeypatch):
    """SKILL.md name 包含非法字符应返回 422。"""
    c = admin_client
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    default_cat_id = await _get_default_category_id(c)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "bad-skill/SKILL.md",
            "---\nname: bad/name\ndescription: test desc\n---\n",
        )
    buf.seek(0)
    r = await c.post(
        "/api/admin/skills/upload",
        data={"category_id": default_cat_id},
        files={"file": ("test.zip", buf, "application/zip")},
    )
    assert r.status_code == 422
    assert "非法字符" in r.json()["detail"]


async def test_admin_skills_returns_200_for_admin(admin_client, tmp_path, monkeypatch):
    """管理员访问管理员 API 应返回 200。"""
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "test-skill"
    skill_dir.mkdir(parents=True)
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)
    r = await admin_client.get("/api/admin/skills/test-skill/files")
    assert r.status_code == 200


async def test_list_skill_files(admin_client, tmp_path, monkeypatch):
    c = admin_client
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Demo", encoding="utf-8")
    (skill_dir / "lib").mkdir()
    (skill_dir / "lib" / "util.py").write_text("# util", encoding="utf-8")
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    r = await c.get("/api/admin/skills/demo/files")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "demo"
    assert len(data["children"]) == 2


async def test_read_skill_file(admin_client, tmp_path, monkeypatch):
    c = admin_client
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("hello", encoding="utf-8")
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    r = await c.get("/api/admin/skills/demo/files/SKILL.md")
    assert r.status_code == 200
    assert r.text == "hello"


async def test_write_skill_file(admin_client, tmp_path, monkeypatch):
    c = admin_client
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("old", encoding="utf-8")
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    r = await c.put(
        "/api/admin/skills/demo/files/SKILL.md",
        json={"content": "new"},
    )
    assert r.status_code == 200
    assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == "new"


async def test_create_skill_file(admin_client, tmp_path, monkeypatch):
    c = admin_client
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "demo"
    skill_dir.mkdir(parents=True)
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    r = await c.post(
        "/api/admin/skills/demo/files",
        json={"path": "new.md", "content": "hello"},
    )
    assert r.status_code == 200
    assert (skill_dir / "new.md").read_text(encoding="utf-8") == "hello"


async def test_delete_skill_file(admin_client, tmp_path, monkeypatch):
    c = admin_client
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "old.md").write_text("bye", encoding="utf-8")
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    r = await c.delete("/api/admin/skills/demo/files/old.md")
    assert r.status_code == 204
    assert not (skill_dir / "old.md").exists()


async def test_delete_skill_with_references(admin_client, tmp_path, monkeypatch):
    from app.models import Agent
    from app.db.session import async_session

    c = admin_client
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---", encoding="utf-8")
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    # 创建一个引用该技能的 agent
    async with async_session() as db:
        db.add(Agent(name="a", code="a", skills="demo", plugins="", is_default=False))
        await db.commit()

    # 不带 force 参数应返回 409
    r = await c.delete("/api/admin/skills/demo")
    assert r.status_code == 409
    data = r.json()
    detail = data["detail"]
    assert "agents" in detail
    assert len(detail["agents"]) == 1

    # 带 force 参数应成功删除
    r = await c.delete("/api/admin/skills/demo?force=true")
    assert r.status_code == 204
    assert not skill_dir.exists()


async def test_delete_skill_no_references(admin_client, tmp_path, monkeypatch):
    c = admin_client
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---", encoding="utf-8")
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    r = await c.delete("/api/admin/skills/demo")
    assert r.status_code == 204
    assert not skill_dir.exists()


async def test_delete_skill_not_found(admin_client, tmp_path, monkeypatch):
    """删除不存在的技能应返回 404。"""
    c = admin_client
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True)
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    r = await c.delete("/api/admin/skills/nonexistent")
    assert r.status_code == 404
    assert "不存在" in r.json()["detail"]


async def test_upload_skill_with_category(admin_client, monkeypatch, tmp_path):
    """上传技能时指定分类，绑定记录正确写入。"""
    c = admin_client
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    # 创建分类
    r = await c.post("/api/admin/categories", json={"name": "技能测试分类"})
    cat_id = r.json()["id"]

    # 创建 ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("upload-skill/SKILL.md", "---\nname: upload-skill\ndescription: d\n---\n")
    buf.seek(0)

    r = await c.post(
        "/api/admin/skills/upload",
        data={"category_id": cat_id},
        files={"file": ("skill.zip", buf, "application/zip")},
    )
    assert r.status_code == 200

    # 验证绑定
    from app.db.session import async_session
    from app.models import SkillBinding
    async with async_session() as session:
        result = await session.execute(
            select(SkillBinding).where(SkillBinding.skill_name == "upload-skill")
        )
        binding = result.scalar_one()
        assert binding.category_id == cat_id


async def test_delete_skill_removes_binding(admin_client, monkeypatch, tmp_path):
    """删除技能时同步删除绑定记录。"""
    c = admin_client
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_skills._skills_dir", lambda: skills_dir)

    default_cat_id = await _get_default_category_id(c)

    # 创建技能 ZIP 并上传
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("del-skill/SKILL.md", "---\nname: del-skill\ndescription: d\n---\n")
    buf.seek(0)

    await c.post(
        "/api/admin/skills/upload",
        data={"category_id": default_cat_id},
        files={"file": ("skill.zip", buf, "application/zip")},
    )

    # 删除技能
    r = await c.delete("/api/admin/skills/del-skill")
    assert r.status_code == 204

    # 验证绑定已删除
    from app.db.session import async_session
    from app.models import SkillBinding
    async with async_session() as session:
        result = await session.execute(
            select(SkillBinding).where(SkillBinding.skill_name == "del-skill")
        )
        assert result.scalar_one_or_none() is None
