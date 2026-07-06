"""FastAPI 共享依赖:current_user。"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import is_development_environment
from app.db.session import get_db
from app.models import User


async def current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录"
        )
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在"
        )
    return user


def _require_role(user: User, allowed: set[str]) -> User:
    if is_development_environment():
        return user
    if user.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限"
        )
    return user


async def require_admin(
    user: User = Depends(current_user),
) -> User:
    return _require_role(user, {"admin", "super"})


async def require_super(
    user: User = Depends(current_user),
) -> User:
    return _require_role(user, {"super"})
