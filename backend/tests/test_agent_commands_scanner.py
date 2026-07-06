from app.modules.catalog.commands import scan_agent_commands


def test_scan_agent_commands_returns_skills_and_plugin_skills(tmp_path):
    """命令清单来自该智能体独立工作目录,插件技能和命令需要带插件名前缀。"""
    workdir = tmp_path / "agent"
    skill = workdir / "skills" / "local-brain"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(
        "---\nname: brainstorming\ndescription: 本地头脑风暴\n---\n",
        encoding="utf-8",
    )

    plugin = workdir / "plugins" / "superpowers" / "5.1.0"
    (plugin / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        '{"name":"superpowers","version":"5.1.0","description":"Superpowers"}',
        encoding="utf-8",
    )
    plugin_skill = plugin / "skills" / "brainstorming"
    plugin_skill.mkdir(parents=True, exist_ok=True)
    (plugin_skill / "SKILL.md").write_text(
        "---\nname: brainstorming\ndescription: 插件头脑风暴\n---\n",
        encoding="utf-8",
    )
    plugin_command = plugin / "commands"
    plugin_command.mkdir(parents=True, exist_ok=True)
    (plugin_command / "writing-plans.md").write_text(
        "---\ndescription: 编写实施计划\n---\n# Writing Plans\n",
        encoding="utf-8",
    )

    assert scan_agent_commands(workdir) == [
        {
            "name": "brainstorming",
            "description": "本地头脑风暴",
            "source": "skill",
            "plugin": None,
        },
        {
            "name": "superpowers:brainstorming",
            "description": "插件头脑风暴",
            "source": "plugin",
            "plugin": "superpowers",
        },
        {
            "name": "superpowers:writing-plans",
            "description": "编写实施计划",
            "source": "plugin",
            "plugin": "superpowers",
        },
    ]


def test_scan_agent_commands_prioritizes_user_workspace_skills(tmp_path):
    """命令清单应优先展示用户个人空间 skills,再展示智能体技能和插件。"""
    user_workspace = tmp_path / "user"
    personal_skill = user_workspace / ".claude" / "skills" / "personal-writer"
    personal_skill.mkdir(parents=True, exist_ok=True)
    (personal_skill / "SKILL.md").write_text(
        "---\nname: personal-writer\ndescription: 个人写作技能\n---\n",
        encoding="utf-8",
    )

    workdir = tmp_path / "agent"
    agent_skill = workdir / "skills" / "agent-helper"
    agent_skill.mkdir(parents=True, exist_ok=True)
    (agent_skill / "SKILL.md").write_text(
        "---\nname: agent-helper\ndescription: 智能体技能\n---\n",
        encoding="utf-8",
    )

    plugin = workdir / "plugins" / "superpowers"
    (plugin / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        '{"name":"superpowers"}',
        encoding="utf-8",
    )
    plugin_skill = plugin / "skills" / "plugin-helper"
    plugin_skill.mkdir(parents=True, exist_ok=True)
    (plugin_skill / "SKILL.md").write_text(
        "---\nname: plugin-helper\ndescription: 插件技能\n---\n",
        encoding="utf-8",
    )

    assert scan_agent_commands(workdir, user_workspace=user_workspace) == [
        {
            "name": "personal-writer",
            "description": "个人写作技能",
            "source": "personal_skill",
            "plugin": None,
        },
        {
            "name": "agent-helper",
            "description": "智能体技能",
            "source": "skill",
            "plugin": None,
        },
        {
            "name": "superpowers:plugin-helper",
            "description": "插件技能",
            "source": "plugin",
            "plugin": "superpowers",
        },
    ]


def test_scan_agent_commands_returns_empty_for_missing_workdir(tmp_path):
    assert scan_agent_commands(tmp_path / "missing") == []


def test_scan_agent_commands_uses_directory_name_fallbacks(tmp_path):
    """frontmatter 或 manifest 缺字段时使用目录名兜底。"""
    workdir = tmp_path / "agent"
    skill = workdir / "skills" / "plain"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text("# plain\n", encoding="utf-8")

    plugin = workdir / "plugins" / "plugin-dir"
    (plugin / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        "{}",
        encoding="utf-8",
    )
    plugin_skill = plugin / "skills" / "plain-plugin-skill"
    plugin_skill.mkdir(parents=True, exist_ok=True)
    (plugin_skill / "SKILL.md").write_text("# plugin skill\n", encoding="utf-8")

    assert scan_agent_commands(workdir) == [
        {"name": "plain", "description": "", "source": "skill", "plugin": None},
        {
            "name": "plugin-dir:plain-plugin-skill",
            "description": "",
            "source": "plugin",
            "plugin": "plugin-dir",
        },
    ]
