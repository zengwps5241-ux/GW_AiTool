"""营销地图相关 ORM 模型（M2.2）。

四张表（严格对齐营销地图设计文档V2.0）：
- StakeholderCard：角色卡（客观层 objectiveLayer / 主观层 subjectiveLayer / behaviors / stanceChangeLog，JSONB）
- StakeholderRelation：角色间显式关系（reports_to/influences/collaborates/opposes，支撑关系网络图）
- TalkScript：话术（五类角色 × 场景；isTemplate=true 为跨客户通用模板）
- KnowledgeBase：知识库（role_recognition/behavior_quick_ref/onboarding_guide）

主键 Integer 自增（决策 #10）；FK 到 projects.id / stakeholder_cards.id / users.id 均为 Integer。
综合评分（compositeScore）/ 等级（gradeLevel）由 service 层在写入时按 §5.2 公式计算。
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


class StakeholderCard(Base):
    """角色卡。"""

    __tablename__ = "stakeholder_cards"
    __table_args__ = (
        Index("ix_sc_project_role", "project_id", "role_type"),
        Index("ix_sc_project_review", "project_id", "review_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[str | None] = mapped_column(String, nullable=True)
    department: Mapped[str | None] = mapped_column(String, nullable=True)
    reports_to: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_info: Mapped[str | None] = mapped_column(String, nullable=True)
    # 角色类型：economic_decision_maker / technical_evaluator / user / coach_supporter / procurement_finance
    role_type: Mapped[str | None] = mapped_column(String, nullable=True)
    decision_power: Mapped[str | None] = mapped_column(String, nullable=True)

    # 客观层（教育/经历/性格/沟通偏好/人际关系/与我方历史/与竞品历史）
    objective_layer: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 主观层（stance/KPI/诉求/态度/参与度/影响力/支持度/综合评分/等级/置信度/顾虑/杠杆）
    subjective_layer: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 行为列表（observation/interpretation/suggestedAction）
    behaviors: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # 态度变化历史（date/from/to/reason，§7.6 自动追加）
    stance_change_log: Mapped[list | None] = mapped_column(JSONB, nullable=True)

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
    is_public: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    shared_with: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    sensitivity_level: Mapped[str] = mapped_column(String, nullable=False, default="internal")
    # 产出该草稿的会话 ID（Chat Session；M4.4.5 待采纳徽标"跳回原对话"用）
    source_session_id: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )


class StakeholderRelation(Base):
    """角色间显式关系（关系网络图边）。"""

    __tablename__ = "stakeholder_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    from_card_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stakeholder_cards.id", ondelete="CASCADE"), nullable=False
    )
    to_card_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stakeholder_cards.id", ondelete="CASCADE"), nullable=False
    )
    # reports_to / influences / collaborates / opposes
    relation_type: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )


class TalkScript(Base):
    """话术（五类角色 × 场景；isTemplate=true 为跨客户通用模板）。"""

    __tablename__ = "talk_scripts"
    __table_args__ = (Index("ix_ts_project_role", "project_id", "role_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # 关联角色卡（可为空：通用模板）
    stakeholder_card_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stakeholder_cards.id", ondelete="SET NULL"), nullable=True
    )
    role_type: Mapped[str | None] = mapped_column(String, nullable=True)
    scenario: Mapped[str | None] = mapped_column(String, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_customer_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_template: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
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


class KnowledgeBase(Base):
    """知识库（role_recognition/behavior_quick_ref/onboarding_guide）。"""

    __tablename__ = "knowledge_base"
    __table_args__ = (Index("ix_kb_project_category", "project_id", "category"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # 类别：role_recognition / behavior_quick_ref / onboarding_guide
    category: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
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


class PersonDisambiguationCandidate(Base):
    """角色去重候选（M5.5.1）。

    AI 在对话中新建角色卡草稿时，若与项目内既有卡疑似同人（姓名相似 + 部门/角色类型加成），
    生成一条去重候选记录供用户在前端确认（§7.1 角色去重）：
    - decision="new"：草稿确认为新人 → promote draft→reviewed（独立建卡）。
    - decision="merge"：草稿实为既有卡的同人 → 合并草稿字段进既有卡并删除草稿。

    draft_card_id / merge_into_card_id 用 SET NULL：草稿被删除/合并后仍保留候选行作审计。
    new_draft_snapshot / candidates 为 JSONB（检测时刻的快照，供前端展示，不随后续变动改变）。
    """

    __tablename__ = "person_disambiguation_candidates"
    __table_args__ = (
        Index("ix_pdc_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # 触发去重的新草稿卡（合并后草稿被删，SET NULL 保留审计）
    draft_card_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stakeholder_cards.id", ondelete="SET NULL"), nullable=True
    )
    # 新草稿字段快照（name/position/department/role_type 等）
    new_draft_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # 候选既有卡列表：[{id,name,position,department,role_type,score,reasons}]
    candidates: Mapped[list] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")  # pending|resolved
    # 用户决策：new|merge（仅 resolved 后有值）
    decision: Mapped[str | None] = mapped_column(String, nullable=True)
    # decision=merge 时指向被合并进的目标卡
    merge_into_card_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stakeholder_cards.id", ondelete="SET NULL"), nullable=True
    )
    resolved_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProcurementTimeline(Base):
    """项目级采购流程时间线（一个项目一份，M4.2.5）。

    五阶段通用模板（需求识别→方案评估→供应商筛选→商务谈判→合同签署），
    由用户手动填写各阶段状态/起止日期/说明/关键角色。stages 为 JSONB 数组，
    内部 camelCase（§5.2 契约）：[{ key, name, status, startDate, endDate, note, ownerCardId }]。
    """

    __tablename__ = "procurement_timelines"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_proc_timeline_project"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # 五阶段数组（camelCase JSONB；键契约见 service 层 PROCUREMENT_STAGE_TEMPLATE）
    stages: Mapped[list | None] = mapped_column(JSONB, nullable=True)
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
