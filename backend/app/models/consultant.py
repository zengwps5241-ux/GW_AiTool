"""顾问 Plugin 相关 ORM 模型。

M3.3.1 起承载「意图路由」的数据记录（IntentRoutingLog）。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IntentRoutingLog(Base):
    """WF01 意图路由日志（每次自然语言输入必入一条，§4.3 Plugin1）。

    记录三级路由全过程：LLM 分类结果 / 关键词命中 / 最终意图 / 实际下发提示，
    便于离线分析路由准确率与调优关键词/分类 Prompt。session_id 沿用
    ``usage_events`` 的 plain String 形式（chat_sessions.id 为 UUID 字符串主键，
    不加 FK 以避免字符串主键外键的迁移复杂度，与既有统计表保持一致）。
    """

    __tablename__ = "intent_routing_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # 用户原始输入（路由前）
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # 最终路由意图标签（7 类之一：hypothesis_map/current_map_verify/
    # stakeholder_card/interview_summary/visit_plan/file_upload/chat）
    intent_label: Mapped[str] = mapped_column(String, nullable=False)
    # 路由目标：Skill 命令名（如 consultant-hypothesis-map）或 "chat"
    route_target: Mapped[str | None] = mapped_column(String, nullable=True)
    # 路由置信来源：chip（chip/斜杠直达）/ llm / keyword / chat_fallback
    confidence_source: Mapped[str] = mapped_column(String, nullable=False)
    # LLM 分类原始结果
    llm_label: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 关键词命中的意图标签集合（去重）
    keyword_hits: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    # LLM 返回的原始结构（含 reason 等，便于调试；解析失败时存 raw 文本）
    llm_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # 实际下发给 Claude 的最终提示（路由到 Skill 时为 /<skill> <原提示>）
    final_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_intent_routing_session", "session_id", "created_at"),
        Index("idx_intent_routing_project", "project_id", "created_at"),
        Index("idx_intent_routing_label", "intent_label"),
    )
