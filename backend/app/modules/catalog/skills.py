"""扫描 CLAUDE_CONFIG_DIR/skills 目录，返回技能清单。"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import get_settings


def _skills_dir() -> Path:
    return get_settings().claude_data_dir / "skills"


def scan_skills() -> list[dict]:
    """遍历 skills 目录，读取每个子目录的 SKILL.md 提取 name 和 description。"""
    root = _skills_dir()
    if not root.exists():
        return []

    results: list[dict] = []
    for subdir in sorted(root.iterdir()):
        if not subdir.is_dir():
            continue
        skill_md = subdir / "SKILL.md"
        if not skill_md.exists():
            continue
        text = skill_md.read_text(encoding="utf-8")
        name = subdir.name
        description = ""
        # 匹配 YAML frontmatter
        m = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if m:
            front = m.group(1)
            name_match = re.search(r"^name:\s*(.+)$", front, re.MULTILINE)
            if name_match:
                name = name_match.group(1).strip()
            desc_match = re.search(r"^description:\s*(.+)$", front, re.MULTILINE)
            if desc_match:
                description = desc_match.group(1).strip()
        results.append({"name": name, "description": description})
    return results
