"""团队空间业务逻辑。"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import TeamSpace, TeamSpaceMember, User


def team_workspace(space_id: int) -> Path:
    """返回团队空间目录，并确保基础 Markdown 目录存在。"""
    root = get_settings().workspaces_dir.parent / "team_workspaces" / str(space_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / ".markdown").mkdir(parents=True, exist_ok=True)
    return root


async def get_membership(db: AsyncSession, user: User, space_id: int) -> TeamSpaceMember | None:
    return (
        await db.execute(
            select(TeamSpaceMember).where(
                TeamSpaceMember.space_id == space_id,
                TeamSpaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()


async def require_member(db: AsyncSession, user: User, space_id: int) -> tuple[TeamSpace, TeamSpaceMember]:
    space = await db.get(TeamSpace, space_id)
    member = await get_membership(db, user, space_id)
    if space is None or member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="空间不存在")
    return space, member


async def require_owner(db: AsyncSession, user: User, space_id: int) -> tuple[TeamSpace, TeamSpaceMember]:
    """校验当前用户是团队空间所有者。"""
    space, member = await require_member(db, user, space_id)
    if space.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="只有空间所有者可以管理成员")
    return space, member


async def get_space_member_by_id(db: AsyncSession, space_id: int, member_id: int) -> TeamSpaceMember:
    member = await db.get(TeamSpaceMember, member_id)
    if member is None or member.space_id != space_id:
        raise HTTPException(status_code=404, detail="成员不存在")
    return member


def can_write(space: TeamSpace, member: TeamSpaceMember) -> tuple[bool, str | None]:
    if member.role != "editor":
        return False, "只读成员不能编辑团队空间"
    if space.lock_holder_user_id is None:
        return True, None
    if space.lock_holder_user_id == member.user_id:
        return True, None
    return False, "当前空间已被其他成员锁定"


async def member_count(db: AsyncSession, space_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(TeamSpaceMember).where(TeamSpaceMember.space_id == space_id)
    )
    return int(result.scalar() or 0)


async def create_space(db: AsyncSession, user: User, name: str, description: str | None) -> TeamSpace:
    space = TeamSpace(name=name, description=description, owner_user_id=user.id, created_by_user_id=user.id)
    db.add(space)
    await db.flush()
    db.add(TeamSpaceMember(space_id=space.id, user_id=user.id, role="editor", added_by_user_id=user.id))
    await db.commit()
    team_workspace(space.id)
    await db.refresh(space)
    return space


async def add_member(
    db: AsyncSession,
    owner: User,
    space_id: int,
    user_id: int,
    role: str,
) -> TeamSpaceMember:
    space, _owner_member = await require_owner(db, owner, space_id)
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    existing = (
        await db.execute(
            select(TeamSpaceMember).where(
                TeamSpaceMember.space_id == space_id,
                TeamSpaceMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.user_id == space.owner_user_id:
            raise HTTPException(status_code=400, detail="不能修改空间所有者权限")
        existing.role = role
        await db.commit()
        await db.refresh(existing)
        return existing

    member = TeamSpaceMember(
        space_id=space_id,
        user_id=user_id,
        role=role,
        added_by_user_id=owner.id,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def update_member_role(
    db: AsyncSession,
    owner: User,
    space_id: int,
    member_id: int,
    role: str,
) -> TeamSpaceMember:
    space, _owner_member = await require_owner(db, owner, space_id)
    member = await get_space_member_by_id(db, space_id, member_id)
    if member.user_id == space.owner_user_id:
        raise HTTPException(status_code=400, detail="不能修改空间所有者权限")
    member.role = role
    await db.commit()
    await db.refresh(member)
    return member


async def remove_member(db: AsyncSession, owner: User, space_id: int, member_id: int) -> None:
    space, _owner_member = await require_owner(db, owner, space_id)
    member = await get_space_member_by_id(db, space_id, member_id)
    if member.user_id == space.owner_user_id:
        raise HTTPException(status_code=400, detail="不能删除空间所有者")
    if space.lock_holder_user_id == member.user_id:
        space.lock_holder_user_id = None
        space.lock_acquired_at = None
        space.lock_note = None
    await db.delete(member)
    await db.commit()


async def transfer_owner(db: AsyncSession, owner: User, space_id: int, user_id: int) -> TeamSpace:
    space, _owner_member = await require_owner(db, owner, space_id)
    target_member = (
        await db.execute(
            select(TeamSpaceMember).where(
                TeamSpaceMember.space_id == space_id,
                TeamSpaceMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if target_member is None:
        raise HTTPException(status_code=404, detail="目标成员不存在")
    space.owner_user_id = user_id
    target_member.role = "editor"
    await db.commit()
    await db.refresh(space)
    return space


async def leave_space(db: AsyncSession, user: User, space_id: int) -> None:
    space, member = await require_member(db, user, space_id)
    if space.owner_user_id == user.id:
        raise HTTPException(status_code=400, detail="空间所有者必须先转让所有权")
    if space.lock_holder_user_id == user.id:
        space.lock_holder_user_id = None
        space.lock_acquired_at = None
        space.lock_note = None
    await db.delete(member)
    await db.commit()


async def search_member_candidates(
    db: AsyncSession,
    owner: User,
    space_id: int,
    keyword: str,
) -> list[tuple[User, bool]]:
    """空间所有者按姓名模糊搜索可添加成员。"""
    await require_owner(db, owner, space_id)

    keyword = keyword.strip()
    if not keyword:
        return []

    pattern = f"%{keyword}%"
    users = (
        await db.execute(
            select(User)
            .where(or_(User.display_name.ilike(pattern), User.username.ilike(pattern)))
            .order_by(
                User.display_name.asc().nullslast(),
                User.username.asc(),
                User.id.asc(),
            )
            .limit(20)
        )
    ).scalars().all()
    if not users:
        return []

    member_user_ids = set(
        (
            await db.execute(
                select(TeamSpaceMember.user_id).where(
                    TeamSpaceMember.space_id == space_id,
                    TeamSpaceMember.user_id.in_(
                        [candidate.id for candidate in users],
                    ),
                )
            )
        ).scalars().all()
    )
    return [(candidate, candidate.id in member_user_ids) for candidate in users]


async def lock_space(db: AsyncSession, user: User, space_id: int, note: str | None) -> TeamSpace:
    space, member = await require_member(db, user, space_id)
    if member.role != "editor":
        raise HTTPException(status_code=403, detail="只读成员不能锁定团队空间")
    if space.lock_holder_user_id not in (None, user.id):
        raise HTTPException(status_code=409, detail="当前空间已被锁定")
    space.lock_holder_user_id = user.id
    space.lock_acquired_at = datetime.now(timezone.utc)
    space.lock_note = note
    await db.commit()
    await db.refresh(space)
    return space


async def unlock_space(db: AsyncSession, user: User, space_id: int) -> TeamSpace:
    space, _member = await require_member(db, user, space_id)
    if space.lock_holder_user_id not in (None, user.id):
        raise HTTPException(status_code=403, detail="只有持锁人可以解除锁定")
    space.lock_holder_user_id = None
    space.lock_acquired_at = None
    space.lock_note = None
    await db.commit()
    await db.refresh(space)
    return space
