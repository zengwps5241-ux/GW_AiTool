"""ChatSession ORM model。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # 内部 UUID4
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    # M3.4.2：项目级会话绑定。绑定后该会话自动加载项目 Agent，
    # 并挂载草稿工具（draft_context），AI 产出写入对应项目的草稿区。
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    claude_session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False, default="新会话")
    workspace_kind: Mapped[str] = mapped_column(String, nullable=False, default="personal")
    team_space_id: Mapped[int | None] = mapped_column(
        ForeignKey("team_spaces.id", ondelete="CASCADE"), nullable=True
    )
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    workflow_type: Mapped[str | None] = mapped_column(String, nullable=True)
    workflow_status: Mapped[str | None] = mapped_column(String, nullable=True)
    workflow_stage: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="sessions")

    __table_args__ = (
        Index("idx_sessions_user", "user_id", "updated_at"),
        Index("idx_sessions_team_space", "team_space_id", "updated_at"),
        Index("idx_sessions_workspace", "workspace_kind", "team_space_id", "updated_at"),
        Index("idx_sessions_shared", "team_space_id", "is_shared", "updated_at"),
        Index("idx_sessions_project", "project_id", "updated_at"),
    )
