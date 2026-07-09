"""项目管理 API（M1.3.6）。

权限（§3）：
- 任何已登录用户可创建项目（创建者默认成为 Owner）并查看自己可访问的项目
- 项目级操作（成员/部门/更新/删除）受 require_project_member / require_project_owner 保护
- admin/super 可访问任意项目
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.api.project_deps import require_project_member, require_project_owner
from app.db.session import get_db
from app.models import Project, User
from app.modules.projects import service as project_service
from app.schemas.projects import (
    ProjectCreate,
    ProjectDepartmentAccessAdd,
    ProjectDepartmentAccessOut,
    ProjectMemberAdd,
    ProjectMemberOut,
    ProjectOut,
    ProjectUpdate,
)

router = APIRouter(prefix="/api/projects")


# ─── 项目 CRUD ────────────────────────────────────────────────


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[ProjectOut]:
    """列出当前用户可访问的项目。"""
    return await project_service.list_projects(db, user)


@router.post(
    "",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ProjectOut:
    """创建项目（自动生成项目 Agent，创建者成为 Owner）。"""
    try:
        return await project_service.create_project(db, payload, user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    """获取单个项目（需为成员或 admin）。"""
    project, user = project_and_user
    return await project_service.build_project_out(db, project, user)


@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(
    payload: ProjectUpdate,
    project_and_user: tuple[Project, User] = Depends(require_project_owner),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    """更新项目（仅 Owner / admin）。"""
    project, user = project_and_user
    updated = await project_service.update_project(db, project, payload)
    return await project_service.build_project_out(db, updated, user)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_and_user: tuple[Project, User] = Depends(require_project_owner),
    db: AsyncSession = Depends(get_db),
) -> None:
    """删除项目（仅 Owner / admin；级联清理成员/部门授权/项目 Agent）。"""
    project, _ = project_and_user
    await project_service.delete_project(db, project)


# ─── 成员管理 ──────────────────────────────────────────────────


@router.get("/{project_id}/members", response_model=list[ProjectMemberOut])
async def list_members(
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectMemberOut]:
    project, _ = project_and_user
    return await project_service.list_members(db, project)


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    payload: ProjectMemberAdd,
    project_and_user: tuple[Project, User] = Depends(require_project_owner),
    db: AsyncSession = Depends(get_db),
) -> ProjectMemberOut:
    """邀请成员（仅 Owner / admin；保持单 Owner，仅可加 deputy）。"""
    project, user = project_and_user
    try:
        return await project_service.add_member(db, project, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete(
    "/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_member(
    user_id: int,
    project_and_user: tuple[Project, User] = Depends(require_project_owner),
    db: AsyncSession = Depends(get_db),
) -> None:
    """移除成员（仅 Owner / admin；不可移除 Owner）。"""
    project, _ = project_and_user
    try:
        await project_service.remove_member(db, project, user_id)
    except ValueError as exc:
        msg = str(exc)
        if "不是" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ─── 部门授权 ──────────────────────────────────────────────────


@router.get(
    "/{project_id}/department-access",
    response_model=list[ProjectDepartmentAccessOut],
)
async def list_department_access(
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectDepartmentAccessOut]:
    project, _ = project_and_user
    return await project_service.list_dept_access(db, project)


@router.post(
    "/{project_id}/department-access",
    response_model=ProjectDepartmentAccessOut,
    status_code=status.HTTP_201_CREATED,
)
async def grant_department_access(
    payload: ProjectDepartmentAccessAdd,
    project_and_user: tuple[Project, User] = Depends(require_project_owner),
    db: AsyncSession = Depends(get_db),
) -> ProjectDepartmentAccessOut:
    """为项目授权部门（仅 Owner / admin）。"""
    project, user = project_and_user
    try:
        return await project_service.grant_dept_access(db, project, payload, user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete(
    "/{project_id}/department-access/{organization_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_department_access(
    organization_id: int,
    project_and_user: tuple[Project, User] = Depends(require_project_owner),
    db: AsyncSession = Depends(get_db),
) -> None:
    """撤销部门授权（仅 Owner / admin）。"""
    project, _ = project_and_user
    try:
        await project_service.revoke_dept_access(db, project, organization_id)
    except ValueError as exc:
        msg = str(exc)
        if "未被授权" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
