"""问题反馈 ORM 模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FeedbackIssue(Base):
    __tablename__ = "feedback_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    reporter_username: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )

    attachments: Mapped[list["FeedbackAttachment"]] = relationship(
        back_populates="issue",
        cascade="all, delete-orphan",
    )


class FeedbackAttachment(Base):
    __tablename__ = "feedback_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_issues.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )

    issue: Mapped[FeedbackIssue] = relationship(back_populates="attachments")


# 与兼容迁移中的手写 SQL 保持一致，避免新库和旧库索引名称不一致。
Index("idx_feedback_issues_created", FeedbackIssue.created_at.desc())
Index("idx_feedback_issues_reporter", FeedbackIssue.reporter_username)
Index("idx_feedback_attachments_issue", FeedbackAttachment.issue_id)
