"""扫描 claude_data_dir/plugins 目录,返回可被智能体引用的插件清单。

约定每个插件根目录都包含 ``.claude-plugin/plugin.json`` (参考 Claude Agent SDK
插件规范)。目录可以是 ``plugins/<name>/`` 这种平铺布局,也可以是
``plugins/<name>/<version>/`` 这种带版本的布局,扫描时统一向下找两层。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_settings

# rglob 可能误入插件内部的子插件,这里限制相对深度,避免重复展示
_MAX_DEPTH = 3


def _plugins_dir() -> Path:
    return get_settings().claude_data_dir / "plugins"


def scan_plugins() -> list[dict]:
    """返回插件列表 ``[{name, version, description, path}]``。

    path 是相对于 plugins 根目录的 POSIX 路径(例如 ``superpowers/5.1.0``),
    与数据库中 Agent.plugins 字段的存储形式保持一致;运行时再通过
    ``claude_data_dir / "plugins" / path`` 还原为绝对路径传给 SDK。
    """
    root = _plugins_dir()
    if not root.exists():
        return []

    results: list[dict] = []
    seen: set[str] = set()
    for manifest_path in sorted(root.rglob(".claude-plugin/plugin.json")):
        plugin_root = manifest_path.parent.parent
        try:
            rel = plugin_root.relative_to(root)
        except ValueError:
            continue
        # 深度过深通常意味着扫到了某插件内部捆绑的另一个插件,忽略
        if len(rel.parts) == 0 or len(rel.parts) > _MAX_DEPTH:
            continue
        rel_str = rel.as_posix()
        if rel_str in seen:
            continue
        seen.add(rel_str)
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        results.append(
            {
                "name": str(data.get("name") or plugin_root.name),
                "version": str(data.get("version") or ""),
                "description": str(data.get("description") or ""),
                "path": rel_str,
            }
        )
    return results


def resolve_plugin_path(rel_path: str) -> Path:
    """把数据库中的相对路径解析为绝对插件根目录。"""
    return (_plugins_dir() / rel_path).resolve()
