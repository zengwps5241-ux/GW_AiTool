"""团队空间 API schema。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


TeamMemberRole = Literal["reader", "editor"]


class TeamSpaceCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None


class TeamSpaceUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None


class TeamSpaceMemberAddIn(BaseModel):
    user_id: int
    role: TeamMemberRole = "reader"


class TeamSpaceMemberUpdateIn(BaseModel):
    role: TeamMemberRole


class TeamSpaceTransferOwnerIn(BaseModel):
    user_id: int


class TeamSpaceLockIn(BaseModel):
    note: str | None = None


class TeamSpaceOut(BaseModel):
    id: int
    name: str
    description: str | None
    owner_user_id: int
    owner_name: str
    member_count: int
    locked_by_user_id: int | None
    locked_by_name: str | None
    lock_acquired_at: datetime | None
    lock_note: str | None
    member_role: TeamMemberRole
    can_write: bool
    is_owner: bool
    readonly_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeamSpaceMemberOut(BaseModel):
    id: int
    user_id: int
    username: str
    display_name: str | None
    role: TeamMemberRole
    is_owner: bool
    added_by_user_id: int
    created_at: datetime
    updated_at: datetime


class TeamSpaceMemberSearchOut(BaseModel):
    user_id: int
    username: str
    display_name: str | None
    is_member: bool
