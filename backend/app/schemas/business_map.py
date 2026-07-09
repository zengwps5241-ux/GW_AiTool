"""业务地图相关 Pydantic 模型（M2.1）。

与 app.modules.business_map.service 对齐。schemas=plain BaseModel（无 orm_mode）。
payload 为层级差异化的 JSONB，schema 层不约束其内部结构（由 Skill/前端约定）。
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ─── 业务地图节点 ──────────────────────────────────────────────


class BusinessMapObjectCreate(BaseModel):
    """创建业务地图节点。"""

    level: str = Field(..., pattern="^(L1|L2|L3|L4)$", description="层级")
    name: str = Field(..., min_length=1, max_length=200)
    parent_id: int | None = Field(None, description="父节点 ID")
    map_type: str = Field("hypothesis", pattern="^(hypothesis|current)$")
    verification_status: str = Field("未验证")
    linked_hypothesis_id: int | None = Field(None, description="current 节点关联的假设节点")
    payload: dict[str, Any] | None = Field(None, description="层级差异化载荷")
    # 手动新增默认直接进正式库（reviewed，§7.3）；AI 产出走草稿→采纳流程
    review_status: str = Field("reviewed", pattern="^(draft|pending_review|reviewed|rejected)$")
    generated_by_ai: bool = False
    is_public: bool = False
    shared_with: list[int] | None = None
    sensitivity_level: str = "internal"


class BusinessMapObjectUpdate(BaseModel):
    """更新业务地图节点（所有字段可选）。"""

    level: str | None = Field(None, pattern="^(L1|L2|L3|L4)$")
    name: str | None = Field(None, min_length=1, max_length=200)
    parent_id: int | None = None
    map_type: str | None = Field(None, pattern="^(hypothesis|current)$")
    verification_status: str | None = None
    linked_hypothesis_id: int | None = None
    payload: dict[str, Any] | None = None
    review_status: str | None = Field(None, pattern="^(draft|pending_review|reviewed|rejected)$")
    is_public: bool | None = None
    shared_with: list[int] | None = None
    sensitivity_level: str | None = None


class BusinessMapObjectOut(BaseModel):
    """业务地图节点输出。"""

    id: int
    project_id: int
    level: str
    name: str
    parent_id: int | None = None
    map_type: str
    verification_status: str
    linked_hypothesis_id: int | None = None
    payload: dict[str, Any] | None = None
    review_status: str
    reviewed_by: int | None = None
    reviewed_by_name: str | None = None
    reviewed_at: str | None = None
    generated_by_ai: bool = False
    created_by: int
    created_by_name: str | None = None
    is_public: bool = False
    shared_with: list[int] | None = None
    sensitivity_level: str = "internal"
    created_at: str | None = None
    updated_at: str | None = None


# ─── 前置分析 ──────────────────────────────────────────────────


class PreAnalysisInput(BaseModel):
    """前置分析创建/更新（一个项目一份，upsert）。"""

    industry_value_chain: str | None = None
    customer_position: str | None = None
    industry_trends: str | None = None
    strategic_positioning: str | None = None
    digitalization_drivers: str | None = None


class PreAnalysisOut(BaseModel):
    """前置分析输出。"""

    id: int
    project_id: int
    industry_value_chain: str | None = None
    customer_position: str | None = None
    industry_trends: str | None = None
    strategic_positioning: str | None = None
    digitalization_drivers: str | None = None
    created_by: int
    created_by_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ─── 草稿区 ────────────────────────────────────────────────────


class BusinessMapDraftUpdate(BaseModel):
    """更新草稿内容（增量）。"""

    draft_data: dict[str, Any] = Field(..., description="草稿内容（整张业务地图）")
    source_session_id: str | None = None


class BusinessMapDraftOut(BaseModel):
    """草稿输出。"""

    id: int
    project_id: int
    draft_data: dict[str, Any] | None = None
    source_session_id: str | None = None
    created_by: int
    created_by_name: str | None = None
    status: str
    expires_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AdoptResult(BaseModel):
    """采纳草稿结果。"""

    success: bool
    adopted_object_count: int
    version_number: int
    review_status: str = Field(..., description="采纳后对象的审核状态：reviewed(Owner) / pending_review(Deputy)")
    message: str | None = None


# ─── 版本 ──────────────────────────────────────────────────────


class BusinessMapVersionOut(BaseModel):
    """版本快照输出。"""

    id: int
    project_id: int
    version_number: int
    snapshot_data: dict[str, Any] | None = None
    change_description: str | None = None
    created_by: int
    created_by_name: str | None = None
    created_at: str | None = None


# ─── 五维健康 ──────────────────────────────────────────────────


class FiveDimHealthOut(BaseModel):
    """某节点的五维健康评分输出。"""

    object_id: int
    five_dim_health: dict[str, Any]
    source: str = Field(..., description="auto（规则计算）/ manual（手动覆盖）")


def iso(value: datetime | None) -> str | None:
    """datetime → ISO 字符串。"""
    return value.isoformat() if value else None
