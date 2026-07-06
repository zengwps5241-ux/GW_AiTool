"""会话相关 Pydantic 模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SessionOut(BaseModel):
    id: str
    title: str
    agent_id: int | None = None
    agent_name: str | None = None
    workspace_kind: Literal["personal", "team"] = "personal"
    team_space_id: int | None = None
    created_by_user_id: int | None = None
    created_by_name: str | None = None
    team_space_name: str | None = None
    is_shared: bool = False
    workspace_member_role: Literal["reader", "editor"] | None = None
    workspace_can_write: bool = True
    workspace_readonly_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class CreateSessionRequest(BaseModel):
    title: str | None = None
    agent_id: int | None = None
    workspace_kind: Literal["personal", "team"] = "personal"
    team_space_id: int | None = None
    is_shared: bool = False


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1)
    model: str | None = Field(default=None, min_length=1)
    thinking_level: Literal["disabled", "low", "medium", "high"] = "low"
