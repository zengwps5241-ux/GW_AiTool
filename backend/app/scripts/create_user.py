"""管理员预创建账号 CLI:
    uv run python -m app.scripts.create_user <username> <password>
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.db.migrations import init_db
from app.db.session import async_session
from app.models import User


async def create_user(username: str, password: str, role: str = "user") -> None:
    await init_db()
    async with async_session() as s:
        existing = (
            await s.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"用户 {username!r} 已存在", file=sys.stderr)
            raise SystemExit(1)
        s.add(User(username=username, password_hash=hash_password(password), role=role))
        try:
            await s.commit()
        except IntegrityError as exc:
            print(f"创建失败: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        print(f"已创建用户: {username} (role={role})")


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2 or len(args) > 4:
        print("用法: python -m app.scripts.create_user <username> <password> [--role admin|super]", file=sys.stderr)
        raise SystemExit(2)
    username, password = args[0], args[1]
    role = "user"
    if len(args) == 4 and args[2] == "--role":
        role = args[3]
    asyncio.run(create_user(username, password, role))


if __name__ == "__main__":
    main()
