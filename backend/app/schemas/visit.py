"""拜访记录相关 Pydantic 模型（M2.3）。

与 app.modules.visits.service 对齐。schemas=plain BaseModel（无 orm_mode）。
JSONB 字段（participantsOur/Client、keyTakeaways、sharedWith、relatedCardIds）schema 层不约束内部结构；
evidenceCount / verifiedHypotheses 为派生统计，由 service 读取时计算后填入 Out。
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


# ─── 拜访记录 ──────────────────────────────────────────────────


class VisitRecordCreate(BaseModel):
    visit_date: date | None = Field(None, description="拜访日期（一句话记录可省略）")
    visit_type: str = Field(
        "一句话记录",
        pattern="^(现场访谈|电话沟通|视频会议|邮件|一句话记录)$",
    )
    participants_our: list[str] | None = None
    participants_client: list[int] | None = Field(None, description="客户方参与人 StakeholderCard id 列表")
    location: str | None = Field(None, max_length=200)
    duration: str | None = Field(None, max_length=50)
    summary: str | None = None
    next_steps: str | None = None
    key_takeaways: list[str] | None = None
    related_card_ids: list[int] | None = None
    # 手动新增默认直接进正式库（reviewed，§7.3）
    review_status: str = Field("reviewed", pattern="^(draft|pending_review|reviewed|rejected)$")
    is_public: bool = False
    shared_with: list[int] | None = None
    sensitivity_level: str = "internal"


class VisitRecordUpdate(BaseModel):
    visit_date: date | None = None
    visit_type: str | None = Field(None, pattern="^(现场访谈|电话沟通|视频会议|邮件|一句话记录)$")
    participants_our: list[str] | None = None
    participants_client: list[int] | None = None
    location: str | None = None
    duration: str | None = None
    summary: str | None = None
    next_steps: str | None = None
    key_takeaways: list[str] | None = None
    related_card_ids: list[int] | None = None
    review_status: str | None = Field(None, pattern="^(draft|pending_review|reviewed|rejected)$")
    is_public: bool | None = None
    shared_with: list[int] | None = None
    sensitivity_level: str | None = None


class VisitRecordOut(BaseModel):
    id: int
    project_id: int
    visit_date: date | None = None
    visit_type: str
    participants_our: list[str] | None = None
    participants_client: list[int] | None = None
    location: str | None = None
    duration: str | None = None
    summary: str | None = None
    next_steps: str | None = None
    key_takeaways: list[str] | None = None
    related_card_ids: list[int] | None = None
    # 派生统计（service 读取时计算）
    evidence_count: int = 0
    verified_hypotheses: int = 0
    review_status: str
    reviewed_by: int | None = None
    reviewed_by_name: str | None = None
    reviewed_at: str | None = None
    created_by: int
    created_by_name: str | None = None
    is_public: bool = False
    shared_with: list[int] | None = None
    sensitivity_level: str = "internal"
    created_at: str | None = None
    updated_at: str | None = None


# ─── 证据 ──────────────────────────────────────────────────────


class EvidenceSourceCreate(BaseModel):
    visit_record_id: int
    evidence_type: str = Field(
        ..., pattern="^(客户原话|行为观察|角色态度信号|业务术语)$"
    )
    strength: str = Field("中", pattern="^(强|中|弱)$")
    strength_note: str | None = None
    content: str = Field(..., min_length=1)
    source_role_id: int | None = Field(None, description="关联 StakeholderCard（角色态度信号类证据可触发 §7.6）")
    source_role_name: str | None = None
    related_hypothesis_id: int | None = Field(None, description="关联 BusinessMapObject 假设节点（触发 §7.5）")
    related_hypothesis_name: str | None = None
    # §7.6 自动态度变化：角色态度信号类证据携带的立场变化
    implied_from_stance: str | None = None
    implied_to_stance: str | None = None
    review_status: str = Field("reviewed", pattern="^(draft|pending_review|reviewed|rejected)$")


class EvidenceSourceUpdate(BaseModel):
    visit_record_id: int | None = None
    evidence_type: str | None = Field(None, pattern="^(客户原话|行为观察|角色态度信号|业务术语)$")
    strength: str | None = Field(None, pattern="^(强|中|弱)$")
    strength_note: str | None = None
    content: str | None = None
    source_role_id: int | None = None
    source_role_name: str | None = None
    related_hypothesis_id: int | None = None
    related_hypothesis_name: str | None = None
    implied_from_stance: str | None = None
    implied_to_stance: str | None = None
    review_status: str | None = Field(None, pattern="^(draft|pending_review|reviewed|rejected)$")


class EvidenceSourceOut(BaseModel):
    id: int
    project_id: int
    visit_record_id: int
    evidence_type: str
    strength: str
    strength_note: str | None = None
    content: str
    source_role_id: int | None = None
    source_role_name: str | None = None
    related_hypothesis_id: int | None = None
    related_hypothesis_name: str | None = None
    implied_from_stance: str | None = None
    implied_to_stance: str | None = None
    review_status: str
    reviewed_by: int | None = None
    reviewed_by_name: str | None = None
    reviewed_at: str | None = None
    created_by: int
    created_by_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ─── 证据验证联动（§7.5） ─────────────────────────────────────


class VerificationSuggestionOut(BaseModel):
    """某假设节点的证据聚合 → 建议验证状态。"""

    hypothesis_id: int
    hypothesis_name: str | None = None
    suggested_status: str = Field(..., description="建议验证状态：未验证 / 成立 / 部分成立 / 待补充")
    strong_count: int
    medium_count: int
    weak_count: int
    total_count: int
    evidence_ids: list[int] = []
    reason: str


class VerificationConfirmIn(BaseModel):
    """人工确认验证状态（默认采纳建议；顾问也可指定推翻等）。"""

    status: str | None = Field(
        None,
        description="确认的验证状态；缺省时采纳 suggested_status。可选：未验证/成立/部分成立/推翻/待补充",
    )


class VerificationConfirmOut(BaseModel):
    """确认结果：更新后的假设节点 + 自动新增的偏差池条目（若有）。"""

    hypothesis_id: int
    verification_status: str
    deviation_created: bool = Field(False, description="是否自动新增了偏差池条目（status=推翻时）")
    deviation_object_id: int | None = None
    message: str | None = None


def iso(value: datetime | None) -> str | None:
    """datetime → ISO 字符串。"""
    return value.isoformat() if value else None
