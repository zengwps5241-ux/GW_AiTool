"""菜单管理 API（方案 A：自引用树 + 角色-菜单可见性关联，决策 #58/#59）。

两类端点（跨 /api/admin 与 /api 两个前缀域，故 router 不设统一 prefix，路径写全）：
- 管理端（require_admin）：菜单 CRUD + 树 + 批量排序
- 用户端（任意登录用户）：GET /api/menus 当前用户可见菜单树

权限规则（决策 #58）：角色只控制菜单可见性，后端 require_admin/require_super 继续硬编码不变。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, require_admin
from app.db.session import get_db
from app.models import User
from app.modules.menus import service as menu_service
from app.schemas.menus import (
    MenuCreate,
    MenuNode,
    MenuOut,
    MenuSortRequest,
    MenuTreeOut,
    MenuUpdate,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── 管理端：菜单 CRUD（require_admin）─────────────────────────
#
# 注意：/tree、/sort 等具名路径必须注册在 /{menu_id} 之前，否则被当作 menu_id 匹配。


@router.get("/api/admin/menus", response_model=list[MenuOut])
async def list_menus(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[MenuOut]:
    """列出全部菜单（平铺）。"""
    return await menu_service.list_menus(db)


@router.get("/api/admin/menus/tree", response_model=list[MenuTreeOut])
async def get_menus_tree(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[MenuTreeOut]:
    """返回完整菜单树（含 is_visible/is_system，供系统设置菜单管理 tab）。"""
    return await menu_service.get_menus_tree(db)


@router.put("/api/admin/menus/sort", response_model=list[int])
async def sort_menus(
    payload: MenuSortRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[int]:
    """批量更新菜单 sort_order，返回实际更新的菜单 id 列表。"""
    return await menu_service.sort_menus(db, payload.items)


@router.post(
    "/api/admin/menus",
    response_model=MenuOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_menu(
    payload: MenuCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> MenuOut:
    """创建自定义菜单（is_system 恒为 False）。"""
    try:
        return await menu_service.create_menu(db, payload, actor_id=_admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/api/admin/menus/{menu_id}", response_model=MenuOut)
async def get_menu(
    menu_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> MenuOut:
    """获取单个菜单。"""
    out = await menu_service.get_menu(db, menu_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="菜单不存在")
    return out


@router.put("/api/admin/menus/{menu_id}", response_model=MenuOut)
async def update_menu(
    menu_id: int,
    payload: MenuUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> MenuOut:
    """更新菜单展示字段（code 与 is_system 不可改）。"""
    try:
        return await menu_service.update_menu(db, menu_id, payload, actor_id=_admin.id)
    except ValueError as exc:
        msg = str(exc)
        if msg == "菜单不存在":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.delete("/api/admin/menus/{menu_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_menu(
    menu_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """删除菜单（系统菜单 is_system=True 不可删除；有子菜单需先删子）。"""
    try:
        await menu_service.delete_menu(db, menu_id, actor_id=_admin.id)
    except ValueError as exc:
        msg = str(exc)
        if msg == "菜单不存在":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ─── 用户端：当前用户可见菜单（任意登录用户）────────────────────


@router.get("/api/menus", response_model=list[MenuNode])
async def get_my_menus(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[MenuNode]:
    """当前登录用户可见菜单树（渲染用，决策 #67 登录后一次性加载）。

    按 User.role → Role.code → role_menus 计算；super 全部可见，其他角色按关联。
    """
    return await menu_service.get_visible_menus_tree(db, user.role)
