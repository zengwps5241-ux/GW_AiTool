"""工作空间上下文解析。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import user_workspace
from app.models import User
from app.modules.team_spaces.service import can_write, require_member, team_workspace


@dataclass(frozen=True)
class WorkspaceScope:
    """统一描述个人/团队空间的访问上下文。"""

    kind: Literal["personal", "team"]
    key: str
    root: Path
    display_name: str
    can_read: bool
    can_write: bool
    member_role: Literal["reader", "editor"] | None = None
    is_owner: bool = False
    locked_by_user_id: int | None = None
    readonly_reason: str | None = None


async def personal_workspace_scope(user: User) -> WorkspaceScope:
    return WorkspaceScope(
        kind="personal",
        key=user.username,
        root=user_workspace(user.username),
        display_name="个人空间",
        can_read=True,
        can_write=True,
    )


async def team_workspace_scope(db: AsyncSession, user: User, space_id: int) -> WorkspaceScope:
    space, member = await require_member(db, user, space_id)
    write, reason = can_write(space, member)
    return WorkspaceScope(
        kind="team",
        key=str(space.id),
        root=team_workspace(space.id),
        display_name=space.name,
        can_read=True,
        can_write=write,
        member_role=member.role,
        is_owner=space.owner_user_id == user.id,
        locked_by_user_id=space.lock_holder_user_id,
        readonly_reason=reason,
    )


def require_workspace_write(scope: WorkspaceScope) -> None:
    if not scope.can_write:
        raise HTTPException(status_code=403, detail=scope.readonly_reason or "当前工作空间不可写")
