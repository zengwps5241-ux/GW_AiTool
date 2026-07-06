"""智能体相关 Pydantic 模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AgentOut(BaseModel):
    id: int
    name: str
    code: str
    system_prompt: str | None
    skills: str
    plugins: str
    category_id: int | None = None
    category: str = "默认"
    is_default: bool
    created_at: datetime
    updated_at: datetime


class CreateAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(..., pattern=r'^[a-zA-Z0-9_-]+$')
    system_prompt: str | None = None
    skills: str = ""
    plugins: str = ""
    category_id: int | None = None


class UpdateAgentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    system_prompt: str | None = None
    skills: str | None = None
    plugins: str | None = None
    category_id: int | None = None
    is_default: bool | None = None


class AgentCommandOut(BaseModel):
    name: str
    description: str = ""
    source: Literal["personal_skill", "skill", "plugin"]
    plugin: str | None = None
