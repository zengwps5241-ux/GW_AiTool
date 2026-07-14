"""用户管理 API（管理端，M6.4）。

仅 admin/super 可访问（require_admin）。提供：
- GET /api/admin/users 全量用户列表 + 筛选（role/status/organization_id/search）
- POST /api/admin/users 管理员创建用户（跳过审批 status=active）
- PUT /api/admin/users/{id}/status 启用/禁用（不可禁自己）
- POST /api/admin/users/{id}/reset-password 重置密码

权限规则：require_admin 硬编码（决策 #58），与角色菜单可见性无关。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import User
from app.modules.users import service as user_service
from app.schemas.users import (
    AdminUserCreate,
    AdminUserOut,
    ResetPasswordRequest,
    UserStatusUpdate,
)

router = APIRouter(prefix="/api/admin")
logger = logging.getLogger(__name__)


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    role: str | None = Query(None, description="按角色筛选"),
    status: str | None = Query(None, description="按状态筛选 active/disabled/pending_approval"),
    organization_id: int | None = Query(None, description="按所属组织筛选"),
    search: str | None = Query(None, description="用户名/手机号模糊搜索"),
    _admin: User = Depends(require_admin),
) -> list[AdminUserOut]:
    """全量用户列表（含所属组织 + 最后登录）。"""
    return await user_service.list_admin_users(
        db, role=role, status=status, organization_id=organization_id, search=search
    )


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AdminUserOut:
    """管理员创建用户（跳过审批，status=active）。"""
    try:
        user = await user_service.create_admin_user(db, payload, actor_id=_admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return user_service._user_to_out(user)


@router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """启用/禁用用户（不可禁自己）。"""
    try:
        await user_service.update_user_status(
            db, user_id, payload.status, actor_id=_admin.id
        )
    except ValueError as exc:
        msg = str(exc)
        if msg == "用户不存在":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "user_id": user_id, "status": payload.status}


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """管理员重置用户密码。"""
    try:
        await user_service.reset_password(
            db, user_id, payload.new_password, actor_id=_admin.id
        )
    except ValueError as exc:
        msg = str(exc)
        if msg == "用户不存在":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "user_id": user_id}
