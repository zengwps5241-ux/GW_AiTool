"""认证相关 Pydantic 模型。"""

from pydantic import BaseModel


class UserOut(BaseModel):
    id: int | None = None
    username: str
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
