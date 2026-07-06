"""智能体 CRUD 业务逻辑。"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent
from app.modules.agents.workdir import (
    init_agent_workdir,
    reinit_agent_workdir,
    remove_agent_workdir,
    sync_agent_selection,
)


async def list_agents(db: AsyncSession) -> list[Agent]:
    return (await db.execute(select(Agent).order_by(Agent.id))).scalars().all()


async def get_agent(db: AsyncSession, agent_id: int) -> Agent | None:
    return await db.get(Agent, agent_id)


async def create_agent(
    db: AsyncSession,
    name: str,
    code: str,
    system_prompt: str | None,
    skills: str,
    plugins: str,
    category_id: int | None = None,
) -> Agent:
    existing = (await db.execute(
        select(Agent).where(Agent.code == code)
    )).scalar_one_or_none()
    if existing is not None:
        raise ValueError("code already exists")
    agent = Agent(
        name=name,
        code=code,
        system_prompt=system_prompt,
        skills=skills,
        plugins=plugins,
        category_id=category_id,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    init_agent_workdir(agent)
    return agent


async def update_agent(
    db: AsyncSession,
    agent: Agent,
    name: str | None = None,
    system_prompt: str | None = None,
    skills: str | None = None,
    plugins: str | None = None,
    category_id: int | None = None,
    is_default: bool | None = None,
) -> Agent:
    old_plugins = agent.plugins
    old_skills = agent.skills
    if name is not None:
        agent.name = name
    if system_prompt is not None:
        agent.system_prompt = system_prompt
    if skills is not None:
        agent.skills = skills
    if plugins is not None:
        agent.plugins = plugins
    if category_id is not None:
        agent.category_id = category_id
    if is_default is not None:
        if is_default:
            await db.execute(update(Agent).values(is_default=False))
        agent.is_default = is_default
    await db.commit()
    await db.refresh(agent)
    if plugins is not None or skills is not None:
        sync_agent_selection(agent, old_plugins=old_plugins, old_skills=old_skills)
    return agent


async def delete_agent(db: AsyncSession, agent: Agent) -> None:
    await db.delete(agent)
    await db.commit()
    remove_agent_workdir(agent.code)
