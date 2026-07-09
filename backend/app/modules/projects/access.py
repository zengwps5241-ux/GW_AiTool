"""项目访问权限的纯数据访问层（不依赖 FastAPI）。

供 api/project_deps.py 与 modules/customers、modules/projects 服务层共用，
避免 modules → api 的反向依赖。

成员判定见 DECISIONS.md / §3 权限模型：
- admin/super：可访问所有项目
- 普通用户：直接成员（project_members）或所属部门被授权（project_department_access）
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Project,
    ProjectDepartmentAccess,
    ProjectMember,
    User,
    UserOrganization,
)


async def get_user_project_role(
    db: AsyncSession, project_id: int, user: User
) -> str | None:
    """返回用户在项目中的角色：owner / deputy / admin / None。

    admin/super 直接返回 "admin"。部门授权成员按 deputy 计。
    """
    if user.role in ("admin", "super"):
        return "admin"

    # 直接成员
    pm = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if pm is not None:
        return pm.role

    # 部门授权
    dept_grant = (
        await db.execute(
            select(ProjectDepartmentAccess)
            .join(
                UserOrganization,
                UserOrganization.organization_id
                == ProjectDepartmentAccess.organization_id,
            )
            .where(
                ProjectDepartmentAccess.project_id == project_id,
                UserOrganization.user_id == user.id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if dept_grant is not None:
        return "deputy"

    return None


async def get_accessible_project_ids(db: AsyncSession, user: User) -> set[int]:
    """返回当前用户可访问（可见）的全部项目 ID 集合。

    admin/super：返回空集合表示"全部可见"（调用方需特判）。
    普通用户：直接成员项目 ∪ 所属部门被授权项目。
    """
    if user.role in ("admin", "super"):
        return set()  # 约定：空集 = 全部可见

    # 直接成员项目
    direct = (
        await db.execute(
            select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
        )
    ).scalars().all()

    # 部门授权项目
    via_dept = (
        await db.execute(
            select(ProjectDepartmentAccess.project_id)
            .join(
                UserOrganization,
                UserOrganization.organization_id
                == ProjectDepartmentAccess.organization_id,
            )
            .where(UserOrganization.user_id == user.id)
        )
    ).scalars().all()

    return set(direct) | set(via_dept)


async def project_exists(db: AsyncSession, project_id: int) -> bool:
    """项目是否存在。"""
    return (
        await db.execute(select(Project.id).where(Project.id == project_id).limit(1))
    ).scalar_one_or_none() is not None
