"""转换任务 API 模型。"""

from datetime import datetime

from pydantic import BaseModel


class ConversionTaskOut(BaseModel):
    id: int
    workspace_kind: str = "personal"
    team_space_id: int | None = None
    source_path: str
    source_name: str
    status: str
    error_message: str | None = None
    markdown_path: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConversionRetryIn(BaseModel):
    source_path: str
