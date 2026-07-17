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
    # M3.4.2：项目级会话绑定（绑定后自动加载项目 Agent + 草稿工具）
    project_id: int | None = None
    project_name: str | None = None
    workflow_type: str | None = None
    workflow_status: str | None = None
    workflow_stage: str | None = None
    created_at: datetime
    updated_at: datetime


class CreateSessionRequest(BaseModel):
    title: str | None = None
    agent_id: int | None = None
    workspace_kind: Literal["personal", "team"] = "personal"
    team_space_id: int | None = None
    is_shared: bool = False
    # M3.4.2：绑定项目后，自动加载项目 Agent（未显式给 agent_id 时）
    project_id: int | None = None


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1)
    model: str | None = Field(default=None, min_length=1)
    thinking_level: Literal["disabled", "low", "medium", "high"] = "low"
    workflow_type: Literal[
        "hypothesis_map",
        "interview_summary",
        "stakeholder_card",
        "visit_plan",
        "current_map_verify",
    ] | None = None


# 对话「标记为有价值」→ 个人空间知识片段（规格 §2.6 line157 / Phase 4 line1334）
class KnowledgeFragmentIn(BaseModel):
    # 标记的对话内容（assistant 回复正文），落盘为 Markdown
    content: str = Field(min_length=1)
    # 可选标题；缺省时取内容首行
    title: str | None = Field(default=None, max_length=200)


class KnowledgeFragmentOut(BaseModel):
    # 相对个人空间根的路径，如「信创迁移项目/知识片段/20260713_103044_xxx.md」
    path: str
    filename: str
    project_name: str | None = None
