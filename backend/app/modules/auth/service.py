"""认证业务逻辑。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models import User


async def authenticate_user(db: AsyncSession, username: str, password: str) -> User | None:
    """验证用户名密码，成功返回 User，失败返回 None。"""
    user = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user
