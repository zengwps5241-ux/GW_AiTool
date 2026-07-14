"""角色管理 API（角色 + 菜单可见性关联，方案 A）。

仅 admin/super 可访问（require_admin）。提供：
- 角色 CRUD（GET/POST/PUT/DELETE /api/admin/roles）
- 角色-菜单关联（GET/PUT /api/admin/roles/{id}/menus）
- 用户角色分配（PUT /api/admin/users/{id}/role）

注意：角色只控制菜单可见性，后端 require_admin/require_super 继续硬编码不变（决策 #58）。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import User
from app.modules.roles import service as role_service
from app.schemas.roles import (
    RoleCreate,
    RoleMenusUpdate,
    RoleOut,
    RoleUpdate,
    UserRoleAssignment,
)

router = APIRouter(prefix="/api/admin")
logger = logging.getLogger(__name__)


# ─── 角色 CRUD ───────────────────────────────────────────────


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[RoleOut]:
    """列出全部角色。"""
    return await role_service.list_roles(db)


@router.post(
    "/roles",
    response_model=RoleOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_role(
    payload: RoleCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> RoleOut:
    """创建自定义角色（is_system 恒为 False）。"""
    try:
        return await role_service.create_role(db, payload, actor_id=_admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/roles/{role_id}", response_model=RoleOut)
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> RoleOut:
    """获取单个角色。"""
    out = await role_service.get_role(db, role_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    return out


@router.put("/roles/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: int,
    payload: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> RoleOut:
    """更新角色（仅 name/description/sort_order）。"""
    try:
        return await role_service.update_role(db, role_id, payload, actor_id=_admin.id)
    except ValueError as exc:
        msg = str(exc)
        if msg == "角色不存在":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """删除角色（系统内置角色 is_system=True 不可删除）。"""
    try:
        await role_service.delete_role(db, role_id, actor_id=_admin.id)
    except ValueError as exc:
        msg = str(exc)
        if msg == "角色不存在":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ─── 角色-菜单关联 ───────────────────────────────────────────


@router.get("/roles/{role_id}/menus", response_model=list[int])
async def get_role_menus(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[int]:
    """查看角色关联的菜单 ID 列表（super 始终全部）。"""
    ids = await role_service.get_role_menu_ids(db, role_id)
    if ids is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    return ids


@router.put("/roles/{role_id}/menus", response_model=list[int])
async def set_role_menus(
    role_id: int,
    payload: RoleMenusUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[int]:
    """批量设置角色关联菜单（全量替换）。super 角色关联不可修改。"""
    try:
        return await role_service.set_role_menus(db, role_id, payload.menu_ids)
    except ValueError as exc:
        msg = str(exc)
        if msg == "角色不存在":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        if msg.startswith("super"):
            # super 保护属业务规则冲突，用 403 更语义化
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ─── 用户角色分配 ─────────────────────────────────────────────


@router.put("/users/{user_id}/role")
async def assign_user_role(
    user_id: int,
    payload: UserRoleAssignment,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """修改用户角色（更新 User.role 为目标 Role.code）。"""
    try:
        user = await role_service.assign_user_role(db, user_id, payload.role_code)
    except ValueError as exc:
        msg = str(exc)
        if msg == "用户不存在":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"user_id": user.id, "role": user.role}
