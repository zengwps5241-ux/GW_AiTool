"""项目（Project）业务服务层。

职责：
- Project CRUD（创建时自动生成项目 Agent，绑定标准 Skill/Plugin，§5.2）
- 成员管理（Owner 邀请/移除 Deputy；保持单 Owner 不变式）
- 部门授权（Owner 授权部门 → 部门成员自动获得项目访问权，§3.5 / V2.2）
- 可见性过滤：admin 全部；普通用户仅可访问项目

权限：项目内全透明、项目外全隔离（§3.5）。Owner/Member 判定见 access.py。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Agent,
    Customer,
    Organization,
    Project,
    ProjectDepartmentAccess,
    ProjectMember,
    User,
)
from app.modules.agents.workdir import init_agent_workdir, remove_agent_workdir
from app.modules.projects.access import get_accessible_project_ids, get_user_project_role
from app.schemas.projects import (
    ProjectCreate,
    ProjectDepartmentAccessAdd,
    ProjectDepartmentAccessOut,
    ProjectMemberAdd,
    ProjectMemberOut,
    ProjectOut,
    ProjectUpdate,
    iso,
)

# 项目 Agent 绑定的标准 Skill / Plugin（§5.2 Agent 创建规则）
# 完整 SKILL.md 在 Phase 3（M3.2）落地；此处先绑定名称占位。
DEFAULT_PROJECT_SKILLS = (
    "consultant-upload,consultant-gap-check,consultant-visit-plan,"
    "consultant-hypothesis-map,consultant-interview,consultant-verify,"
    "consultant-stakeholder"
)
DEFAULT_PROJECT_PLUGINS = "consultant-router,consultant-search,consultant-defense"


# ─── 工具 ──────────────────────────────────────────────────────


async def _user_name(db: AsyncSession, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    u = await db.get(User, user_id)
    return (u.display_name or u.username) if u else None


def _build_project_system_prompt(project: Project, customer: Customer | None) -> str:
    """生成项目 Agent 的初始 system_prompt（道层 + 项目上下文）。

    完整「道层」防御性 System Prompt 在 Phase 3（consultant-defense Plugin）注入；
    此处先注入项目上下文骨架。
    """
    lines = [
        f"你是「{project.name}」项目的咨询顾问智能体。",
    ]
    if customer is not None:
        lines.append(f"服务客户：{customer.name}（{customer.industry or '行业未填'}）。")
    if project.objectives:
        lines.append(f"项目目标：{project.objectives}")
    lines.append("遵循顾问方法论（业务地图 / 营销地图 / 拜访记录）协助推进项目。")
    return "\n".join(lines)


async def build_project_out(
    db: AsyncSession, project: Project, user: User
) -> ProjectOut:
    """组装项目输出（含客户名、Owner 名、成员数、当前用户角色）。"""
    customer = await db.get(Customer, project.customer_id)
    member_count = (
        await db.execute(
            select(func.count(ProjectMember.id)).where(
                ProjectMember.project_id == project.id
            )
        )
    ).scalar_one()
    role = await get_user_project_role(db, project.id, user)
    return ProjectOut(
        id=project.id,
        customer_id=project.customer_id,
        customer_name=customer.name if customer else None,
        name=project.name,
        agent_id=project.agent_id,
        project_type=project.project_type,
        fde_stage=project.fde_stage,
        status=project.status,
        owner_id=project.owner_id,
        owner_name=await _user_name(db, project.owner_id),
        description=project.description,
        objectives=project.objectives,
        start_date=project.start_date.isoformat() if project.start_date else None,
        end_date=project.end_date.isoformat() if project.end_date else None,
        created_by=project.created_by,
        created_by_name=await _user_name(db, project.created_by),
        visibility=project.visibility,
        sensitivity_level=project.sensitivity_level,
        member_count=int(member_count or 0),
        my_role=role,
        created_at=iso(project.created_at),
        updated_at=iso(project.updated_at),
    )


# ─── CRUD ──────────────────────────────────────────────────────


async def list_projects(db: AsyncSession, user: User) -> list[ProjectOut]:
    """列出项目。admin 全部；普通用户仅可访问项目。"""
    if user.role in ("admin", "super"):
        projects = (
            await db.execute(select(Project).order_by(Project.id))
        ).scalars().all()
    else:
        accessible = await get_accessible_project_ids(db, user)
        if not accessible:
            return []
        projects = (
            await db.execute(
                select(Project).where(Project.id.in_(accessible)).order_by(Project.id)
            )
        ).scalars().all()

    out: list[ProjectOut] = []
    for p in projects:
        out.append(await build_project_out(db, p, user))
    return out


async def create_project(
    db: AsyncSession, payload: ProjectCreate, user: User
) -> ProjectOut:
    """创建项目：校验客户 → 建项目 → 自动建 Agent → 建 Owner 成员记录。

    单事务提交，保证项目与 Agent 原子创建。
    """
    customer = await db.get(Customer, payload.customer_id)
    if customer is None:
        raise ValueError("客户不存在")

    # 1) 先建项目（agent_id 暂空），flush 拿到 id
    project = Project(
        customer_id=payload.customer_id,
        name=payload.name,
        agent_id=None,
        project_type=payload.project_type,
        fde_stage=payload.fde_stage,
        status=payload.status,
        owner_id=user.id,
        description=payload.description,
        objectives=payload.objectives,
        start_date=payload.start_date,
        end_date=payload.end_date,
        created_by=user.id,
        visibility=payload.visibility,
        sensitivity_level=payload.sensitivity_level,
    )
    db.add(project)
    await db.flush()

    # 2) 自动创建项目 Agent（code 唯一，用项目 id 生成）
    agent = Agent(
        name=f"{project.name} Agent",
        code=f"consultant_{project.id}",
        system_prompt=_build_project_system_prompt(project, customer),
        skills=DEFAULT_PROJECT_SKILLS,
        plugins=DEFAULT_PROJECT_PLUGINS,
        category_id=None,
    )
    db.add(agent)
    await db.flush()
    project.agent_id = agent.id

    # 3) 创建者成为 Owner
    db.add(
        ProjectMember(
            project_id=project.id,
            user_id=user.id,
            role="owner",
        )
    )
    await db.commit()
    await db.refresh(project)
    await db.refresh(agent)

    # 文件系统侧作用放在提交之后（不回滚 DB）
    init_agent_workdir(agent)

    return await build_project_out(db, project, user)


async def update_project(
    db: AsyncSession, project: Project, payload: ProjectUpdate
) -> Project:
    """更新项目（Owner 已由路由层校验）。返回刷新后的 ORM 对象，
    由路由层调用 build_project_out 组装响应（需要当前 user 计算 my_role）。"""
    if payload.name is not None:
        project.name = payload.name
    if payload.project_type is not None:
        project.project_type = payload.project_type
    if payload.fde_stage is not None:
        project.fde_stage = payload.fde_stage
    if payload.status is not None:
        project.status = payload.status
    if payload.description is not None:
        project.description = payload.description
    if payload.objectives is not None:
        project.objectives = payload.objectives
    if payload.start_date is not None:
        project.start_date = payload.start_date
    if payload.end_date is not None:
        project.end_date = payload.end_date
    if payload.visibility is not None:
        project.visibility = payload.visibility
    if payload.sensitivity_level is not None:
        project.sensitivity_level = payload.sensitivity_level

    await db.commit()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, project: Project) -> None:
    """删除项目：级联清除成员/部门授权，并删除自动创建的项目 Agent。"""
    agent_code: str | None = None
    agent: Agent | None = None
    if project.agent_id is not None:
        agent = await db.get(Agent, project.agent_id)
        if agent is not None:
            agent_code = agent.code

    # 删除项目（ON DELETE CASCADE 自动清理 project_members / project_department_access）
    await db.delete(project)
    if agent is not None:
        await db.delete(agent)
    await db.commit()

    # 清理 Agent 工作目录
    if agent_code:
        try:
            remove_agent_workdir(agent_code)
        except Exception:  # noqa: BLE001 — 文件系统清理失败不阻断删除
            pass


# ─── 成员管理 ──────────────────────────────────────────────────


async def list_members(db: AsyncSession, project: Project) -> list[ProjectMemberOut]:
    """列出项目成员。"""
    rows = (
        await db.execute(
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == project.id)
            .order_by(ProjectMember.joined_at, ProjectMember.id)
        )
    ).all()
    out: list[ProjectMemberOut] = []
    for pm, u in rows:
        out.append(
            ProjectMemberOut(
                id=pm.id,
                project_id=pm.project_id,
                user_id=pm.user_id,
                username=u.username,
                display_name=u.display_name,
                role=pm.role,
                joined_at=iso(pm.joined_at),
            )
        )
    return out


async def add_member(
    db: AsyncSession, project: Project, payload: ProjectMemberAdd
) -> ProjectMemberOut:
    """邀请成员。保持单 Owner 不变式：仅允许添加 deputy。"""
    if payload.role == "owner":
        raise ValueError("项目 Owner 唯一，不能新增 Owner（如需转让请使用转让功能）")
    user = await db.get(User, payload.user_id)
    if user is None:
        raise ValueError("用户不存在")
    existing = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == payload.user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("该用户已是项目成员")

    pm = ProjectMember(
        project_id=project.id,
        user_id=payload.user_id,
        role=payload.role,
    )
    db.add(pm)
    await db.commit()
    await db.refresh(pm)
    return ProjectMemberOut(
        id=pm.id,
        project_id=pm.project_id,
        user_id=pm.user_id,
        username=user.username,
        display_name=user.display_name,
        role=pm.role,
        joined_at=iso(pm.joined_at),
    )


async def remove_member(db: AsyncSession, project: Project, user_id: int) -> None:
    """移除成员。不能移除 Owner（保持至少一个 Owner）。"""
    pm = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if pm is None:
        raise ValueError("该用户不是项目成员")
    if pm.role == "owner":
        raise ValueError("不能移除项目 Owner")
    await db.delete(pm)
    await db.commit()


# ─── 部门授权 ──────────────────────────────────────────────────


async def list_dept_access(
    db: AsyncSession, project: Project
) -> list[ProjectDepartmentAccessOut]:
    """列出来项目授权的部门。"""
    rows = (
        await db.execute(
            select(ProjectDepartmentAccess, Organization, User)
            .join(Organization, Organization.id == ProjectDepartmentAccess.organization_id)
            .join(User, User.id == ProjectDepartmentAccess.granted_by, isouter=True)
            .where(ProjectDepartmentAccess.project_id == project.id)
            .order_by(ProjectDepartmentAccess.granted_at, ProjectDepartmentAccess.id)
        )
    ).all()
    out: list[ProjectDepartmentAccessOut] = []
    for access, org, grantor in rows:
        out.append(
            ProjectDepartmentAccessOut(
                id=access.id,
                project_id=access.project_id,
                organization_id=access.organization_id,
                organization_name=org.name if org else None,
                granted_by=access.granted_by,
                granted_by_name=(grantor.display_name or grantor.username) if grantor else None,
                granted_at=iso(access.granted_at),
            )
        )
    return out


async def grant_dept_access(
    db: AsyncSession, project: Project, payload: ProjectDepartmentAccessAdd, user: User
) -> ProjectDepartmentAccessOut:
    """为项目授权一个部门。"""
    org = await db.get(Organization, payload.organization_id)
    if org is None:
        raise ValueError("组织不存在")
    existing = (
        await db.execute(
            select(ProjectDepartmentAccess).where(
                ProjectDepartmentAccess.project_id == project.id,
                ProjectDepartmentAccess.organization_id == payload.organization_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("该部门已被授权访问本项目")

    access = ProjectDepartmentAccess(
        project_id=project.id,
        organization_id=payload.organization_id,
        granted_by=user.id,
    )
    db.add(access)
    await db.commit()
    await db.refresh(access)
    grantor_name = await _user_name(db, access.granted_by)
    return ProjectDepartmentAccessOut(
        id=access.id,
        project_id=access.project_id,
        organization_id=access.organization_id,
        organization_name=org.name,
        granted_by=access.granted_by,
        granted_by_name=grantor_name,
        granted_at=iso(access.granted_at),
    )


async def revoke_dept_access(
    db: AsyncSession, project: Project, organization_id: int
) -> None:
    """撤销部门授权。"""
    access = (
        await db.execute(
            select(ProjectDepartmentAccess).where(
                ProjectDepartmentAccess.project_id == project.id,
                ProjectDepartmentAccess.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if access is None:
        raise ValueError("该部门未被授权访问本项目")
    await db.delete(access)
    await db.commit()
