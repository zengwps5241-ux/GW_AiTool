"""工作空间相关 Pydantic 模型。"""

from pydantic import BaseModel


class WorkspaceNode(BaseModel):
    name: str
    path: str
    type: str
    size: int | None = None
    mtime: float | None = None
    # 已转换为 markdown 的源文件,这里给出 agent 应使用的 md 路径;
    # 普通文件留空,前端引用时回退到 path 自身。
    agent_path: str | None = None
    children: list["WorkspaceNode"] | None = None
    # 来自 ConversionTask 的转换元数据
    conversion_status: str | None = None
    conversion_task_id: int | None = None
    conversion_error: str | None = None
    markdown_path: str | None = None


WorkspaceNode.model_rebuild()


class UploadedFileOut(BaseModel):
    name: str
    path: str
    size: int
    preview_path: str
    agent_path: str
    converted: bool = False


class UploadItemOut(BaseModel):
    name: str
    path: str | None = None
    size: int = 0
    preview_path: str | None = None
    agent_path: str | None = None
    converted: bool = False
    conversion_task_id: int | None = None
    status: str
    error: str | None = None


class UploadSummaryOut(BaseModel):
    total: int
    succeeded: int
    failed: int


class UploadBatchOut(BaseModel):
    summary: UploadSummaryOut
    items: list[UploadItemOut]


class WorkspaceTextOut(BaseModel):
    path: str
    content: str
    size: int
    mtime: float | None = None


class WorkspaceTextSaveIn(BaseModel):
    path: str
    content: str
    lock_token: str | None = None


class WorkspaceFileLockIn(BaseModel):
    path: str


class WorkspaceFileUnlockIn(BaseModel):
    path: str
    lock_token: str


class WorkspaceFileLockOut(BaseModel):
    ok: bool
    path: str
    lock_token: str
    expires_at_ms: int


class WorkspaceFileUnlockOut(BaseModel):
    released: bool


class WorkspaceCreateIn(BaseModel):
    path: str
    kind: str
    content: str = ""


class WorkspaceRenameIn(BaseModel):
    path: str
    new_name: str


class WorkspaceMoveIn(BaseModel):
    path: str
    target_dir: str
