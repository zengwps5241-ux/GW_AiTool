import pytest
from pathlib import Path
from app.modules.catalog.skills import scan_skills


async def test_scan_skills_reads_directory(monkeypatch, tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_dir = skills_dir / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: A test skill\n---\n# Test", encoding="utf-8"
    )
    monkeypatch.setattr("app.modules.catalog.skills._skills_dir", lambda: skills_dir)
    result = scan_skills()
    assert len(result) == 1
    assert result[0]["name"] == "test-skill"
    assert result[0]["description"] == "A test skill"
