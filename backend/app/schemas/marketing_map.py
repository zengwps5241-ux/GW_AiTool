"""营销地图相关 Pydantic 模型（M2.2）。

与 app.modules.marketing_map.service 对齐。schemas=plain BaseModel（无 orm_mode）。
客观层/主观层/behaviors/stanceChangeLog 为 JSONB，schema 层不约束内部结构；
主观层的 compositeScore / gradeLevel 由 service 按 §5.2 公式计算后写回。
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ─── 角色卡 ────────────────────────────────────────────────────


class StakeholderCardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    position: str | None = Field(None, max_length=100)
    department: str | None = Field(None, max_length=100)
    reports_to: str | None = Field(None, max_length=100)
    contact_info: str | None = None
    role_type: str | None = Field(
        None,
        pattern="^(economic_decision_maker|technical_evaluator|user|coach_supporter|procurement_finance)$",
    )
    decision_power: str | None = None
    objective_layer: dict[str, Any] | None = None
    subjective_layer: dict[str, Any] | None = None
    behaviors: list[dict[str, Any]] | None = None
    stance_change_log: list[dict[str, Any]] | None = None
    review_status: str = Field("reviewed", pattern="^(draft|pending_review|reviewed|rejected)$")
    is_public: bool = False
    shared_with: list[int] | None = None
    sensitivity_level: str = "internal"


class StakeholderCardUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    position: str | None = None
    department: str | None = None
    reports_to: str | None = None
    contact_info: str | None = None
    role_type: str | None = Field(
        None,
        pattern="^(economic_decision_maker|technical_evaluator|user|coach_supporter|procurement_finance)$",
    )
    decision_power: str | None = None
    objective_layer: dict[str, Any] | None = None
    subjective_layer: dict[str, Any] | None = None
    behaviors: list[dict[str, Any]] | None = None
    stance_change_log: list[dict[str, Any]] | None = None
    review_status: str | None = Field(None, pattern="^(draft|pending_review|reviewed|rejected)$")
    is_public: bool | None = None
    shared_with: list[int] | None = None
    sensitivity_level: str | None = None


class StakeholderCardOut(BaseModel):
    id: int
    project_id: int
    name: str
    position: str | None = None
    department: str | None = None
    reports_to: str | None = None
    contact_info: str | None = None
    role_type: str | None = None
    decision_power: str | None = None
    objective_layer: dict[str, Any] | None = None
    subjective_layer: dict[str, Any] | None = None
    behaviors: list[dict[str, Any]] | None = None
    stance_change_log: list[dict[str, Any]] | None = None
    review_status: str
    reviewed_by: int | None = None
    reviewed_by_name: str | None = None
    reviewed_at: str | None = None
    created_by: int
    created_by_name: str | None = None
    is_public: bool = False
    shared_with: list[int] | None = None
    sensitivity_level: str = "internal"
    source_session_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ─── 角色关系 ──────────────────────────────────────────────────


class StakeholderRelationCreate(BaseModel):
    from_card_id: int
    to_card_id: int
    relation_type: str = Field(
        ..., pattern="^(reports_to|influences|collaborates|opposes)$"
    )
    description: str | None = None


class StakeholderRelationOut(BaseModel):
    id: int
    project_id: int
    from_card_id: int
    from_card_name: str | None = None
    to_card_id: int
    to_card_name: str | None = None
    relation_type: str
    description: str | None = None
    created_by: int
    created_at: str | None = None


class StakeholderGraphNode(BaseModel):
    id: int
    name: str
    role_type: str | None = None
    department: str | None = None


class StakeholderGraphEdge(BaseModel):
    id: int
    source: int
    target: int
    relation_type: str
    description: str | None = None


class StakeholderGraphOut(BaseModel):
    nodes: list[StakeholderGraphNode]
    edges: list[StakeholderGraphEdge]


# ─── 话术 ──────────────────────────────────────────────────────


class TalkScriptCreate(BaseModel):
    stakeholder_card_id: int | None = None
    role_type: str | None = Field(
        None,
        pattern="^(economic_decision_maker|technical_evaluator|user|coach_supporter|procurement_finance)$",
    )
    scenario: str | None = None
    content: str = Field(..., min_length=1)
    source_customer_quote: str | None = None
    is_template: bool = False


class TalkScriptUpdate(BaseModel):
    stakeholder_card_id: int | None = None
    role_type: str | None = None
    scenario: str | None = None
    content: str | None = None
    source_customer_quote: str | None = None
    is_template: bool | None = None


class TalkScriptOut(BaseModel):
    id: int
    project_id: int
    stakeholder_card_id: int | None = None
    stakeholder_card_name: str | None = None
    role_type: str | None = None
    scenario: str | None = None
    content: str
    source_customer_quote: str | None = None
    is_template: bool = False
    created_by: int
    created_at: str | None = None
    updated_at: str | None = None


# ─── 知识库 ────────────────────────────────────────────────────


class KnowledgeBaseCreate(BaseModel):
    category: str = Field(
        ..., pattern="^(role_recognition|behavior_quick_ref|onboarding_guide)$"
    )
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)


class KnowledgeBaseUpdate(BaseModel):
    category: str | None = Field(
        None, pattern="^(role_recognition|behavior_quick_ref|onboarding_guide)$"
    )
    title: str | None = Field(None, min_length=1, max_length=200)
    content: str | None = None


class KnowledgeBaseOut(BaseModel):
    id: int
    project_id: int
    category: str
    title: str
    content: str
    created_by: int
    created_at: str | None = None
    updated_at: str | None = None


# ─── 采购流程时间线（M4.2.5）──────────────────────────────────


class ProcurementStageIn(BaseModel):
    """采购单阶段（camelCase JSONB；键契约见 service.PROCUREMENT_STAGE_TEMPLATE）。"""

    key: str = Field(..., description="阶段 key，五阶段通用模板之一")
    name: str | None = None
    status: str | None = Field(
        None,
        pattern="^(not_started|in_progress|completed|blocked)$",
        description="未开始/进行中/已完成/受阻",
    )
    startDate: str | None = None
    endDate: str | None = None
    note: str | None = None
    ownerCardId: int | None = None


class ProcurementStageOut(BaseModel):
    key: str
    name: str | None = None
    status: str | None = None
    startDate: str | None = None
    endDate: str | None = None
    note: str | None = None
    ownerCardId: int | None = None


class ProcurementTimelineInput(BaseModel):
    """采购时间线 upsert（一个项目一份，整体替换 stages）。"""

    stages: list[ProcurementStageIn]


class ProcurementTimelineOut(BaseModel):
    """采购时间线输出。"""

    id: int
    project_id: int
    stages: list[ProcurementStageOut]
    created_by: int
    created_by_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ─── 态度变化（§7.6） ─────────────────────────────────────────


class StanceChangeIn(BaseModel):
    """手动/自动追加一条态度变化记录。"""

    from_stance: str = Field(..., alias="from", description="此前立场")
    to_stance: str = Field(..., alias="to", description="当前立场")
    reason: str

    model_config = {"populate_by_name": True}


class StanceChangeOut(BaseModel):
    date: str
    from_stance: str
    to_stance: str
    reason: str


# ─── 角色去重候选（M5.5.1 person_disambiguation）──────────────


class DisambiguationCandidateCard(BaseModel):
    """去重候选中的既有角色卡（比对项，含相似度评分与命中原因）。"""

    id: int
    name: str
    position: str | None = None
    department: str | None = None
    role_type: str | None = None
    score: float
    reasons: list[str]


class DisambiguationCandidateOut(BaseModel):
    """一条去重候选：新草稿 vs 项目内疑似同人的既有卡列表。"""

    id: int
    project_id: int
    draft_card_id: int | None = None
    new_draft_snapshot: dict[str, Any]
    candidates: list[DisambiguationCandidateCard]
    status: str  # pending|resolved
    decision: str | None = None  # new|merge（resolved 后有值）
    merge_into_card_id: int | None = None
    resolved_by: int | None = None
    created_at: str | None = None
    resolved_at: str | None = None


class DisambiguationResolveIn(BaseModel):
    """用户去重确认决策。merge 时必须给 merge_into_card_id（候选列表内的既有卡 id）。"""

    decision: str = Field(..., pattern="^(new|merge)$")
    merge_into_card_id: int | None = None


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
