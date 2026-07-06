import pytest


async def test_agent_catalog_endpoints_require_login(client):
    for path in ("/api/agents", "/api/skills", "/api/plugins"):
        r = await client.get(path)
        assert r.status_code == 401


async def test_agent_catalog_endpoints_allow_logged_in_user(logged_in_client):
    for path in ("/api/agents", "/api/skills", "/api/plugins"):
        r = await logged_in_client.get(path)
        assert r.status_code == 200


async def test_agent_mutations_require_admin(logged_in_client):
    c = logged_in_client
    r = await c.post("/api/agents", json={"name": "普通用户创建", "code": "normal-create"})
    assert r.status_code == 403

    for method, path in (
        ("patch", "/api/agents/1"),
        ("delete", "/api/agents/1"),
        ("post", "/api/agents/1/reinit"),
    ):
        if method == "patch":
            r = await c.patch(path, json={"name": "x"})
        elif method == "delete":
            r = await c.delete(path)
        else:
            r = await c.post(path)
        assert r.status_code == 403


async def test_admin_can_create_agent(admin_client):
    r = await admin_client.post(
        "/api/agents",
        json={"name": "管理员创建", "code": "admin-create"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "管理员创建"


async def test_create_and_list_agents(admin_client):
    c = admin_client
    r = await c.post("/api/agents", json={"name": "测试助手", "code": "test-assistant", "system_prompt": "你是一个测试助手", "skills": "employee-management"})
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "测试助手"
    assert data["system_prompt"] == "你是一个测试助手"
    assert data["skills"] == "employee-management"

    r = await c.get("/api/agents")
    assert r.status_code == 200
    agents = r.json()
    assert len(agents) >= 1
    assert any(a["name"] == "测试助手" for a in agents)


async def test_get_agent(admin_client):
    c = admin_client
    r = await c.post("/api/agents", json={"name": "查询测试", "code": "query-test"})
    aid = r.json()["id"]
    r = await c.get(f"/api/agents/{aid}")
    assert r.status_code == 200
    assert r.json()["name"] == "查询测试"


async def test_update_agent(admin_client):
    c = admin_client
    r = await c.post("/api/agents", json={"name": "旧名字", "code": "old-name"})
    aid = r.json()["id"]
    r = await c.patch(f"/api/agents/{aid}", json={"name": "新名字"})
    assert r.status_code == 200
    assert r.json()["name"] == "新名字"


async def test_agent_category_round_trip(admin_client):
    """智能体应复用分类表,支持创建、列表和编辑分类。"""
    c = admin_client
    r = await c.post("/api/admin/categories", json={"name": "研发"})
    assert r.status_code == 201
    dev_category = r.json()
    r = await c.post("/api/admin/categories", json={"name": "销售"})
    assert r.status_code == 201
    sales_category = r.json()

    r = await c.post(
        "/api/agents",
        json={
            "name": "研发助手",
            "code": "dev-agent",
            "category_id": dev_category["id"],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["category_id"] == dev_category["id"]
    assert data["category"] == "研发"
    aid = data["id"]

    r = await c.get("/api/agents")
    assert r.status_code == 200
    listed = next(a for a in r.json() if a["id"] == aid)
    assert listed["category_id"] == dev_category["id"]
    assert listed["category"] == "研发"

    r = await c.patch(
        f"/api/agents/{aid}",
        json={"category_id": sales_category["id"]},
    )
    assert r.status_code == 200
    assert r.json()["category_id"] == sales_category["id"]
    assert r.json()["category"] == "销售"


async def test_agent_category_defaults_to_default(admin_client):
    """未指定分类时,智能体应归入默认分类。"""
    r = await admin_client.post(
        "/api/agents",
        json={"name": "默认分类助手", "code": "default-category-agent"},
    )
    assert r.status_code == 200
    assert r.json()["category"] == "默认"
    assert isinstance(r.json()["category_id"], int)


async def test_delete_agent(admin_client):
    c = admin_client
    r = await c.post("/api/agents", json={"name": "待删除", "code": "to-delete"})
    aid = r.json()["id"]
    r = await c.delete(f"/api/agents/{aid}")
    assert r.status_code == 204
    r = await c.get("/api/agents")
    assert not any(a["id"] == aid for a in r.json())


async def test_agent_plugins_round_trip(admin_client):
    """智能体可以保存、读取和更新 plugins 字段。"""
    c = admin_client
    # 创建时携带 plugins
    r = await c.post(
        "/api/agents",
        json={"name": "带插件的助手", "code": "plugin-assistant", "plugins": "superpowers/5.1.0,custom"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["plugins"] == "superpowers/5.1.0,custom"
    aid = data["id"]

    # GET 应返回相同内容
    r = await c.get(f"/api/agents/{aid}")
    assert r.json()["plugins"] == "superpowers/5.1.0,custom"

    # PATCH 可以单独更新 plugins
    r = await c.patch(f"/api/agents/{aid}", json={"plugins": "only-one"})
    assert r.status_code == 200
    assert r.json()["plugins"] == "only-one"

    # PATCH 不传 plugins 时不应清空
    r = await c.patch(f"/api/agents/{aid}", json={"name": "改个名字"})
    assert r.json()["plugins"] == "only-one"


async def test_agent_default_plugins_empty(admin_client):
    """未传 plugins 时,Agent.plugins 应为空字符串。"""
    c = admin_client
    r = await c.post("/api/agents", json={"name": "无插件助手", "code": "no-plugins"})
    assert r.status_code == 200
    assert r.json()["plugins"] == ""


from pathlib import Path


async def test_post_agent_creates_workdir_with_selected_only(admin_client, tmp_path):
    """POST 后工作目录应只含勾选项 + CLAUDE.md。"""
    # 准备模板源(在测试 cwd 下的 claude_data 中)
    cwd = Path.cwd()  # conftest 已 chdir 到 tmp_path
    (cwd / "claude_data").mkdir(exist_ok=True)
    (cwd / "claude_data" / "CLAUDE.md").write_text("主指令\n", encoding="utf-8")
    (cwd / "claude_data" / "plugins" / "alpha").mkdir(parents=True, exist_ok=True)
    (cwd / "claude_data" / "plugins" / "alpha" / "manifest.json").write_text("{}", encoding="utf-8")
    (cwd / "claude_data" / "skills" / "hello").mkdir(parents=True, exist_ok=True)
    (cwd / "claude_data" / "skills" / "hello" / "SKILL.md").write_text("# hello\n", encoding="utf-8")

    c = admin_client
    r = await c.post(
        "/api/agents",
        json={"name": "目录测试", "code": "dir-test", "plugins": "alpha", "skills": "hello"},
    )
    assert r.status_code == 200
    aid = r.json()["id"]
    wd = cwd / "agent_workspaces" / "dir-test"
    assert (wd / "CLAUDE.md").exists()
    assert (wd / "plugins" / "alpha" / "manifest.json").exists()
    assert (wd / "skills" / "hello" / "SKILL.md").exists()


async def test_patch_agent_diffs_workdir(admin_client, tmp_path):
    cwd = Path.cwd()
    (cwd / "claude_data" / "plugins" / "alpha").mkdir(parents=True, exist_ok=True)
    (cwd / "claude_data" / "plugins" / "alpha" / "manifest.json").write_text("{}", encoding="utf-8")
    (cwd / "claude_data" / "plugins" / "beta").mkdir(parents=True, exist_ok=True)
    (cwd / "claude_data" / "plugins" / "beta" / "manifest.json").write_text("{}", encoding="utf-8")

    c = admin_client
    r = await c.post("/api/agents", json={"name": "差量", "code": "diff-test", "plugins": "alpha"})
    aid = r.json()["id"]
    wd = cwd / "agent_workspaces" / "diff-test"
    assert (wd / "plugins" / "alpha").exists()

    r = await c.patch(f"/api/agents/{aid}", json={"plugins": "beta"})
    assert r.status_code == 200
    assert not (wd / "plugins" / "alpha").exists()
    assert (wd / "plugins" / "beta").exists()


async def test_delete_agent_removes_workdir(admin_client, tmp_path):
    cwd = Path.cwd()
    c = admin_client
    r = await c.post("/api/agents", json={"name": "待删", "code": "to-delete-wd"})
    aid = r.json()["id"]
    wd = cwd / "agent_workspaces" / "to-delete-wd"
    assert wd.exists()

    r = await c.delete(f"/api/agents/{aid}")
    assert r.status_code == 204
    assert not wd.exists()


async def test_reinit_endpoint_refreshes_three_targets_only(admin_client, tmp_path):
    cwd = Path.cwd()
    (cwd / "claude_data").mkdir(exist_ok=True)
    (cwd / "claude_data" / "CLAUDE.md").write_text("主指令\n", encoding="utf-8")
    (cwd / "claude_data" / "plugins" / "alpha").mkdir(parents=True, exist_ok=True)
    (cwd / "claude_data" / "plugins" / "alpha" / "manifest.json").write_text("{}", encoding="utf-8")

    c = admin_client
    r = await c.post("/api/agents", json={"name": "刷新测试", "code": "refresh-test", "plugins": "alpha"})
    aid = r.json()["id"]
    wd = cwd / "agent_workspaces" / "refresh-test"

    # 模拟 SDK 产物
    sdk_jsonl = wd / "projects" / "user" / "session.jsonl"
    sdk_jsonl.parent.mkdir(parents=True, exist_ok=True)
    sdk_jsonl.write_text('{"role":"user"}\n', encoding="utf-8")

    # 主目录升级
    (cwd / "claude_data" / "CLAUDE.md").write_text("v2\n", encoding="utf-8")

    r = await c.post(f"/api/agents/{aid}/reinit")
    assert r.status_code == 200
    # SDK 产物保留
    assert sdk_jsonl.read_text(encoding="utf-8") == '{"role":"user"}\n'
    # CLAUDE.md 已刷新
    assert (wd / "CLAUDE.md").read_text(encoding="utf-8") == "v2\n"


async def test_create_agent_code_format(admin_client):
    """代号只能包含字母、数字、_、-"""
    c = admin_client
    res = await c.post("/api/agents", json={
        "name": "测试",
        "code": "invalid@code",
    })
    assert res.status_code == 422


async def test_create_agent_code_unique(admin_client):
    """代号必须全局唯一"""
    c = admin_client
    res1 = await c.post("/api/agents", json={
        "name": "A",
        "code": "same-code",
    })
    assert res1.status_code == 200

    res2 = await c.post("/api/agents", json={
        "name": "B",
        "code": "same-code",
    })
    assert res2.status_code == 409


async def test_agent_commands_endpoint_returns_selected_workdir_commands(admin_client):
    """API 只返回该智能体工作目录中实际存在的命令。"""
    from pathlib import Path

    cwd = Path.cwd()
    selected = cwd / "claude_data" / "skills" / "selected"
    selected.mkdir(parents=True, exist_ok=True)
    (selected / "SKILL.md").write_text(
        "---\nname: selected\ndescription: 已选择\n---\n",
        encoding="utf-8",
    )
    unselected = cwd / "claude_data" / "skills" / "unselected"
    unselected.mkdir(parents=True, exist_ok=True)
    (unselected / "SKILL.md").write_text(
        "---\nname: unselected\ndescription: 未选择\n---\n",
        encoding="utf-8",
    )

    plugin = cwd / "claude_data" / "plugins" / "superpowers" / "5.1.0"
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

    r = await admin_client.post(
        "/api/agents",
        json={
            "name": "命令助手",
            "code": "command-agent",
            "skills": "selected",
            "plugins": "superpowers/5.1.0",
        },
    )
    aid = r.json()["id"]

    r = await admin_client.get(f"/api/agents/{aid}/commands")
    assert r.status_code == 200
    assert r.json() == [
        {
            "name": "selected",
            "description": "已选择",
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


async def test_agent_commands_endpoint_prioritizes_current_user_skills(admin_client):
    """命令 API 应把当前用户个人空间 skills 排在智能体技能和插件之前。"""
    from pathlib import Path

    cwd = Path.cwd()
    personal = cwd / "user_workspaces" / "admin_user" / ".claude" / "skills" / "personal-helper"
    personal.mkdir(parents=True, exist_ok=True)
    (personal / "SKILL.md").write_text(
        "---\nname: personal-helper\ndescription: 个人技能\n---\n",
        encoding="utf-8",
    )

    selected = cwd / "claude_data" / "skills" / "agent-helper"
    selected.mkdir(parents=True, exist_ok=True)
    (selected / "SKILL.md").write_text(
        "---\nname: agent-helper\ndescription: 智能体技能\n---\n",
        encoding="utf-8",
    )

    plugin = cwd / "claude_data" / "plugins" / "superpowers"
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

    r = await admin_client.post(
        "/api/agents",
        json={
            "name": "个人命令助手",
            "code": "personal-command-agent",
            "skills": "agent-helper",
            "plugins": "superpowers",
        },
    )
    aid = r.json()["id"]

    r = await admin_client.get(f"/api/agents/{aid}/commands")

    assert r.status_code == 200
    assert r.json() == [
        {
            "name": "personal-helper",
            "description": "个人技能",
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


async def test_agent_commands_endpoint_missing_agent_returns_404(logged_in_client):
    r = await logged_in_client.get("/api/agents/999999/commands")
    assert r.status_code == 404


async def test_agent_commands_endpoint_missing_workdir_returns_empty(admin_client):
    from pathlib import Path
    import shutil

    r = await admin_client.post(
        "/api/agents",
        json={"name": "无目录", "code": "missing-command-workdir"},
    )
    aid = r.json()["id"]
    shutil.rmtree(Path.cwd() / "agent_workspaces" / "missing-command-workdir")

    r = await admin_client.get(f"/api/agents/{aid}/commands")
    assert r.status_code == 200
    assert r.json() == []
