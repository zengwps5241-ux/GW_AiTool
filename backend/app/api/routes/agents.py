"""智能体 CRUD 与技能清单。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, require_admin
from app.core.config import user_workspace
from app.db.session import get_db
from app.models import Agent, Category, PluginBinding, SkillBinding, User
from app.modules.agents.service import (
    create_agent as create_agent_svc,
    delete_agent as delete_agent_svc,
    get_agent as get_agent_svc,
    list_agents as list_agents_svc,
    update_agent as update_agent_svc,
)
from app.modules.agents.workdir import get_agent_workdir, reinit_agent_workdir
from app.modules.catalog.commands import scan_agent_commands
from app.modules.catalog.plugins import scan_plugins
from app.modules.catalog.skills import scan_skills
from app.schemas import (
    AgentCommandOut,
    AgentOut,
    CreateAgentRequest,
    PluginOut,
    SkillOut,
    UpdateAgentRequest,
)

router = APIRouter(prefix="/api")


async def _default_category(db: AsyncSession) -> Category:
    """返回默认分类；数据库初始化会确保它存在。"""
    result = await db.execute(select(Category).where(Category.name == "默认"))
    category = result.scalar_one_or_none()
    if category is None:
        raise HTTPException(status_code=500, detail="默认分类不存在")
    return category


async def _resolve_category(db: AsyncSession, category_id: int | None) -> Category:
    """校验并返回智能体分类；未传时使用默认分类。"""
    if category_id is None:
        return await _default_category(db)
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")
    return category


async def _agent_out(db: AsyncSession, agent: Agent) -> AgentOut:
    """组装带分类名称的智能体响应。"""
    category = await db.get(Category, agent.category_id) if agent.category_id else None
    if category is None:
        category = await _default_category(db)
    return AgentOut.model_validate(
        {
            "id": agent.id,
            "name": agent.name,
            "code": agent.code,
            "system_prompt": agent.system_prompt,
            "skills": agent.skills,
            "plugins": agent.plugins,
            "category_id": category.id,
            "category": category.name,
            "is_default": agent.is_default,
            "created_at": agent.created_at,
            "updated_at": agent.updated_at,
        }
    )


@router.get("/agents", response_model=list[AgentOut])
async def list_agents(
    _user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentOut]:
    rows = await list_agents_svc(db)
    return [await _agent_out(db, r) for r in rows]


@router.get("/agents/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: int,
    _user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentOut:
    agent = await get_agent_svc(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体不存在")
    return await _agent_out(db, agent)


@router.get("/agents/{agent_id}/commands", response_model=list[AgentCommandOut])
async def list_agent_commands(
    agent_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentCommandOut]:
    """返回该智能体当前工作目录中可用的 slash command 清单。"""
    agent = await get_agent_svc(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体不存在")
    workdir = get_agent_workdir(agent.code)
    return [
        AgentCommandOut(**item)
        for item in scan_agent_commands(workdir, user_workspace=user_workspace(user.username))
    ]


@router.post("/agents", response_model=AgentOut)
async def create_agent(
    payload: CreateAgentRequest,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AgentOut:
    category = await _resolve_category(db, payload.category_id)
    try:
        agent = await create_agent_svc(
            db,
            name=payload.name,
            code=payload.code,
            system_prompt=payload.system_prompt,
            skills=payload.skills,
            plugins=payload.plugins,
            category_id=category.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="代号已存在",
        ) from exc
    return await _agent_out(db, agent)


@router.patch("/agents/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: int,
    payload: UpdateAgentRequest,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AgentOut:
    agent = await get_agent_svc(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体不存在")
    category_id = None
    if payload.category_id is not None:
        category = await _resolve_category(db, payload.category_id)
        category_id = category.id
    agent = await update_agent_svc(
        db,
        agent,
        name=payload.name,
        system_prompt=payload.system_prompt,
        skills=payload.skills,
        plugins=payload.plugins,
        category_id=category_id,
        is_default=payload.is_default,
    )
    return await _agent_out(db, agent)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: int,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    agent = await get_agent_svc(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体不存在")
    await delete_agent_svc(db, agent)


@router.post("/agents/{agent_id}/reinit", response_model=AgentOut)
async def reinit_agent(
    agent_id: int,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AgentOut:
    """重新初始化工作目录:清空 plugins/、skills/、CLAUDE.md,按当前勾选与主目录最新模板重建。"""
    agent = await get_agent_svc(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体不存在")
    reinit_agent_workdir(agent)
    return await _agent_out(db, agent)


@router.get("/skills", response_model=list[SkillOut])
async def list_skills(
    _user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SkillOut]:
    skills = scan_skills()

    # 获取所有绑定
    bindings_result = await db.execute(select(SkillBinding))
    bindings = {b.skill_name: b.category_id for b in bindings_result.scalars().all()}

    # 获取所有分类
    categories_result = await db.execute(select(Category))
    categories = {c.id: c.name for c in categories_result.scalars().all()}

    # 获取默认分类
    default_cat_result = await db.execute(
        select(Category).where(Category.name == "默认")
    )
    default_category = default_cat_result.scalar_one()

    # 为未绑定的技能创建默认绑定
    for skill in skills:
        if skill["name"] not in bindings:
            db.add(SkillBinding(skill_name=skill["name"], category_id=default_category.id))
            bindings[skill["name"]] = default_category.id

    if any(s["name"] not in bindings for s in skills):
        await db.commit()

    return [
        SkillOut(
            name=s["name"],
            description=s["description"],
            category=categories.get(bindings.get(s["name"]), "默认"),
        )
        for s in skills
    ]


@router.get("/plugins", response_model=list[PluginOut])
async def list_plugins(
    _user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PluginOut]:
    """枚举 claude_data_dir/plugins 下的所有插件,供前端勾选。"""
    plugins = scan_plugins()

    # 获取所有绑定
    bindings_result = await db.execute(select(PluginBinding))
    bindings = {b.plugin_path: b.category_id for b in bindings_result.scalars().all()}

    # 获取所有分类
    categories_result = await db.execute(select(Category))
    categories = {c.id: c.name for c in categories_result.scalars().all()}

    # 获取默认分类
    default_cat_result = await db.execute(
        select(Category).where(Category.name == "默认")
    )
    default_category = default_cat_result.scalar_one()

    # 为未绑定的插件创建默认绑定
    for plugin in plugins:
        if plugin["path"] not in bindings:
            db.add(PluginBinding(plugin_path=plugin["path"], category_id=default_category.id))
            bindings[plugin["path"]] = default_category.id

    if any(p["path"] not in bindings for p in plugins):
        await db.commit()

    return [
        PluginOut(
            name=p["name"],
            version=p["version"],
            description=p["description"],
            path=p["path"],
            category=categories.get(bindings.get(p["path"]), "默认"),
        )
        for p in plugins
    ]
