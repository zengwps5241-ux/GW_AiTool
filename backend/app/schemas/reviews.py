"""统一采纳/审批相关 Pydantic 模型（M2.4）。

跨模块统一「待审批列表 + approve/reject」层（§3.4 / §7.1 / §7.3）。
覆盖四类可审批实体：business_map_object / stakeholder_card / visit_record / evidence_source
（均具备 review_status / reviewed_by / reviewed_at 三列）。

schemas=plain BaseModel（无 orm_mode），与既有 schema 风格一致。
"""

from pydantic import BaseModel, Field


class PendingReviewItem(BaseModel):
    """待审批项（统一形态，跨模块聚合）。

    用于 GET /pending-reviews 列表，以及 approve/reject 的返回结果
   （返回时 review_status 反映动作后的实际状态：reviewed / rejected）。
    """

    entity_type: str = Field(..., description="实体类型：business_map_object/stakeholder_card/visit_record/evidence_source")
    entity_id: int
    project_id: int
    entity_label: str = Field(..., description="实体中文名（业务地图节点/角色卡/拜访记录/证据）")
    name: str | None = Field(None, description="展示名（节点名/角色名/摘要/证据内容，截断）")
    review_status: str
    submitted_by: int | None = Field(None, description="提交者 user_id（created_by）")
    submitted_by_name: str | None = None
    submitted_at: str | None = Field(None, description="提交时间（created_at ISO）")
    reviewed_by: int | None = None
    reviewed_by_name: str | None = None
    reviewed_at: str | None = None


class AdoptRequest(BaseModel):
    """统一采纳请求（POST /adopt）。

    M2.4 阶段仅支持 entity_type='business_map_draft'（整图草稿单元，§7.1.7），
    委派给 business_map.adopt_draft（保留版本快照语义，§7.4/#18）。
    营销地图/拜访记录的草稿采纳在 M3.1.1（save_xxx_draft 工具）落地后扩展。
    """

    entity_type: str = Field("business_map_draft", description="采纳目标类型")
    draft_id: int = Field(..., description="草稿/候选 ID")


class RejectRequest(BaseModel):
    """驳回请求（POST /reviews/.../reject）。

    comment 为驳回意见（§3.4「驳回 + 修改意见 → 退回副手」）。
    M2.4 数据层将实体置 rejected 退回；意见的持久化存储留待 Phase 3 对话 Banner 审核流。
    """

    comment: str | None = Field(None, description="驳回意见（可选）")
