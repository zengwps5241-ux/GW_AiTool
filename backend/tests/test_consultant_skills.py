"""M3.2 七个顾问 Skill 校验测试。

校验交付物本身（SKILL.md 文件）：
- 7 个技能目录与 SKILL.md 齐备
- frontmatter（name/description）可被 scan_skills 解析
- 名称与项目 Agent 绑定的 DEFAULT_PROJECT_SKILLS 一致（M1.3.7）
- 产出结构化草稿的 Skill 指示调用正确的草稿工具
- seed_default_skills 能把模板播种到运行时 master 目录

不依赖真实 Claude 会话；master 模板版本化存放于 app/skills_seed（claude_data/ 被 gitignore）。
"""

import re
from pathlib import Path

import pytest

# 版本化 master 模板目录：backend/tests → backend/app/skills_seed
SKILLS_DIR = Path(__file__).resolve().parent.parent / "app" / "skills_seed"

# 7 个 Skill：名称 → (WF 编码, 产出草稿的关键工具裸名或 None)
EXPECTED_SKILLS = {
    "consultant-upload": ("WF02", None),
    "consultant-gap-check": ("WF03", None),
    "consultant-visit-plan": ("WF06", None),
    "consultant-hypothesis-map": ("WF07", "save_hypothesis_map_stage"),
    "consultant-interview": ("WF09", "save_visit_record_draft"),
    "consultant-verify": ("WF10", "save_business_map_draft"),
    "consultant-stakeholder": ("WF12", "save_stakeholder_card_draft"),
}


def _parse_frontmatter(text: str) -> tuple[str, str]:
    """复用 scan_skills 的 frontmatter 解析逻辑，返回 (name, description)。"""
    m = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    assert m, "SKILL.md 缺少 YAML frontmatter"
    front = m.group(1)
    name = re.search(r"^name:\s*(.+)$", front, re.MULTILINE)
    desc = re.search(r"^description:\s*(.+)$", front, re.MULTILINE)
    return (name.group(1).strip() if name else "", desc.group(1).strip() if desc else "")


def test_seven_skill_files_exist():
    """7 个技能目录各含 SKILL.md。"""
    for skill_name in EXPECTED_SKILLS:
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        assert skill_md.exists(), f"缺少技能文件：{skill_md}"


def test_skill_names_match_default_project_skills():
    """技能目录名与项目 Agent 绑定的 DEFAULT_PROJECT_SKILLS 完全一致（M1.3.7）。"""
    from app.modules.projects.service import DEFAULT_PROJECT_SKILLS

    bound = {s.strip() for s in DEFAULT_PROJECT_SKILLS.split(",") if s.strip()}
    assert bound == set(EXPECTED_SKILLS), (
        f"绑定技能集合与 M3.2 交付不一致：绑定={sorted(bound)} 交付={sorted(EXPECTED_SKILLS)}"
    )


@pytest.mark.parametrize(
    "skill_name,wf_code,draft_tool",
    [(name, wf, tool) for name, (wf, tool) in EXPECTED_SKILLS.items()],
)
def test_each_skill_frontmatter_and_wf_code(skill_name, wf_code, draft_tool):
    """每个 SKILL.md：frontmatter name=目录名、description 非空、正文含 WF 编码。"""
    text = (SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
    name, desc = _parse_frontmatter(text)
    assert name == skill_name, f"{skill_name}: frontmatter name={name} 与目录名不符"
    assert desc, f"{skill_name}: description 为空"
    assert wf_code in text, f"{skill_name}: 正文未提及 {wf_code}"


@pytest.mark.parametrize(
    "skill_name,draft_tool",
    [(name, tool) for name, (wf, tool) in EXPECTED_SKILLS.items() if tool is not None],
)
def test_draft_skills_reference_correct_tool(skill_name, draft_tool):
    """产出结构化草稿的 Skill 必须指示调用对应草稿工具。"""
    text = (SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
    # 草稿工具在 Claude 侧的调用名为 mcp__consultant_drafts__<tool>（裸名也应出现）
    assert draft_tool in text, (
        f"{skill_name}: 未指示调用草稿工具 {draft_tool}（M3.2 要求 SKILL.md 指示调 save_xxx_draft）"
    )
    assert "mcp__consultant_drafts__" in text or draft_tool in text


@pytest.mark.parametrize(
    "skill_name",
    [k for k, v in EXPECTED_SKILLS.items() if v[1] is None],
)
def test_non_draft_skills_do_not_claim_draft_tool(skill_name):
    """不产出结构化草稿的 Skill（WF02/03/06）不应指示调用 save_xxx_draft。"""
    text = (SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
    for tool in (
        "save_business_map_draft",
        "save_stakeholder_card_draft",
        "save_visit_record_draft",
    ):
        assert tool not in text, f"{skill_name}: 不应引用草稿工具 {tool}"


def test_scan_skills_discovers_all_seven(monkeypatch):
    """scan_skills() 能解析出全部 7 个技能（name + description）。"""
    from app.modules.catalog import skills as skills_module

    monkeypatch.setattr(skills_module, "_skills_dir", lambda: SKILLS_DIR)
    result = {s["name"]: s["description"] for s in skills_module.scan_skills()}
    for skill_name in EXPECTED_SKILLS:
        assert skill_name in result, f"scan_skills 未发现 {skill_name}"
        assert result[skill_name], f"{skill_name}: scan_skills 解析的 description 为空"


def test_seed_default_skills_copies_templates(app_env):
    """seed_default_skills() 把 app/skills_seed 模板播种到运行时 master 目录（claude_data/skills）。"""
    from app.core.config import get_settings
    from app.modules.agents.workdir import seed_default_skills

    master = get_settings().claude_data_dir / "skills"

    seed_default_skills()

    # 7 个模板都被播种
    seeded = {p.name for p in master.iterdir() if p.is_dir()}
    for skill_name in EXPECTED_SKILLS:
        assert skill_name in seeded, f"seed 未播种 {skill_name}"
        assert (master / skill_name / "SKILL.md").exists()

    # 非破坏性：再次播种不覆盖（用占位文件验证跳过逻辑）
    placeholder = master / "consultant-upload" / "SKILL.md"
    placeholder.write_text("---\nname: custom\n---\n用户自定义", encoding="utf-8")
    seed_default_skills()
    assert "用户自定义" in placeholder.read_text(encoding="utf-8")
