"""Workspace 文件上传任务 ORM model。"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UploadTask(Base):
    """前端批量上传文件的持久化排队任务。"""

    __tablename__ = "upload_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, nullable=False)
    workspace_kind: Mapped[str] = mapped_column(String, nullable=False, default="personal")
    team_space_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_dir: Mapped[str] = mapped_column(String, nullable=False, default="")
    relative_path: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    saved_path: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_upload_tasks_user_created", "username", "created_at"),
        Index("idx_upload_tasks_user_status", "username", "status"),
        Index("idx_upload_tasks_status", "status"),
        Index("idx_upload_tasks_workspace_created", "workspace_kind", "team_space_id", "created_at"),
        Index(
            "uq_upload_tasks_one_running_per_user",
            "username",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )
