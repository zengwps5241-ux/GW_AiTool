"""项目级权限依赖（M1.3.8）。

提供 require_project_member / require_project_owner 两个 FastAPI 依赖，
实现项目级数据隔离（§3.5：项目内全透明、项目外全隔离）。

成员/Owner 判定逻辑见 app.modules.projects.access（纯数据访问层），
本模块仅做 HTTP 层的 404/403 翻译。

使用方式：路由函数声明 project_id 路径参数 + Depends(require_project_member)。
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.db.session import get_db
from app.models import Project, User
from app.modules.projects.access import get_user_project_role


async def _load_project_or_404(db: AsyncSession, project_id: int) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在"
        )
    return project


async def require_project_member(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> tuple[Project, User]:
    """要求当前用户为项目成员（或 admin/super）。"""
    user = await current_user(request, db)
    project = await _load_project_or_404(db, project_id)
    role = await get_user_project_role(db, project_id, user)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目"
        )
    return project, user


async def require_project_owner(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> tuple[Project, User]:
    """要求当前用户为项目 Owner（或 admin/super）。"""
    user = await current_user(request, db)
    project = await _load_project_or_404(db, project_id)
    role = await get_user_project_role(db, project_id, user)
    if role in ("admin", "owner"):
        return project, user
    if role == "deputy":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="仅项目 Owner 可执行此操作"
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目"
    )
