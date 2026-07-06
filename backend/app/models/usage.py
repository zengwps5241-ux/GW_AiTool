"""Usage analytics ORM models。"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UsageEvent(Base):
    """每次用户发送消息产生的一轮对话统计。"""

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_code: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_api_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    sdk_usage_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sdk_model_usage_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    resources: Mapped[list["UsageResourceEvent"]] = relationship(
        lambda: UsageResourceEvent,
        back_populates="usage_event",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_usage_events_started_at", "started_at"),
        Index("idx_usage_events_user_started", "user_id", "started_at"),
        Index("idx_usage_events_agent_started", "agent_id", "started_at"),
        Index("idx_usage_events_status_started", "status", "started_at"),
    )


class UsageResourceEvent(Base):
    """一轮对话中实际触发的 skill/plugin 资源。"""

    __tablename__ = "usage_resource_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usage_event_id: Mapped[int] = mapped_column(
        ForeignKey("usage_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String, nullable=False)
    resource_name: Mapped[str] = mapped_column(String, nullable=False)
    plugin_name: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    tool_use_id: Mapped[str | None] = mapped_column(String, nullable=True)
    is_error: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    usage_event: Mapped[UsageEvent] = relationship(back_populates="resources")

    __table_args__ = (
        Index("idx_usage_resource_event", "usage_event_id"),
        Index("idx_usage_resource_type_name", "resource_type", "resource_name"),
        Index("idx_usage_resource_plugin", "plugin_name"),
    )
