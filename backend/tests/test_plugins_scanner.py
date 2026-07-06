"""扫描 plugins 目录的单元测试。"""

import json

from app.modules.catalog.plugins import resolve_plugin_path, scan_plugins


def _write_manifest(plugin_root, **fields):
    """在指定插件目录下生成 .claude-plugin/plugin.json。"""
    meta_dir = plugin_root / ".claude-plugin"
    meta_dir.mkdir(parents=True)
    (meta_dir / "plugin.json").write_text(
        json.dumps(fields, ensure_ascii=False), encoding="utf-8"
    )


async def test_scan_returns_empty_when_dir_missing(monkeypatch, tmp_path):
    # 目录不存在应返回空列表,不应抛错
    monkeypatch.setattr(
        "app.modules.catalog.plugins._plugins_dir", lambda: tmp_path / "missing"
    )
    assert scan_plugins() == []


async def test_scan_flat_layout(monkeypatch, tmp_path):
    plugins_dir = tmp_path / "plugins"
    flat = plugins_dir / "demo"
    _write_manifest(flat, name="demo", version="1.0", description="平铺布局")
    monkeypatch.setattr("app.modules.catalog.plugins._plugins_dir", lambda: plugins_dir)

    result = scan_plugins()
    assert len(result) == 1
    assert result[0]["name"] == "demo"
    assert result[0]["version"] == "1.0"
    assert result[0]["description"] == "平铺布局"
    assert result[0]["path"] == "demo"


async def test_scan_versioned_layout(monkeypatch, tmp_path):
    plugins_dir = tmp_path / "plugins"
    versioned = plugins_dir / "demo" / "1.0.0"
    _write_manifest(versioned, name="demo", version="1.0.0")
    monkeypatch.setattr("app.modules.catalog.plugins._plugins_dir", lambda: plugins_dir)

    result = scan_plugins()
    assert len(result) == 1
    assert result[0]["path"] == "demo/1.0.0"


async def test_scan_falls_back_to_dir_name_when_manifest_lacks_name(
    monkeypatch, tmp_path
):
    plugins_dir = tmp_path / "plugins"
    plugin = plugins_dir / "无名插件"
    _write_manifest(plugin)  # 空 manifest
    monkeypatch.setattr("app.modules.catalog.plugins._plugins_dir", lambda: plugins_dir)

    result = scan_plugins()
    assert len(result) == 1
    assert result[0]["name"] == "无名插件"
    assert result[0]["version"] == ""
    assert result[0]["description"] == ""


async def test_scan_skips_invalid_json(monkeypatch, tmp_path):
    plugins_dir = tmp_path / "plugins"
    plugin = plugins_dir / "broken"
    meta_dir = plugin / ".claude-plugin"
    meta_dir.mkdir(parents=True)
    (meta_dir / "plugin.json").write_text("{这不是合法 JSON", encoding="utf-8")
    monkeypatch.setattr("app.modules.catalog.plugins._plugins_dir", lambda: plugins_dir)

    # 损坏的 manifest 不应阻止扫描,而是回退到目录名
    result = scan_plugins()
    assert len(result) == 1
    assert result[0]["name"] == "broken"


async def test_resolve_plugin_path_returns_absolute(monkeypatch, tmp_path):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    monkeypatch.setattr("app.modules.catalog.plugins._plugins_dir", lambda: plugins_dir)

    resolved = resolve_plugin_path("demo/1.0.0")
    assert resolved == (plugins_dir / "demo" / "1.0.0").resolve()
