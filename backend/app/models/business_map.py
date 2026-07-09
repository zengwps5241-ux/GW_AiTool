"""业务地图相关 ORM 模型（M2.1）。

包含四张表：
- BusinessMapObject：业务地图节点（L1/L2/L3/L4，假设/现状），payload 按层级差异化（JSONB）
- PreAnalysis：项目级前置分析（一个项目一份）
- BusinessMapVersion：项目级版本快照（采纳时生成，支持回滚，§7.4）
- BusinessMapDraft：草稿区（整个业务地图为一个草稿单元，§7.1.7；7 天过期，§7.1.6）

主键 Integer 自增（决策 #10）；FK 到 projects.id / users.id 均为 Integer。
parentId / linkedHypothesisId 为本表自引用（Integer FK，不建 ORM 关系，树在 service 层组装）。
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BusinessMapObject(Base):
    """业务地图节点。"""

    __tablename__ = "business_map_objects"
    __table_args__ = (
        Index("ix_bmo_project_map_level", "project_id", "map_type", "level"),
        Index("ix_bmo_project_review", "project_id", "review_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # 层级：L1 / L2 / L3 / L4
    level: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # 父节点（同项目同 mapType 内的树结构）
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("business_map_objects.id", ondelete="CASCADE"), nullable=True
    )
    # 地图类型：hypothesis（假设）/ current（现状）
    map_type: Mapped[str] = mapped_column(String, nullable=False, default="hypothesis")
    # 验证状态：未验证 / 成立 / 部分成立 / 推翻 / 待补充
    verification_status: Mapped[str] = mapped_column(
        String, nullable=False, default="未验证"
    )
    # current 节点关联的假设节点（必填）
    linked_hypothesis_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("business_map_objects.id", ondelete="SET NULL"), nullable=True
    )
    # 层级差异化载荷（通用字段 + L1/L2/L3/L4 专属字段 + 五维健康）
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 审核状态：draft / pending_review / reviewed / rejected（§7.3：页面只展示 reviewed）
    review_status: Mapped[str] = mapped_column(
        String, nullable=False, default="draft"
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_by_ai: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=0  # SQLite 兼容用 Integer 代替 Boolean
    )
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


class PreAnalysis(Base):
    """项目级前置分析（一个项目一份）。"""

    __tablename__ = "pre_analyses"
    __table_args__ = (UniqueConstraint("project_id", name="uq_pre_analysis_project"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    industry_value_chain: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_position: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry_trends: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategic_positioning: Mapped[str | None] = mapped_column(Text, nullable=True)
    digitalization_drivers: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class BusinessMapVersion(Base):
    """项目级业务地图版本快照（采纳时生成，支持回滚，§7.4）。"""

    __tablename__ = "business_map_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # 采纳时刻的整张业务地图快照（business_map_objects 序列化）
    snapshot_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    change_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )


class BusinessMapDraft(Base):
    """业务地图草稿区（整个业务地图为一个草稿单元，§7.1.7；7 天过期，§7.1.6）。"""

    __tablename__ = "business_map_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # 草稿内容（增量更新的整张业务地图草稿）
    draft_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 产出该草稿的会话 ID（Chat Session）
    source_session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 状态：active / adopted / expired
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )
