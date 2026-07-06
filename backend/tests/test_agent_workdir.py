"""智能体独立工作目录工具模块的测试。"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest


@pytest.fixture
def setup_env(monkeypatch, tmp_path):
    """配置最小环境,加载 config/agent_workdir 模块。"""
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://x")
    monkeypatch.chdir(tmp_path)
    from importlib import reload
    from app.core import config as core_config
    reload(core_config)
    from app.modules.agents import workdir as agent_workdir
    reload(agent_workdir)
    return tmp_path, core_config, agent_workdir


def test_get_agent_workdir_returns_absolute_path(setup_env):
    tmp_path, _, agent_workdir = setup_env
    p = agent_workdir.get_agent_workdir("my-agent")
    # 应该是 tmp_path / agent_workspaces / my-agent 的绝对路径
    assert p == (tmp_path / "agent_workspaces" / "my-agent").resolve()
    assert p.is_absolute()


async def test_override_claude_config_dir_sets_and_restores(setup_env):
    tmp_path, _, agent_workdir = setup_env
    workdir = tmp_path / "agent_workspaces" / "gokagent"
    workdir.mkdir(parents=True)
    original = os.environ.get("CLAUDE_CONFIG_DIR")
    async with agent_workdir.override_claude_config_dir(workdir):
        assert os.environ["CLAUDE_CONFIG_DIR"] == str(workdir)
    # 退出后恢复
    assert os.environ.get("CLAUDE_CONFIG_DIR") == original


async def test_override_claude_config_dir_serializes_concurrent(setup_env):
    """并发的 override 应通过模块级 Lock 串行化,避免互相污染 os.environ。"""
    tmp_path, _, agent_workdir = setup_env
    wd_a = tmp_path / "agent_workspaces" / "a"
    wd_b = tmp_path / "agent_workspaces" / "b"
    wd_a.mkdir(parents=True)
    wd_b.mkdir(parents=True)
    observed: list[str] = []

    async def use(workdir: Path) -> None:
        async with agent_workdir.override_claude_config_dir(workdir):
            observed.append(os.environ["CLAUDE_CONFIG_DIR"])
            await asyncio.sleep(0.01)
            # 仍应保持自己的设置,不被并发任务覆盖
            assert os.environ["CLAUDE_CONFIG_DIR"] == str(workdir)

    await asyncio.gather(use(wd_a), use(wd_b), use(wd_a))
    assert sorted(observed) == sorted([str(wd_a), str(wd_b), str(wd_a)])


def _setup_template(claude_data: Path, *, with_claude_md: bool = True) -> None:
    """在 tmp_path/claude_data 下构造一个模板源:CLAUDE.md + 2 个插件 + 2 个技能。"""
    claude_data.mkdir(parents=True, exist_ok=True)
    if with_claude_md:
        (claude_data / "CLAUDE.md").write_text("主指令\n", encoding="utf-8")
    plugins_root = claude_data / "plugins"
    plugins_root.mkdir(exist_ok=True)
    for rel in ("alpha", "scoped/beta"):
        d = plugins_root / rel
        d.mkdir(parents=True, exist_ok=True)
        (d / "manifest.json").write_text("{}", encoding="utf-8")
    skills_root = claude_data / "skills"
    skills_root.mkdir(exist_ok=True)
    for name in ("hello", "world"):
        d = skills_root / name
        d.mkdir(exist_ok=True)
        (d / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")


class _FakeAgent:
    """测试用 Agent stub,字段与 ORM Agent 对齐。"""
    def __init__(self, id: int, code: str, plugins: str = "", skills: str = "") -> None:
        self.id = id
        self.code = code
        self.plugins = plugins
        self.skills = skills


def test_init_agent_workdir_copies_selected_only(setup_env):
    tmp_path, _, agent_workdir = setup_env
    _setup_template(tmp_path / "claude_data")

    agent = _FakeAgent(1, "gokagent", plugins="alpha,scoped/beta", skills="hello")
    agent_workdir.init_agent_workdir(agent)

    wd = tmp_path / "agent_workspaces" / "gokagent"
    # CLAUDE.md 始终拷贝
    assert (wd / "CLAUDE.md").read_text(encoding="utf-8") == "主指令\n"
    # 仅勾选的插件被拷贝
    assert (wd / "plugins" / "alpha" / "manifest.json").exists()
    assert (wd / "plugins" / "scoped" / "beta" / "manifest.json").exists()
    # 仅勾选的技能被拷贝
    assert (wd / "skills" / "hello" / "SKILL.md").exists()
    assert not (wd / "skills" / "world").exists()


def test_init_agent_workdir_idempotent(setup_env):
    """重复调用应保持稳定,不抛错。"""
    tmp_path, _, agent_workdir = setup_env
    _setup_template(tmp_path / "claude_data")
    agent = _FakeAgent(2, "agent-2", plugins="alpha", skills="hello")
    agent_workdir.init_agent_workdir(agent)
    agent_workdir.init_agent_workdir(agent)  # 第二次应无副作用
    wd = tmp_path / "agent_workspaces" / "agent-2"
    assert (wd / "plugins" / "alpha" / "manifest.json").exists()


def test_init_agent_workdir_missing_template_does_not_raise(setup_env):
    """模板源缺 CLAUDE.md / 缺勾选项 时,跳过 + 不抛错。"""
    tmp_path, _, agent_workdir = setup_env
    _setup_template(tmp_path / "claude_data", with_claude_md=False)
    agent = _FakeAgent(3, "agent-3", plugins="alpha,does-not-exist", skills="missing-skill")
    agent_workdir.init_agent_workdir(agent)  # 不应抛错

    wd = tmp_path / "agent_workspaces" / "agent-3"
    # CLAUDE.md 缺失则不拷贝
    assert not (wd / "CLAUDE.md").exists()
    # 缺失插件/技能被跳过
    assert (wd / "plugins" / "alpha" / "manifest.json").exists()
    assert not (wd / "plugins" / "does-not-exist").exists()
    assert not (wd / "skills" / "missing-skill").exists()


def test_sync_agent_selection_add_only(setup_env):
    """只新增勾选时,只动新增项,旧文件保留。"""
    tmp_path, _, agent_workdir = setup_env
    _setup_template(tmp_path / "claude_data")

    agent = _FakeAgent(10, "agent-10", plugins="alpha", skills="")
    agent_workdir.init_agent_workdir(agent)
    # 在 plugins/alpha 内放一个"用户产物",验证 sync 不会误删
    wd = tmp_path / "agent_workspaces" / "agent-10"
    (wd / "plugins" / "alpha" / "user-note.txt").write_text("keep me", encoding="utf-8")

    # 模拟用户在前端新增勾选 scoped/beta + hello
    agent.plugins = "alpha,scoped/beta"
    agent.skills = "hello"
    agent_workdir.sync_agent_selection(agent, old_plugins="alpha", old_skills="")

    assert (wd / "plugins" / "alpha" / "user-note.txt").read_text(encoding="utf-8") == "keep me"
    assert (wd / "plugins" / "scoped" / "beta" / "manifest.json").exists()
    assert (wd / "skills" / "hello" / "SKILL.md").exists()


def test_sync_agent_selection_remove_only(setup_env):
    """取消勾选时,只删该项目录,plugins/ 整体保留。"""
    tmp_path, _, agent_workdir = setup_env
    _setup_template(tmp_path / "claude_data")

    agent = _FakeAgent(11, "agent-11", plugins="alpha,scoped/beta", skills="hello,world")
    agent_workdir.init_agent_workdir(agent)
    wd = tmp_path / "agent_workspaces" / "agent-11"

    agent.plugins = "alpha"
    agent.skills = "hello"
    agent_workdir.sync_agent_selection(
        agent, old_plugins="alpha,scoped/beta", old_skills="hello,world"
    )

    # 保留项依然在
    assert (wd / "plugins" / "alpha" / "manifest.json").exists()
    assert (wd / "skills" / "hello" / "SKILL.md").exists()
    # 取消项被删
    assert not (wd / "plugins" / "scoped" / "beta").exists()
    assert not (wd / "skills" / "world").exists()
    # plugins/ skills/ 根目录依然存在
    assert (wd / "plugins").is_dir()
    assert (wd / "skills").is_dir()


def test_sync_agent_selection_mixed(setup_env):
    """混合 ADD 与 REMOVE,仅动差量。"""
    tmp_path, _, agent_workdir = setup_env
    _setup_template(tmp_path / "claude_data")

    agent = _FakeAgent(12, "agent-12", plugins="alpha", skills="hello")
    agent_workdir.init_agent_workdir(agent)
    wd = tmp_path / "agent_workspaces" / "agent-12"

    agent.plugins = "scoped/beta"
    agent.skills = "world"
    agent_workdir.sync_agent_selection(
        agent, old_plugins="alpha", old_skills="hello"
    )

    assert not (wd / "plugins" / "alpha").exists()
    assert (wd / "plugins" / "scoped" / "beta" / "manifest.json").exists()
    assert not (wd / "skills" / "hello").exists()
    assert (wd / "skills" / "world" / "SKILL.md").exists()


def test_reinit_agent_workdir_preserves_projects(setup_env):
    """reinit 只刷新 plugins/、skills/、CLAUDE.md,projects/ 等 SDK 产物保留。"""
    tmp_path, _, agent_workdir = setup_env
    _setup_template(tmp_path / "claude_data")

    agent = _FakeAgent(20, "agent-20", plugins="alpha", skills="hello")
    agent_workdir.init_agent_workdir(agent)
    wd = tmp_path / "agent_workspaces" / "agent-20"

    # 模拟 SDK 产生的会话文件
    sdk_jsonl = wd / "projects" / "-tmp-ws" / "session.jsonl"
    sdk_jsonl.parent.mkdir(parents=True, exist_ok=True)
    sdk_jsonl.write_text('{"role":"user"}\n', encoding="utf-8")

    # 主目录升级:hello 新内容,新增 brand-new 插件
    (tmp_path / "claude_data" / "skills" / "hello" / "SKILL.md").write_text(
        "# hello v2\n", encoding="utf-8"
    )
    (tmp_path / "claude_data" / "CLAUDE.md").write_text("主指令 v2\n", encoding="utf-8")

    # 用户加新勾选
    agent.plugins = "alpha,scoped/beta"

    agent_workdir.reinit_agent_workdir(agent)

    # 会话历史保留 — 关键断言
    assert sdk_jsonl.read_text(encoding="utf-8") == '{"role":"user"}\n'
    # CLAUDE.md 已刷新为 v2
    assert (wd / "CLAUDE.md").read_text(encoding="utf-8") == "主指令 v2\n"
    # skills/hello 已刷新为 v2
    assert (wd / "skills" / "hello" / "SKILL.md").read_text(encoding="utf-8") == "# hello v2\n"
    # 新增勾选已拷贝
    assert (wd / "plugins" / "scoped" / "beta" / "manifest.json").exists()
    # 旧的 plugins/alpha 仍存在(因为仍勾选)
    assert (wd / "plugins" / "alpha" / "manifest.json").exists()


def test_reinit_agent_workdir_cleans_unselected(setup_env):
    """reinit 后,工作目录的 plugins/skills 完全反映当前勾选,不留旧项。"""
    tmp_path, _, agent_workdir = setup_env
    _setup_template(tmp_path / "claude_data")

    agent = _FakeAgent(21, "agent-21", plugins="alpha,scoped/beta", skills="hello,world")
    agent_workdir.init_agent_workdir(agent)
    wd = tmp_path / "agent_workspaces" / "agent-21"

    # 用户取消勾选 scoped/beta 与 world,然后 reinit
    agent.plugins = "alpha"
    agent.skills = "hello"
    agent_workdir.reinit_agent_workdir(agent)

    assert (wd / "plugins" / "alpha").exists()
    assert not (wd / "plugins" / "scoped").exists()
    assert (wd / "skills" / "hello").exists()
    assert not (wd / "skills" / "world").exists()


def test_remove_agent_workdir(setup_env):
    tmp_path, _, agent_workdir = setup_env
    _setup_template(tmp_path / "claude_data")
    agent = _FakeAgent(30, "agent-30", plugins="alpha")
    agent_workdir.init_agent_workdir(agent)
    wd = tmp_path / "agent_workspaces" / "agent-30"
    assert wd.exists()

    agent_workdir.remove_agent_workdir("agent-30")
    assert not wd.exists()


def test_remove_agent_workdir_missing_is_safe(setup_env):
    """目录不存在不抛错。"""
    _, _, agent_workdir = setup_env
    agent_workdir.remove_agent_workdir("nonexistent")  # 不应抛错


async def test_ensure_all_agent_workdirs_creates_missing(setup_env):
    """启动钩子应为 DB 中所有缺工作目录的 Agent 兜底初始化。"""
    tmp_path, core_config, agent_workdir = setup_env
    _setup_template(tmp_path / "claude_data")

    from importlib import reload
    from app.db import base as db_base, session as db_session, migrations as db_migrations
    from app.models import agent as model_agent, category as model_category, session as model_session, team_space as model_team_space, user as model_user
    reload(db_base)
    reload(db_session)
    reload(db_migrations)
    reload(model_agent)
    reload(model_category)
    reload(model_session)
    reload(model_team_space)
    reload(model_user)
    import app.db as db_pkg
    reload(db_pkg)
    await db_pkg.init_db()

    # 模拟一个用户创建的 Agent(没有 workdir)
    from app.models import Agent
    async with db_pkg.async_session() as s:
        a = Agent(name="待补", code="pending-fix-wd", system_prompt=None, skills="hello", plugins="alpha")
        s.add(a)
        await s.commit()
        await s.refresh(a)
        aid = a.id

    await agent_workdir.ensure_all_agent_workdirs()
    assert (tmp_path / "agent_workspaces" / "pending-fix-wd" / "plugins" / "alpha" / "manifest.json").exists()
    # 默认 Agent 也应被初始化(skills/plugins 为空 → 仅 CLAUDE.md)
    assert (tmp_path / "agent_workspaces" / "default-agent" / "CLAUDE.md").exists()

    await db_pkg.engine.dispose()
