"""统一采纳/审批业务服务层（M2.4）。

职责（§3.4 WF07 审核流程 / §7.1 候选区 / §7.3 页面单一真源=reviewed）：
- 待审批聚合：跨模块汇总 review_status='pending_review' 的实体（业务地图节点/角色卡/拜访记录/证据）。
- approve / reject：Owner 对单条待审批项翻状态（→ reviewed 发布 / → rejected 退回）。
- adopt 派发：统一采纳入口，按 entity_type 委派到对应模块（business_map_draft → business_map.adopt_draft）。

设计（决策 #28）：保留各模块自有的 adopt（business_map.adopt_draft 因带「整图草稿单元 + 版本快照」
专有语义而不抽象），仅在跨模块处新增统一审批层。四类实体共享 review_status/reviewed_by/reviewed_at
三列，故用「实体注册表」把列表/审批动作参数化，新增可审批实体只需登记一行。

权限：列表 GET 用 require_project_member（项目内透明）；approve/reject/adopt 的 Owner 约束在路由层。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BusinessMapObject,
    EvidenceSource,
    StakeholderCard,
    User,
    VisitRecord,
)
from app.modules.business_map import service as business_map_service
from app.modules.projects.access import get_user_project_role
from app.schemas.business_map import AdoptResult
from app.schemas.reviews import AdoptRequest, PendingReviewItem


# ─── 可审批实体注册表 ──────────────────────────────────────────


def _trunc(text: str | None, limit: int = 80) -> str | None:
    if not text:
        return None
    return text if len(text) <= limit else text[:limit] + "…"


@dataclass(frozen=True)
class ReviewableAdapter:
    """单个可审批实体的适配元数据。"""

    entity_type: str
    model: type
    label: str  # 中文展示标签
    name_extractor: Callable[[Any], str | None]  # 从实例取展示名


# 四类实体均具备 review_status / reviewed_by / reviewed_at / created_by / created_at
REGISTRY: dict[str, ReviewableAdapter] = {
    "business_map_object": ReviewableAdapter(
        "business_map_object", BusinessMapObject, "业务地图节点", lambda o: o.name
    ),
    "stakeholder_card": ReviewableAdapter(
        "stakeholder_card", StakeholderCard, "角色卡", lambda o: o.name
    ),
    "visit_record": ReviewableAdapter(
        "visit_record", VisitRecord, "拜访记录",
        lambda o: _trunc(o.summary) or o.visit_type or None,
    ),
    "evidence_source": ReviewableAdapter(
        "evidence_source", EvidenceSource, "证据",
        lambda o: _trunc(o.content),
    ),
}

# 统一排序：按提交时间倒序（最新提交优先审批）
_ORDERED_TYPES = list(REGISTRY.keys())


async def _user_name(db: AsyncSession, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    u = await db.get(User, user_id)
    return (u.display_name or u.username) if u else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def _build_item(
    db: AsyncSession, adapter: ReviewableAdapter, obj: Any
) -> PendingReviewItem:
    return PendingReviewItem(
        entity_type=adapter.entity_type,
        entity_id=obj.id,
        project_id=obj.project_id,
        entity_label=adapter.label,
        name=adapter.name_extractor(obj),
        review_status=obj.review_status,
        submitted_by=obj.created_by,
        submitted_by_name=await _user_name(db, obj.created_by),
        submitted_at=_iso(obj.created_at),
        reviewed_by=obj.reviewed_by,
        reviewed_by_name=await _user_name(db, obj.reviewed_by),
        reviewed_at=_iso(obj.reviewed_at),
    )


# ─── 待审批列表（跨模块聚合） ─────────────────────────────────


async def list_pending_reviews(
    db: AsyncSession, project_id: int, *, entity_type: str | None = None
) -> list[PendingReviewItem]:
    """汇总项目下所有 pending_review 实体（§3.4 待主手审核区）。

    可用 entity_type 仅查某一类。结果按提交时间倒序。
    """
    types = [entity_type] if entity_type else _ORDERED_TYPES
    items: list[PendingReviewItem] = []
    for et in types:
        adapter = REGISTRY.get(et)
        if adapter is None:
            raise ValueError(f"未知的实体类型: {et}")
        rows = (
            await db.execute(
                select(adapter.model)
                .where(
                    adapter.model.project_id == project_id,
                    adapter.model.review_status == "pending_review",
                )
                .order_by(adapter.model.created_at.desc())
            )
        ).scalars().all()
        for obj in rows:
            items.append(await _build_item(db, adapter, obj))
    # 跨类型统一按提交时间倒序
    items.sort(key=lambda it: it.submitted_at or "", reverse=True)
    return items


# ─── approve / reject ─────────────────────────────────────────


async def _fetch_pending(
    db: AsyncSession, project_id: int, entity_type: str, entity_id: int
) -> Any:
    """取一条 pending_review 实体；不存在/跨项目/非 pending 抛错。"""
    adapter = REGISTRY.get(entity_type)
    if adapter is None:
        raise ValueError(f"未知的实体类型: {entity_type}")
    obj = await db.get(adapter.model, entity_id)
    if obj is None or obj.project_id != project_id:
        raise LookupError("待审批项不存在")
    if obj.review_status != "pending_review":
        raise ValueError(f"该项当前状态为 {obj.review_status}，无法审批")
    return obj, adapter


async def approve_review(
    db: AsyncSession, project_id: int, entity_type: str, entity_id: int, user: User
) -> PendingReviewItem:
    """Owner 通过待审批项 → review_status=reviewed（发布，页面立即可见，§7.3）。"""
    obj, adapter = await _fetch_pending(db, project_id, entity_type, entity_id)
    obj.review_status = "reviewed"
    obj.reviewed_by = user.id
    obj.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return await _build_item(db, adapter, obj)


async def reject_review(
    db: AsyncSession,
    project_id: int,
    entity_type: str,
    entity_id: int,
    user: User,
    *,
    comment: str | None = None,
) -> PendingReviewItem:
    """Owner 驳回待审批项 → review_status=rejected（退回，§3.4）。

    comment 为驳回意见；M2.4 数据层不持久化意见（Phase 3 对话 Banner 审核流承载）。
    """
    obj, adapter = await _fetch_pending(db, project_id, entity_type, entity_id)
    obj.review_status = "rejected"
    obj.reviewed_by = user.id
    obj.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return await _build_item(db, adapter, obj)


# ─── 统一采纳派发 ─────────────────────────────────────────────


async def adopt(
    db: AsyncSession, project_id: int, payload: AdoptRequest, user: User
) -> AdoptResult:
    """统一采纳入口（POST /adopt）。

    按 entity_type 委派：
    - business_map_draft → business_map.adopt_draft（Owner→reviewed / Deputy→pending_review + 版本快照）。
    - 其它类型（营销/拜访草稿）留待 M3.1.1 落地后扩展。

    权限由调用者项目角色决定目标 review_status（在 business_map.adopt_draft 内判定）。
    """
    # 项目成员校验（与各模块 adopt 一致）
    role = await get_user_project_role(db, project_id, user)
    if role is None:
        raise PermissionError("无权访问该项目")

    if payload.entity_type == "business_map_draft":
        return await business_map_service.adopt_draft(
            db, project_id, payload.draft_id, user
        )
    raise ValueError(f"暂不支持的采纳类型: {payload.entity_type}")
