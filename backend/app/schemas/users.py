"""用户管理（管理端）Pydantic 模型。M6.4 用户管理增强。

与 app.modules.users.service 对齐。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserOrgBrief(BaseModel):
    """用户所属组织简要信息（列表用）。"""

    id: int
    name: str


class AdminUserOut(BaseModel):
    """管理端用户列表项（含所属组织 + 最后登录）。"""

    id: int
    username: str
    phone: str | None = None
    role: str
    status: str
    display_name: str | None = None
    department: str | None = None
    registration_source: str | None = None
    organizations: list[UserOrgBrief] = []
    created_at: str | None = None
    last_login: str | None = None


class AdminUserCreate(BaseModel):
    """管理员创建用户（跳过审批，status=active）。"""

    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    phone: str | None = Field(None, min_length=11, max_length=11, description="手机号")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    display_name: str | None = Field(None, max_length=50, description="显示名称")
    role: str = Field("user", description="角色 code（user/admin/super/自定义，须已存在）")


class UserStatusUpdate(BaseModel):
    """用户状态变更（启用/禁用）。"""

    status: str = Field(..., pattern="^(active|disabled)$", description="active=启用 / disabled=禁用")


class ResetPasswordRequest(BaseModel):
    """管理员重置用户密码。"""

    new_password: str = Field(..., min_length=6, max_length=128, description="新密码")
