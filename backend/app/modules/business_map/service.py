"""业务地图业务服务层（M2.1）。

职责：
- BusinessMapObject CRUD（按 level/mapType/reviewStatus 筛选；默认只查 reviewed，§7.3）
- PreAnalysis upsert（一个项目一份）
- BusinessMapDraft：获取/更新草稿 + 采纳（草稿→正式对象 + 版本快照，§7.1/§7.4）
- BusinessMapVersion：列表/详情/回滚（§7.4 V2.2 回滚）
- 五维健康：触发重评估 + 手动覆盖（§7.7，简单规则版见 health.py）

权限：路由层用 require_project_member/owner 保证项目隔离；本层只做业务。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BusinessMapDraft,
    BusinessMapObject,
    BusinessMapVersion,
    PreAnalysis,
    User,
)
from app.modules.business_map.health import (
    compute_five_dim_health,
    merge_health_into_payload,
)
from app.modules.projects.access import get_user_project_role
from app.schemas.business_map import (
    AdoptResult,
    BusinessMapDraftOut,
    BusinessMapDraftUpdate,
    BusinessMapObjectCreate,
    BusinessMapObjectOut,
    BusinessMapObjectUpdate,
    BusinessMapVersionOut,
    FiveDimHealthOut,
    PreAnalysisInput,
    PreAnalysisOut,
    iso,
)

# 草稿默认 7 天过期（§7.1.6）
DRAFT_TTL_DAYS = 7


# ─── 工具 ──────────────────────────────────────────────────────


async def _user_name(db: AsyncSession, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    u = await db.get(User, user_id)
    return (u.display_name or u.username) if u else None


def _obj_to_out(
    obj: BusinessMapObject,
    created_by_name: str | None,
    reviewed_by_name: str | None,
) -> BusinessMapObjectOut:
    return BusinessMapObjectOut(
        id=obj.id,
        project_id=obj.project_id,
        level=obj.level,
        name=obj.name,
        parent_id=obj.parent_id,
        map_type=obj.map_type,
        verification_status=obj.verification_status,
        linked_hypothesis_id=obj.linked_hypothesis_id,
        payload=obj.payload,
        review_status=obj.review_status,
        reviewed_by=obj.reviewed_by,
        reviewed_by_name=reviewed_by_name,
        reviewed_at=iso(obj.reviewed_at),
        generated_by_ai=bool(obj.generated_by_ai),
        created_by=obj.created_by,
        created_by_name=created_by_name,
        is_public=bool(obj.is_public),
        shared_with=obj.shared_with,
        sensitivity_level=obj.sensitivity_level,
        created_at=iso(obj.created_at),
        updated_at=iso(obj.updated_at),
    )


async def _enrich_obj(db: AsyncSession, obj: BusinessMapObject) -> BusinessMapObjectOut:
    return _obj_to_out(
        obj,
        await _user_name(db, obj.created_by),
        await _user_name(db, obj.reviewed_by),
    )


# ─── 业务地图对象 CRUD ────────────────────────────────────────


async def list_objects(
    db: AsyncSession,
    project_id: int,
    *,
    level: str | None = None,
    map_type: str | None = None,
    review_status: str | None = None,
    include_drafts: bool = False,
) -> list[BusinessMapObjectOut]:
    """列出业务地图对象。

    默认只返回 reviewed（§7.3 页面单一真源）；include_drafts=True 或显式传 review_status 时按条件查。
    """
    stmt = select(BusinessMapObject).where(BusinessMapObject.project_id == project_id)
    if review_status is not None:
        stmt = stmt.where(BusinessMapObject.review_status == review_status)
    elif not include_drafts:
        stmt = stmt.where(BusinessMapObject.review_status == "reviewed")
    if level is not None:
        stmt = stmt.where(BusinessMapObject.level == level)
    if map_type is not None:
        stmt = stmt.where(BusinessMapObject.map_type == map_type)
    stmt = stmt.order_by(BusinessMapObject.map_type, BusinessMapObject.level, BusinessMapObject.id)
    objs = (await db.execute(stmt)).scalars().all()
    return [await _enrich_obj(db, o) for o in objs]


async def get_object(
    db: AsyncSession, project_id: int, object_id: int
) -> BusinessMapObjectOut | None:
    obj = await db.get(BusinessMapObject, object_id)
    if obj is None or obj.project_id != project_id:
        return None
    return await _enrich_obj(db, obj)


async def create_object(
    db: AsyncSession, project_id: int, payload: BusinessMapObjectCreate, user: User
) -> BusinessMapObjectOut:
    obj = BusinessMapObject(
        project_id=project_id,
        level=payload.level,
        name=payload.name,
        parent_id=payload.parent_id,
        map_type=payload.map_type,
        verification_status=payload.verification_status,
        linked_hypothesis_id=payload.linked_hypothesis_id,
        payload=payload.payload,
        review_status=payload.review_status,
        generated_by_ai=1 if payload.generated_by_ai else 0,
        created_by=user.id,
        is_public=1 if payload.is_public else 0,
        shared_with=payload.shared_with,
        sensitivity_level=payload.sensitivity_level,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return await _enrich_obj(db, obj)


async def update_object(
    db: AsyncSession, project_id: int, object_id: int, payload: BusinessMapObjectUpdate
) -> BusinessMapObjectOut | None:
    obj = await db.get(BusinessMapObject, object_id)
    if obj is None or obj.project_id != project_id:
        return None
    if payload.level is not None:
        obj.level = payload.level
    if payload.name is not None:
        obj.name = payload.name
    if payload.parent_id is not None:
        obj.parent_id = payload.parent_id
    if payload.map_type is not None:
        obj.map_type = payload.map_type
    if payload.verification_status is not None:
        obj.verification_status = payload.verification_status
    if payload.linked_hypothesis_id is not None:
        obj.linked_hypothesis_id = payload.linked_hypothesis_id
    if payload.payload is not None:
        obj.payload = payload.payload
    if payload.review_status is not None:
        obj.review_status = payload.review_status
        obj.reviewed_at = datetime.now(timezone.utc) if payload.review_status == "reviewed" else obj.reviewed_at
    if payload.is_public is not None:
        obj.is_public = 1 if payload.is_public else 0
    if payload.shared_with is not None:
        obj.shared_with = payload.shared_with
    if payload.sensitivity_level is not None:
        obj.sensitivity_level = payload.sensitivity_level
    await db.commit()
    await db.refresh(obj)
    return await _enrich_obj(db, obj)


async def delete_object(db: AsyncSession, project_id: int, object_id: int) -> bool:
    obj = await db.get(BusinessMapObject, object_id)
    if obj is None or obj.project_id != project_id:
        return False
    await db.delete(obj)
    await db.commit()
    return True


# ─── 前置分析 ──────────────────────────────────────────────────


def _pre_to_out(pa: PreAnalysis, created_by_name: str | None) -> PreAnalysisOut:
    return PreAnalysisOut(
        id=pa.id,
        project_id=pa.project_id,
        industry_value_chain=pa.industry_value_chain,
        customer_position=pa.customer_position,
        industry_trends=pa.industry_trends,
        strategic_positioning=pa.strategic_positioning,
        digitalization_drivers=pa.digitalization_drivers,
        created_by=pa.created_by,
        created_by_name=created_by_name,
        created_at=iso(pa.created_at),
        updated_at=iso(pa.updated_at),
    )


async def get_pre_analysis(db: AsyncSession, project_id: int) -> PreAnalysisOut | None:
    pa = (
        await db.execute(
            select(PreAnalysis).where(PreAnalysis.project_id == project_id)
        )
    ).scalar_one_or_none()
    if pa is None:
        return None
    return _pre_to_out(pa, await _user_name(db, pa.created_by))


async def upsert_pre_analysis(
    db: AsyncSession, project_id: int, payload: PreAnalysisInput, user: User
) -> PreAnalysisOut:
    """创建或更新前置分析（一个项目一份）。"""
    pa = (
        await db.execute(
            select(PreAnalysis).where(PreAnalysis.project_id == project_id)
        )
    ).scalar_one_or_none()
    if pa is None:
        pa = PreAnalysis(
            project_id=project_id,
            industry_value_chain=payload.industry_value_chain,
            customer_position=payload.customer_position,
            industry_trends=payload.industry_trends,
            strategic_positioning=payload.strategic_positioning,
            digitalization_drivers=payload.digitalization_drivers,
            created_by=user.id,
        )
        db.add(pa)
    else:
        pa.industry_value_chain = payload.industry_value_chain
        pa.customer_position = payload.customer_position
        pa.industry_trends = payload.industry_trends
        pa.strategic_positioning = payload.strategic_positioning
        pa.digitalization_drivers = payload.digitalization_drivers
    await db.commit()
    await db.refresh(pa)
    return _pre_to_out(pa, await _user_name(db, pa.created_by))


# ─── 草稿区 + 采纳 ─────────────────────────────────────────────


def _draft_to_out(draft: BusinessMapDraft, created_by_name: str | None) -> BusinessMapDraftOut:
    return BusinessMapDraftOut(
        id=draft.id,
        project_id=draft.project_id,
        draft_data=draft.draft_data,
        source_session_id=draft.source_session_id,
        created_by=draft.created_by,
        created_by_name=created_by_name,
        status=draft.status,
        expires_at=iso(draft.expires_at),
        created_at=iso(draft.created_at),
        updated_at=iso(draft.updated_at),
    )


async def _mark_expired_drafts(db: AsyncSession, project_id: int) -> None:
    """把已过期且仍 active 的草稿标记为 expired（§7.1.6）。"""
    now = datetime.now(timezone.utc)
    await db.execute(
        BusinessMapDraft.__table__.update()
        .where(
            BusinessMapDraft.project_id == project_id,
            BusinessMapDraft.status == "active",
            BusinessMapDraft.expires_at.is_not(None),
            BusinessMapDraft.expires_at < now,
        )
        .values(status="expired")
    )
    await db.commit()


async def get_active_draft(
    db: AsyncSession, project_id: int
) -> BusinessMapDraftOut | None:
    """获取项目当前 active 草稿（顺带标记过期）。"""
    await _mark_expired_drafts(db, project_id)
    draft = (
        await db.execute(
            select(BusinessMapDraft)
            .where(
                BusinessMapDraft.project_id == project_id,
                BusinessMapDraft.status == "active",
            )
            .order_by(BusinessMapDraft.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if draft is None:
        return None
    return _draft_to_out(draft, await _user_name(db, draft.created_by))


async def upsert_draft(
    db: AsyncSession, project_id: int, payload: BusinessMapDraftUpdate, user: User
) -> BusinessMapDraftOut:
    """更新当前 active 草稿（不存在则创建）。整个业务地图为一个草稿单元（§7.1.7）。"""
    await _mark_expired_drafts(db, project_id)
    draft = (
        await db.execute(
            select(BusinessMapDraft)
            .where(
                BusinessMapDraft.project_id == project_id,
                BusinessMapDraft.status == "active",
            )
            .order_by(BusinessMapDraft.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if draft is None:
        draft = BusinessMapDraft(
            project_id=project_id,
            draft_data=payload.draft_data,
            source_session_id=payload.source_session_id,
            created_by=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=DRAFT_TTL_DAYS),
            status="active",
        )
        db.add(draft)
    else:
        draft.draft_data = payload.draft_data
        if payload.source_session_id is not None:
            draft.source_session_id = payload.source_session_id
        draft.expires_at = datetime.now(timezone.utc) + timedelta(days=DRAFT_TTL_DAYS)
    await db.commit()
    await db.refresh(draft)
    return _draft_to_out(draft, await _user_name(db, draft.created_by))


def _extract_object_specs(draft_data: dict | None) -> list[dict]:
    """从草稿数据中抽取对象规格列表，兼容 {objects:[...]} 与 [...] 两种形态。"""
    if not draft_data:
        return []
    if isinstance(draft_data, list):
        return [d for d in draft_data if isinstance(d, dict)]
    objs = draft_data.get("objects") if isinstance(draft_data, dict) else None
    if isinstance(objs, list):
        return [d for d in objs if isinstance(d, dict)]
    return []


async def _next_version_number(db: AsyncSession, project_id: int) -> int:
    max_no = (
        await db.execute(
            select(func.max(BusinessMapVersion.version_number)).where(
                BusinessMapVersion.project_id == project_id
            )
        )
    ).scalar_one()
    return int(max_no or 0) + 1


async def _snapshot_reviewed_objects(
    db: AsyncSession, project_id: int
) -> list[dict]:
    """序列化项目当前 reviewed 对象为快照数据。"""
    objs = (
        await db.execute(
            select(BusinessMapObject).where(
                BusinessMapObject.project_id == project_id,
                BusinessMapObject.review_status == "reviewed",
            )
        )
    ).scalars().all()
    return [
        {
            "level": o.level,
            "name": o.name,
            "parent_id": o.parent_id,
            "map_type": o.map_type,
            "verification_status": o.verification_status,
            "linked_hypothesis_id": o.linked_hypothesis_id,
            "payload": o.payload,
        }
        for o in objs
    ]


async def adopt_draft(
    db: AsyncSession, project_id: int, draft_id: int, user: User
) -> AdoptResult:
    """采纳草稿：草稿对象写入正式表 + 生成版本快照 + 草稿标记 adopted。

    Owner/admin 采纳 → 对象 review_status=reviewed（直接发布）；
    Deputy 采纳 → 对象 review_status=pending_review（待 Owner 审核，§3.4/§7.4）。
    """
    role = await get_user_project_role(db, project_id, user)
    if role is None:
        raise PermissionError("无权访问该项目")
    target_review_status = "reviewed" if role in ("owner", "admin") else "pending_review"

    draft = await db.get(BusinessMapDraft, draft_id)
    if draft is None or draft.project_id != project_id:
        raise ValueError("草稿不存在")
    if draft.status != "active":
        raise ValueError(f"草稿当前状态为 {draft.status}，不能采纳")

    specs = _extract_object_specs(draft.draft_data)
    created_count = 0
    for spec in specs:
        obj = BusinessMapObject(
            project_id=project_id,
            level=spec.get("level", "L1"),
            name=spec.get("name", "未命名"),
            parent_id=spec.get("parent_id"),
            map_type=spec.get("map_type", "hypothesis"),
            verification_status=spec.get("verification_status", "未验证"),
            linked_hypothesis_id=spec.get("linked_hypothesis_id"),
            payload=spec.get("payload"),
            review_status=target_review_status,
            generated_by_ai=1 if spec.get("generated_by_ai") else 0,
            created_by=user.id,
            is_public=1 if spec.get("is_public") else 0,
            shared_with=spec.get("shared_with"),
            sensitivity_level=spec.get("sensitivity_level", "internal"),
        )
        db.add(obj)
        created_count += 1

    # 采纳后对 reviewed 正式数据生成版本快照
    version_no = await _next_version_number(db, project_id)
    snapshot = await _snapshot_reviewed_objects(db, project_id)
    db.add(
        BusinessMapVersion(
            project_id=project_id,
            version_number=version_no,
            snapshot_data={"objects": snapshot},
            change_description=f"采纳草稿 #{draft.id}（{created_count} 个对象）",
            created_by=user.id,
        )
    )

    draft.status = "adopted"
    await db.commit()

    return AdoptResult(
        success=True,
        adopted_object_count=created_count,
        version_number=version_no,
        review_status=target_review_status,
        message="采纳成功" if target_review_status == "reviewed" else "已提交，待 Owner 审核",
    )


# ─── 版本管理 + 回滚 ───────────────────────────────────────────


def _version_to_out(v: BusinessMapVersion, created_by_name: str | None) -> BusinessMapVersionOut:
    return BusinessMapVersionOut(
        id=v.id,
        project_id=v.project_id,
        version_number=v.version_number,
        snapshot_data=v.snapshot_data,
        change_description=v.change_description,
        created_by=v.created_by,
        created_by_name=created_by_name,
        created_at=iso(v.created_at),
    )


async def list_versions(
    db: AsyncSession, project_id: int
) -> list[BusinessMapVersionOut]:
    rows = (
        await db.execute(
            select(BusinessMapVersion)
            .where(BusinessMapVersion.project_id == project_id)
            .order_by(BusinessMapVersion.version_number.desc())
        )
    ).scalars().all()
    out: list[BusinessMapVersionOut] = []
    for v in rows:
        out.append(_version_to_out(v, await _user_name(db, v.created_by)))
    return out


async def get_version(
    db: AsyncSession, project_id: int, version_id: int
) -> BusinessMapVersionOut | None:
    v = await db.get(BusinessMapVersion, version_id)
    if v is None or v.project_id != project_id:
        return None
    return _version_to_out(v, await _user_name(db, v.created_by))


async def rollback_to_version(
    db: AsyncSession, project_id: int, version_id: int, user: User
) -> BusinessMapVersionOut:
    """回滚到历史版本：先把当前 reviewed 对象存为审计快照，再用目标版本替换（§7.4 V2.2）。

    仅替换 reviewed 正式数据；草稿 / pending_review 不受影响。
    """
    target = await db.get(BusinessMapVersion, version_id)
    if target is None or target.project_id != project_id:
        raise ValueError("版本不存在")

    # 1) 当前 reviewed 状态存为审计快照（保证回滚可追溯）
    current_snapshot = await _snapshot_reviewed_objects(db, project_id)
    audit_no = await _next_version_number(db, project_id)
    db.add(
        BusinessMapVersion(
            project_id=project_id,
            version_number=audit_no,
            snapshot_data={"objects": current_snapshot},
            change_description=f"回滚到版本 #{target.version_number} 前的快照",
            created_by=user.id,
        )
    )

    # 2) 删除当前 reviewed 对象，用目标版本快照重建
    await db.execute(
        delete(BusinessMapObject).where(
            BusinessMapObject.project_id == project_id,
            BusinessMapObject.review_status == "reviewed",
        )
    )
    target_objs = (
        target.snapshot_data.get("objects") if target.snapshot_data else []
    )
    for spec in target_objs:
        db.add(
            BusinessMapObject(
                project_id=project_id,
                level=spec.get("level", "L1"),
                name=spec.get("name", "未命名"),
                parent_id=spec.get("parent_id"),
                map_type=spec.get("map_type", "hypothesis"),
                verification_status=spec.get("verification_status", "未验证"),
                linked_hypothesis_id=spec.get("linked_hypothesis_id"),
                payload=spec.get("payload"),
                review_status="reviewed",
                created_by=user.id,
            )
        )

    await db.commit()
    # 返回审计快照版本信息
    audit = (
        await db.execute(
            select(BusinessMapVersion)
            .where(BusinessMapVersion.project_id == project_id)
            .order_by(BusinessMapVersion.version_number.desc())
            .limit(1)
        )
    ).scalar_one()
    return _version_to_out(audit, await _user_name(db, audit.created_by))


# ─── 五维健康 ──────────────────────────────────────────────────


async def compute_node_health(
    db: AsyncSession, project_id: int, object_id: int
) -> FiveDimHealthOut | None:
    """对单个节点重新计算五维健康（规则版）并写回 payload.fiveDimHealth。"""
    obj = await db.get(BusinessMapObject, object_id)
    if obj is None or obj.project_id != project_id:
        return None
    health = compute_five_dim_health(obj.payload, obj.level)
    if not health:
        return None  # L4 等不计算五维健康
    obj.payload = merge_health_into_payload(obj.payload, health, source="auto")
    await db.commit()
    await db.refresh(obj)
    return FiveDimHealthOut(object_id=obj.id, five_dim_health=health, source="auto")


async def recompute_project_health(
    db: AsyncSession, project_id: int
) -> list[FiveDimHealthOut]:
    """对项目下所有支持五维健康的节点（L1/L2/L3）批量重评估。"""
    objs = (
        await db.execute(
            select(BusinessMapObject).where(
                BusinessMapObject.project_id == project_id,
                BusinessMapObject.level.in_(["L1", "L2", "L3"]),
            )
        )
    ).scalars().all()
    out: list[FiveDimHealthOut] = []
    for obj in objs:
        health = compute_five_dim_health(obj.payload, obj.level)
        if not health:
            continue
        obj.payload = merge_health_into_payload(obj.payload, health, source="auto")
        out.append(FiveDimHealthOut(object_id=obj.id, five_dim_health=health, source="auto"))
    await db.commit()
    return out


async def set_node_health(
    db: AsyncSession, project_id: int, object_id: int, health: dict, user: User
) -> FiveDimHealthOut | None:
    """手动覆盖某节点的五维健康评分（标记 source=manual，§7.7）。"""
    obj = await db.get(BusinessMapObject, object_id)
    if obj is None or obj.project_id != project_id:
        return None
    obj.payload = merge_health_into_payload(obj.payload, health, source="manual")
    await db.commit()
    await db.refresh(obj)
    return FiveDimHealthOut(object_id=obj.id, five_dim_health=health, source="manual")
