"""认证相关 Pydantic 模型。"""

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int | None = None
    username: str
    phone: str | None = None
    status: str = "active"
    registration_source: str = "admin_create"
    # DEPRECATED: 企微字段，保留兼容
    wechat_user_id: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    department: str | None = None
    department_ids: list[int] | None = None
    position: str | None = None
    mobile: str | None = None
    email: str | None = None
    auth_source: str = "local"
    role: str = "user"


class RegisterRequest(BaseModel):
    """用户注册请求。支持手机号+密码或用户名+密码。"""
    username: str | None = Field(None, min_length=2, max_length=50, description="用户名")
    phone: str | None = Field(None, min_length=11, max_length=11, description="手机号")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    display_name: str | None = Field(None, max_length=50, description="显示名称")

    def get_login_key(self) -> str:
        """返回用于登录的标识（手机号或用户名）。"""
        return self.phone or self.username or ""


class LoginRequest(BaseModel):
    """用户登录请求。支持手机号/用户名 + 密码。"""
    login: str = Field(..., min_length=1, description="手机号或用户名")
    password: str = Field(..., min_length=1, description="密码")


class PendingUserOut(BaseModel):
    """待审批用户信息。"""
    id: int
    username: str
    phone: str | None = None
    display_name: str | None = None
    status: str
    registration_source: str
    created_at: str | None = None


class ApproveRequest(BaseModel):
    """审批操作请求。"""
    action: str = Field(..., pattern="^(approve|reject)$", description="approve=通过, reject=驳回")
    reason: str | None = Field(None, max_length=500, description="审批理由")
