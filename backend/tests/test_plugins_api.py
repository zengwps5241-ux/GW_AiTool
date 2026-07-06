"""/api/plugins 端点的集成测试。"""

import json


async def test_plugins_endpoint_returns_list(logged_in_client, monkeypatch, tmp_path):
    c = logged_in_client
    plugins_dir = tmp_path / "plugins"
    plugin = plugins_dir / "demo"
    meta = plugin / ".claude-plugin"
    meta.mkdir(parents=True)
    (meta / "plugin.json").write_text(
        json.dumps({"name": "demo", "version": "1.0", "description": "演示插件"}),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.modules.catalog.plugins._plugins_dir", lambda: plugins_dir)

    r = await c.get("/api/plugins")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "demo"
    assert data[0]["version"] == "1.0"
    assert data[0]["description"] == "演示插件"
    assert data[0]["path"] == "demo"
    assert data[0]["category"] == "默认"


async def test_plugins_endpoint_empty_when_dir_missing(
    logged_in_client, monkeypatch, tmp_path
):
    c = logged_in_client
    monkeypatch.setattr(
        "app.modules.catalog.plugins._plugins_dir", lambda: tmp_path / "absent"
    )
    r = await c.get("/api/plugins")
    assert r.status_code == 200
    assert r.json() == []
