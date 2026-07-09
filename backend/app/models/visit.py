"""拜访记录相关 ORM 模型（M2.3）。

两张表（严格对齐规格说明书V2.0 §5.2）：
- VisitRecord：拜访记录（时间线，按 visitDate 倒序；含参与人/摘要/下一步/Key Takeaways）
- EvidenceSource：证据（挂在某次拜访下；关联角色卡 sourceRoleId + 关联假设节点 relatedHypothesisId）

主键 Integer 自增（决策 #10）；FK 到 projects.id / visit_records.id / stakeholder_cards.id /
business_map_objects.id / users.id 均为 Integer。
JSONB 字段（participantsOur/Client、keyTakeaways、sharedWith、relatedCardIds）schema 层不约束内部结构。
evidenceCount / verifiedHypotheses 为派生统计，由 service 层在读取时按关联证据计算（不落库，避免同步问题）。

联动（§7.5/§7.6）：
- 证据 relatedHypothesisId 关联假设节点时，service 提供「建议验证状态」+「人工确认」入口，
  确认后更新假设节点 verificationStatus；若推翻则自动新增偏差池条目（current 节点）。
- 证据 sourceRoleId 关联角色卡且 evidenceType=角色态度信号 时，自动调 marketing_map.record_stance_change。
"""

from datetime import datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VisitRecord(Base):
    """拜访记录（时间线单元）。"""

    __tablename__ = "visit_records"
    __table_args__ = (
        Index("ix_vr_project_date", "project_id", "visit_date"),
        Index("ix_vr_project_review", "project_id", "review_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # 拜访日期（一句话记录可省略）
    visit_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    # 拜访类型：现场访谈 / 电话沟通 / 视频会议 / 邮件 / 一句话记录
    visit_type: Mapped[str] = mapped_column(String, nullable=False, default="一句话记录")
    # 我方参与人姓名
    participants_our: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # 客户方参与人（关联 StakeholderCard 的 id 列表）
    participants_client: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    duration: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_takeaways: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # 关联的角色卡 id 列表（冗余于证据，便于按角色筛选拜访）
    related_card_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # 审核状态：draft / pending_review / reviewed / rejected（§7.3：页面只展示 reviewed）
    review_status: Mapped[str] = mapped_column(
        String, nullable=False, default="draft"
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # 跨项目公开（§3.5）
    is_public: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    shared_with: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    sensitivity_level: Mapped[str] = mapped_column(String, nullable=False, default="internal")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )


class EvidenceSource(Base):
    """证据（挂在某次拜访下；关联角色卡 + 关联假设节点）。"""

    __tablename__ = "evidence_sources"
    __table_args__ = (
        Index("ix_es_project_visit", "project_id", "visit_record_id"),
        Index("ix_es_project_type", "project_id", "evidence_type"),
        Index("ix_es_project_strength", "project_id", "strength"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    visit_record_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("visit_records.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # 证据类型：客户原话 / 行为观察 / 角色态度信号 / 业务术语
    evidence_type: Mapped[str] = mapped_column(String, nullable=False)
    # 强度：强 / 中 / 弱
    strength: Mapped[str] = mapped_column(String, nullable=False, default="中")
    strength_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 关联角色卡（§7.6：角色态度信号类证据关联后自动记录态度变化）
    source_role_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stakeholder_cards.id", ondelete="SET NULL"), nullable=True
    )
    source_role_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # 关联假设节点（§7.5：证据关联假设节点 → 建议验证状态 → 人工确认）
    related_hypothesis_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("business_map_objects.id", ondelete="SET NULL"), nullable=True
    )
    related_hypothesis_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # §7.6 自动态度变化触发用：角色态度信号类证据可携带「此前立场 → 当前立场」
    implied_from_stance: Mapped[str | None] = mapped_column(String, nullable=True)
    implied_to_stance: Mapped[str | None] = mapped_column(String, nullable=True)

    review_status: Mapped[str] = mapped_column(
        String, nullable=False, default="draft"
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )
