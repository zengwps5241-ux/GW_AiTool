"""上传任务 API 模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class UploadTaskCreateItemIn(BaseModel):
    filename: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    size: int = Field(ge=0)


class UploadTaskCreateIn(BaseModel):
    target_dir: str = ""
    items: list[UploadTaskCreateItemIn]


class UploadTaskProgressIn(BaseModel):
    progress: int = Field(ge=0, le=100)


class UploadTaskAbandonIn(BaseModel):
    ids: list[int]
    error_message: str | None = Field(default=None, max_length=500)


class UploadTaskOut(BaseModel):
    id: int
    workspace_kind: str = "personal"
    team_space_id: int | None = None
    target_dir: str
    relative_path: str
    filename: str
    status: str
    progress: int
    size: int
    saved_path: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}
