"""个人空间通用任务 API 模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class WorkspaceTaskOut(BaseModel):
    type: Literal["upload", "conversion"]
    task_key: str
    id: int
    workspace_kind: str = "personal"
    team_space_id: int | None = None
    name: str
    path: str
    status: str
    progress: int | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}
