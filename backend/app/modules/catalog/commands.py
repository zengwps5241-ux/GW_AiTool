"""扫描单个智能体工作目录中的 slash command 清单。"""

from __future__ import annotations

import json
import re
from pathlib import Path

_PLUGIN_MANIFEST = ".claude-plugin/plugin.json"


def _frontmatter_value(text: str, key: str) -> str | None:
    """读取 SKILL.md YAML frontmatter 中的简单字符串字段。"""
    match = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return None
    frontmatter = match.group(1)
    value_match = re.search(rf"^{re.escape(key)}:\s*(.+)$", frontmatter, re.MULTILINE)
    if not value_match:
        return None
    return value_match.group(1).strip().strip('"').strip("'")


def _read_skill_meta(skill_dir: Path) -> tuple[str, str] | None:
    """返回 (name, description);无法读取 SKILL.md 时返回 None。"""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return None
    name = _frontmatter_value(text, "name") or skill_dir.name
    description = _frontmatter_value(text, "description") or ""
    return name, description


def _read_plugin_name(plugin_root: Path) -> str:
    """读取插件名;manifest 异常时使用插件根目录名兜底。"""
    manifest = plugin_root / _PLUGIN_MANIFEST
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return plugin_root.name
    if not isinstance(data, dict):
        return plugin_root.name
    return str(data.get("name") or plugin_root.name)


def _find_plugin_root(path: Path, workdir: Path) -> Path | None:
    """从插件内文件向上找最近的插件根目录。"""
    for parent in path.parents:
        if parent == workdir:
            return None
        if (parent / _PLUGIN_MANIFEST).exists():
            return parent
    return None


def _read_markdown_command_meta(command_md: Path) -> tuple[str, str] | None:
    """返回 (name, description);无法读取命令 markdown 时返回 None。"""
    try:
        text = command_md.read_text(encoding="utf-8")
    except OSError:
        return None
    name = command_md.stem
    description = _frontmatter_value(text, "description") or ""
    return name, description


def _scan_skills(skills_root: Path, source: str) -> list[dict]:
    """扫描指定 skills 目录，并标记来源。"""
    commands: list[dict] = []
    if not skills_root.exists():
        return commands
    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        meta = _read_skill_meta(skill_dir)
        if meta is None:
            continue
        name, description = meta
        commands.append(
            {
                "name": name,
                "description": description,
                "source": source,
                "plugin": None,
            }
        )
    return commands


def scan_agent_commands(workdir: Path, user_workspace: Path | None = None) -> list[dict]:
    """扫描 Agent 工作目录,返回可用于输入框提示的命令列表。"""
    if not workdir.exists() and (user_workspace is None or not user_workspace.exists()):
        return []

    commands: list[dict] = []

    if user_workspace is not None:
        commands.extend(_scan_skills(user_workspace / ".claude" / "skills", "personal_skill"))

    commands.extend(_scan_skills(workdir / "skills", "skill"))

    plugins_root = workdir / "plugins"
    if plugins_root.exists():
        for skill_md in sorted(plugins_root.rglob("skills/*/SKILL.md")):
            plugin_root = _find_plugin_root(skill_md, workdir)
            if plugin_root is None:
                continue
            meta = _read_skill_meta(skill_md.parent)
            if meta is None:
                continue
            skill_name, description = meta
            plugin_name = _read_plugin_name(plugin_root)
            commands.append(
                {
                    "name": f"{plugin_name}:{skill_name}",
                    "description": description,
                    "source": "plugin",
                    "plugin": plugin_name,
                }
            )
        for command_md in sorted(plugins_root.rglob("commands/*.md")):
            plugin_root = _find_plugin_root(command_md, workdir)
            if plugin_root is None:
                continue
            meta = _read_markdown_command_meta(command_md)
            if meta is None:
                continue
            command_name, description = meta
            plugin_name = _read_plugin_name(plugin_root)
            commands.append(
                {
                    "name": f"{plugin_name}:{command_name}",
                    "description": description,
                    "source": "plugin",
                    "plugin": plugin_name,
                }
            )

    source_rank = {"personal_skill": 0, "skill": 1, "plugin": 2}
    return sorted(commands, key=lambda item: (source_rank[item["source"]], item["name"]))
