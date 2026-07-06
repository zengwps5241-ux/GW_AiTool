"""智能体独立工作目录管理。

每个智能体在 `Settings.agent_workdirs_dir/<agent_id>/` 下拥有一份独立的
`CLAUDE_CONFIG_DIR`,运行时拷贝主目录(`Settings.claude_data_dir`)中勾选
的 plugins、skills 以及 CLAUDE.md。
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

from app.core.config import get_settings

# 串行化对 os.environ["CLAUDE_CONFIG_DIR"] 的临时修改,避免并发协程互相污染。
# 仅供 load_history / remove_session 这类必须走 SDK 全局 env 的工具函数使用;
# 对话流主路径由 ClaudeAgentOptions.env 注入,不经过这里。
_env_lock = asyncio.Lock()


def get_agent_workdir(code: str) -> Path:
    """返回该智能体的工作目录绝对路径(可能尚未在文件系统中存在)。"""
    return (get_settings().agent_workdirs_dir / code).resolve()


@contextlib.asynccontextmanager
async def override_claude_config_dir(workdir: Path) -> AsyncIterator[None]:
    """临时把 os.environ['CLAUDE_CONFIG_DIR'] 切到 workdir,退出时恢复。

    用法:
        async with override_claude_config_dir(get_agent_workdir(agent.id)):
            ...  # 调用 SDK 的 get_session_messages / delete_session 等
    """
    async with _env_lock:
        original = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = str(workdir)
        try:
            yield
        finally:
            if original is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = original


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


def _copy_template_item(src: Path, dst: Path) -> bool:
    """将模板源 src 拷贝到 dst;src 不存在则返回 False。"""
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    return True


def init_agent_workdir(agent) -> None:  # noqa: ANN001 — 容忍 ORM 或 stub
    """按 agent 当前的 plugins/skills 勾选,从主目录拷贝到独立工作目录。

    缺失的模板源会被静默跳过(创建/同步流程容错)。
    """
    settings = get_settings()
    workdir = get_agent_workdir(agent.code)
    workdir.mkdir(parents=True, exist_ok=True)

    # CLAUDE.md 始终尝试拷贝(主目录有就拷,没就跳过)
    _copy_template_item(
        settings.claude_data_dir / "CLAUDE.md",
        workdir / "CLAUDE.md",
    )

    # 勾选的 plugins
    for rel in _parse_csv(getattr(agent, "plugins", None)):
        _copy_template_item(
            settings.claude_data_dir / "plugins" / rel,
            workdir / "plugins" / rel,
        )

    # 勾选的 skills
    for name in _parse_csv(getattr(agent, "skills", None)):
        _copy_template_item(
            settings.claude_data_dir / "skills" / name,
            workdir / "skills" / name,
        )


def _remove_path(p: Path) -> None:
    """安全删除 p:目录走 rmtree,文件走 unlink;不存在则忽略;失败则忽略。"""
    if not p.exists():
        return
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    else:
        try:
            p.unlink()
        except OSError:
            pass


def sync_agent_selection(
    agent,  # noqa: ANN001
    *,
    old_plugins: str | None,
    old_skills: str | None,
) -> None:
    """根据勾选差量更新工作目录。

    ADD = new - old → copytree
    REMOVE = old - new → rmtree(workdir/<kind>/<name>)
    """
    settings = get_settings()
    workdir = get_agent_workdir(agent.code)
    workdir.mkdir(parents=True, exist_ok=True)

    old_p, new_p = set(_parse_csv(old_plugins)), set(_parse_csv(getattr(agent, "plugins", None)))
    for rel in new_p - old_p:
        _copy_template_item(
            settings.claude_data_dir / "plugins" / rel,
            workdir / "plugins" / rel,
        )
    for rel in old_p - new_p:
        _remove_path(workdir / "plugins" / rel)

    old_s, new_s = set(_parse_csv(old_skills)), set(_parse_csv(getattr(agent, "skills", None)))
    for name in new_s - old_s:
        _copy_template_item(
            settings.claude_data_dir / "skills" / name,
            workdir / "skills" / name,
        )
    for name in old_s - new_s:
        _remove_path(workdir / "skills" / name)


def reinit_agent_workdir(agent) -> None:  # noqa: ANN001
    """重新初始化:仅清空 plugins/、skills/、CLAUDE.md,保留其他子目录(如 projects/)。

    用于「主目录升级后想把模板源同步过来」的手动刷新场景。
    """
    workdir = get_agent_workdir(agent.code)
    if workdir.exists():
        _remove_path(workdir / "CLAUDE.md")
        _remove_path(workdir / "plugins")
        _remove_path(workdir / "skills")
    init_agent_workdir(agent)


def remove_agent_workdir(code: str) -> None:
    """删除该智能体的工作目录(目录不存在或 IO 失败时静默忽略)。"""
    workdir = get_agent_workdir(code)
    if workdir.exists():
        shutil.rmtree(workdir, ignore_errors=True)


async def ensure_all_agent_workdirs() -> None:
    """启动钩子:为 DB 中所有 Agent 兜底初始化工作目录(缺则补)。"""
    # 延迟 import 避免 import 循环
    from sqlalchemy import select

    from app.db import async_session
    from app.models import Agent

    async with async_session() as s:
        rows = (await s.execute(select(Agent))).scalars().all()
    for agent in rows:
        workdir = get_agent_workdir(agent.code)
        if not workdir.exists():
            init_agent_workdir(agent)
