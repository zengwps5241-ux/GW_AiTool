"""角色管理相关 Pydantic 模型。

方案 A（决策 #58）：角色只管菜单可见性，User.role 字符串与 Role.code 逻辑关联。
与后端 app.modules.roles.service 对齐。
"""

from pydantic import BaseModel, Field


class RoleCreate(BaseModel):
    """创建角色（自定义角色 is_system 恒为 False，由服务层强制）。"""

    code: str = Field(..., min_length=1, max_length=50, description="角色编码（UNIQUE）")
    name: str = Field(..., min_length=1, max_length=50, description="角色显示名")
    description: str | None = Field(None, max_length=255)
    sort_order: int = Field(0, description="排序")


class RoleUpdate(BaseModel):
    """更新角色（仅可改 name/description/sort_order；code 与 is_system 不可改）。"""

    name: str | None = Field(None, min_length=1, max_length=50)
    description: str | None = Field(None, max_length=255)
    sort_order: int | None = None


class RoleOut(BaseModel):
    """角色输出。"""

    id: int
    code: str
    name: str
    description: str | None = None
    is_system: bool
    sort_order: int
    created_at: str | None = None
    updated_at: str | None = None


class RoleMenusUpdate(BaseModel):
    """批量设置角色关联的菜单（全量替换 menu_id 列表）。"""

    menu_ids: list[int] = Field(..., description="菜单 ID 列表（全量替换）")


class UserRoleAssignment(BaseModel):
    """给用户分配角色（更新 User.role 为目标 Role.code）。"""

    role_code: str = Field(..., min_length=1, description="目标角色编码")
