"""管理员插件 API 测试。"""

import io
import zipfile

from sqlalchemy import select


async def _get_default_category_id(admin_client):
    """获取默认分类的 ID。"""
    r = await admin_client.get("/api/admin/categories")
    return next(c["id"] for c in r.json() if c["name"] == "默认")


async def test_admin_plugins_requires_admin_role(logged_in_client):
    r = await logged_in_client.get("/api/admin/plugins/test/files")
    assert r.status_code == 403


async def test_admin_plugins_allows_regular_user_in_development(
    logged_in_client, monkeypatch
):
    """开发环境下普通用户也应拥有管理员 API 权限。"""
    monkeypatch.setenv("APP_ENV", "development")

    from app.core.config import get_settings

    get_settings.cache_clear()

    r = await logged_in_client.get("/api/admin/plugins/test/files")
    assert r.status_code != 403


async def test_upload_plugin_zip(admin_client, tmp_path, monkeypatch):
    c = admin_client
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_plugins._plugins_dir", lambda: plugins_dir)

    default_cat_id = await _get_default_category_id(c)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "test-plugin/.claude-plugin/plugin.json",
            '{"name": "test-plugin", "version": "1.0", "description": "test"}',
        )
    buf.seek(0)
    r = await c.post(
        "/api/admin/plugins/upload",
        data={"category_id": default_cat_id},
        files={"file": ("test.zip", buf, "application/zip")},
    )
    assert r.status_code == 200
    assert (plugins_dir / "test-plugin" / ".claude-plugin" / "plugin.json").exists()


async def test_update_plugin_category(admin_client, tmp_path, monkeypatch):
    """修改已上传插件的分类绑定。"""
    c = admin_client
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_plugins._plugins_dir", lambda: plugins_dir)

    default_cat_id = await _get_default_category_id(c)
    r = await c.post("/api/admin/categories", json={"name": "新插件分类"})
    target_cat_id = r.json()["id"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "move-plugin/.claude-plugin/plugin.json",
            '{"name": "move-plugin", "version": "1.0", "description": "test"}',
        )
    buf.seek(0)
    await c.post(
        "/api/admin/plugins/upload",
        data={"category_id": default_cat_id},
        files={"file": ("move.zip", buf, "application/zip")},
    )

    r = await c.patch(
        "/api/admin/plugins/move-plugin/category",
        json={"category_id": target_cat_id},
    )
    assert r.status_code == 200
    assert r.json()["category_id"] == target_cat_id

    from app.db.session import async_session
    from app.models import PluginBinding

    async with async_session() as session:
        result = await session.execute(
            select(PluginBinding).where(PluginBinding.plugin_path == "move-plugin")
        )
        binding = result.scalar_one()
        assert binding.category_id == target_cat_id


async def test_list_plugin_files(admin_client, tmp_path, monkeypatch):
    c = admin_client
    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "demo"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / ".claude-plugin").mkdir()
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("app.api.routes.admin_plugins._plugins_dir", lambda: plugins_dir)

    r = await c.get("/api/admin/plugins/demo/files")
    assert r.status_code == 200


async def test_upload_plugin_zip_non_zip_rejected(admin_client):
    """上传非 zip 文件应返回 422。"""
    c = admin_client
    default_cat_id = await _get_default_category_id(c)
    buf = io.BytesIO(b"not a zip")
    r = await c.post(
        "/api/admin/plugins/upload",
        data={"category_id": default_cat_id},
        files={"file": ("test.txt", buf, "text/plain")},
    )
    assert r.status_code == 422
    assert "zip" in r.json()["detail"].lower()


async def test_upload_plugin_zip_missing_plugin_json(admin_client, tmp_path, monkeypatch):
    """zip 包缺少 plugin.json 应返回 422。"""
    c = admin_client
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_plugins._plugins_dir", lambda: plugins_dir)

    default_cat_id = await _get_default_category_id(c)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("test-plugin/README.md", "# readme")
    buf.seek(0)
    r = await c.post(
        "/api/admin/plugins/upload",
        data={"category_id": default_cat_id},
        files={"file": ("test.zip", buf, "application/zip")},
    )
    assert r.status_code == 422
    assert "plugin.json" in r.json()["detail"]


