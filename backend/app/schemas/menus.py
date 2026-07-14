"""菜单管理相关 Pydantic 模型。

方案 A（决策 #58/#59）：菜单自引用树驱动侧边栏动态渲染，角色经 role_menus 控制可见性。
与后端 app.modules.menus.service 对齐。

- MenuOut / MenuTreeOut：管理端完整字段（含 is_visible/is_system），供系统设置菜单管理 tab 使用
- MenuNode：当前用户可见菜单精简字段（渲染用，决策 #67 登录后一次性加载）
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MenuCreate(BaseModel):
    """创建菜单（自定义菜单 is_system 恒为 False，由服务层强制）。"""

    code: str = Field(..., min_length=1, max_length=50, description="菜单编码（UNIQUE）")
    name: str = Field(..., min_length=1, max_length=50, description="菜单显示名")
    parent_id: int | None = Field(None, description="父级菜单 ID，根菜单为空")
    icon: str | None = Field(None, max_length=50, description="Lucide 图标名")
    view_name: str | None = Field(None, max_length=50, description="对应前端 ViewName")
    sort_order: int = Field(0, description="同层级排序")
    is_visible: bool = Field(True, description="是否可见")


class MenuUpdate(BaseModel):
    """更新菜单（仅可改展示字段；code 与 is_system 不可改）。"""

    name: str | None = Field(None, min_length=1, max_length=50)
    parent_id: int | None = None
    icon: str | None = Field(None, max_length=50)
    view_name: str | None = Field(None, max_length=50)
    sort_order: int | None = None
    is_visible: bool | None = None


class MenuOut(BaseModel):
    """菜单输出（管理端完整字段，平铺无 children）。"""

    id: int
    parent_id: int | None = None
    name: str
    code: str
    icon: str | None = None
    view_name: str | None = None
    sort_order: int
    is_visible: bool
    is_system: bool
    created_at: str | None = None
    updated_at: str | None = None


class MenuTreeOut(BaseModel):
    """菜单树节点（管理端，含完整字段 + children）。"""

    id: int
    parent_id: int | None = None
    name: str
    code: str
    icon: str | None = None
    view_name: str | None = None
    sort_order: int
    is_visible: bool
    is_system: bool
    children: list["MenuTreeOut"] = []


class MenuNode(BaseModel):
    """当前用户可见菜单树节点（渲染用，精简字段，决策 #67）。

    与 M6.5.1 前端 MenuNode 类型对齐。
    """

    id: int
    parent_id: int | None = None
    name: str
    code: str
    icon: str | None = None
    view_name: str | None = None
    sort_order: int
    children: list["MenuNode"] = []


class MenuSortItem(BaseModel):
    """批量排序单项：{id, sort_order}。"""

    id: int
    sort_order: int


class MenuSortRequest(BaseModel):
    """批量更新菜单排序（全量或部分均可，按 id 更新 sort_order）。"""

    items: list[MenuSortItem] = Field(..., description="待排序菜单列表")