async def test_upload_plugin_zip_path_traversal_rejected(admin_client, tmp_path, monkeypatch):
    """zip 包包含路径穿越应返回 422。"""
    c = admin_client
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_plugins._plugins_dir", lambda: plugins_dir)

    default_cat_id = await _get_default_category_id(c)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "../../../etc/passwd",
            "root:x:0:0:root:/root:/bin/bash",
        )
    buf.seek(0)
    r = await c.post(
        "/api/admin/plugins/upload",
        data={"category_id": default_cat_id},
        files={"file": ("test.zip", buf, "application/zip")},
    )
    assert r.status_code == 422


async def test_read_plugin_file(admin_client, tmp_path, monkeypatch):
    """读取插件文件内容。"""
    c = admin_client
    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "demo"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / ".claude-plugin").mkdir()
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
        '{"name":"demo"}', encoding="utf-8"
    )
    monkeypatch.setattr("app.api.routes.admin_plugins._plugins_dir", lambda: plugins_dir)

    r = await c.get("/api/admin/plugins/demo/files/.claude-plugin/plugin.json")
    assert r.status_code == 200
    assert '"name":"demo"' in r.text


async def test_delete_plugin_not_found(admin_client, tmp_path, monkeypatch):
    """删除不存在的插件应返回 404。"""
    c = admin_client
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(parents=True)
    monkeypatch.setattr("app.api.routes.admin_plugins._plugins_dir", lambda: plugins_dir)

    r = await c.delete("/api/admin/plugins/nonexistent")
    assert r.status_code == 404
    assert "不存在" in r.json()["detail"]


async def test_delete_plugin_with_references(admin_client, tmp_path, monkeypatch):
    from app.models import Agent
    from app.db.session import async_session

    c = admin_client
    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "demo"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / ".claude-plugin").mkdir()
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
        '{"name":"demo","version":"1","description":"d"}', encoding="utf-8"
    )
    monkeypatch.setattr("app.api.routes.admin_plugins._plugins_dir", lambda: plugins_dir)

    async with async_session() as db:
        db.add(Agent(name="a", code="a", skills="", plugins="demo", is_default=False))
        await db.commit()

    r = await c.delete("/api/admin/plugins/demo")
    assert r.status_code == 409

    r = await c.delete("/api/admin/plugins/demo?force=true")
    assert r.status_code == 204
    assert not plugin_dir.exists()


async def test_upload_plugin_with_category(admin_client, monkeypatch, tmp_path):
    """上传插件时指定分类，绑定记录正确写入。"""
    c = admin_client
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_plugins._plugins_dir", lambda: plugins_dir)

    # 创建分类
    r = await c.post("/api/admin/categories", json={"name": "插件测试分类"})
    cat_id = r.json()["id"]

    # 创建 ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "upload-plugin/.claude-plugin/plugin.json",
            '{"name": "upload-plugin", "version": "1.0", "description": "d"}',
        )
    buf.seek(0)

    r = await c.post(
        "/api/admin/plugins/upload",
        data={"category_id": cat_id},
        files={"file": ("plugin.zip", buf, "application/zip")},
    )
    assert r.status_code == 200

    # 验证绑定
    from app.db.session import async_session
    from app.models import PluginBinding

    async with async_session() as session:
        result = await session.execute(
            select(PluginBinding).where(PluginBinding.plugin_path == "upload-plugin")
        )
        binding = result.scalar_one()
        assert binding.category_id == cat_id


async def test_delete_plugin_removes_binding(admin_client, monkeypatch, tmp_path):
    """删除插件时同步删除绑定记录。"""
    c = admin_client
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    monkeypatch.setattr("app.api.routes.admin_plugins._plugins_dir", lambda: plugins_dir)

    default_cat_id = await _get_default_category_id(c)

    # 创建插件 ZIP 并上传
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "del-plugin/.claude-plugin/plugin.json",
            '{"name": "del-plugin", "version": "1.0", "description": "d"}',
        )
    buf.seek(0)

    await c.post(
        "/api/admin/plugins/upload",
        data={"category_id": default_cat_id},
        files={"file": ("plugin.zip", buf, "application/zip")},
    )

    # 删除插件
    r = await c.delete("/api/admin/plugins/del-plugin")
    assert r.status_code == 204

    # 验证绑定已删除
    from app.db.session import async_session
    from app.models import PluginBinding

    async with async_session() as session:
        result = await session.execute(
            select(PluginBinding).where(PluginBinding.plugin_path == "del-plugin")
        )
        assert result.scalar_one_or_none() is None
