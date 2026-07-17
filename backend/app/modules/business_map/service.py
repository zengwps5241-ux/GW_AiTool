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

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BusinessMapDraft,
    BusinessMapObject,
    BusinessMapVersion,
    ChatSession,
    PreAnalysis,
    User,
)
from app.modules.business_map.health import (
    FIVE_DIM_KEYS,
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
    VersionDiffChangedItem,
    VersionDiffItem,
    VersionDiffOut,
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
        payload=_payload_with_health_source(payload.payload),
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
        obj.payload = _merge_updated_payload(obj.payload, payload.payload)
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
    pa = await _apply_pre_analysis(db, project_id, payload, user)
    await db.commit()
    await db.refresh(pa)
    return _pre_to_out(pa, await _user_name(db, pa.created_by))


async def _apply_pre_analysis(
    db: AsyncSession, project_id: int, payload: PreAnalysisInput, user: User
) -> PreAnalysis:
    """在当前事务中创建或更新前置分析，不提交。"""
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
    return pa


# ─── 草稿区 + 采纳 ─────────────────────────────────────────────


def _draft_to_out(draft: BusinessMapDraft, created_by_name: str | None) -> BusinessMapDraftOut:
    return BusinessMapDraftOut(
        id=draft.id,
        project_id=draft.project_id,
        draft_data=draft.draft_data,
        previous_data=draft.previous_data,
        revision=draft.revision if draft.revision is not None else 1,
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
    """更新当前 active 草稿（不存在则创建）。整个业务地图为一个草稿单元（§7.1.7）。

    增量更新语义（§7.2 Chat 调整）：覆盖前把旧 draft_data 存入 previous_data、
    revision +1，使前端可对「上一版 vs 当前版」做 diff 对比。首次生成 revision=1。
    """
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
            previous_data=None,
            revision=1,
            source_session_id=payload.source_session_id,
            created_by=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=DRAFT_TTL_DAYS),
            status="active",
        )
        db.add(draft)
    else:
        # 增量更新：保留上一版内容供 diff，修订号递增
        draft.previous_data = draft.draft_data
        draft.draft_data = payload.draft_data
        draft.revision = (draft.revision or 1) + 1
        if payload.source_session_id is not None:
            draft.source_session_id = payload.source_session_id
        draft.expires_at = datetime.now(timezone.utc) + timedelta(days=DRAFT_TTL_DAYS)
    await db.commit()
    await db.refresh(draft)
    return _draft_to_out(draft, await _user_name(db, draft.created_by))


def is_draft_ready_for_adoption(draft_data: dict | None) -> bool:
    """业务地图草稿是否已经完成到可采纳状态。

    旧版草稿没有 ready_for_adoption 字段，按可采纳处理，避免破坏既有流程。
    新的假设地图分阶段流程会在阶段保存时显式写入 False，最终完成后再改为 True。
    """
    if not isinstance(draft_data, dict):
        return True
    return draft_data.get("ready_for_adoption") is not False


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


def _extract_pre_analysis_spec(draft_data: dict | None) -> dict | None:
    """从业务地图草稿中抽取项目前置分析。"""
    if not isinstance(draft_data, dict):
        return None
    pre_analysis = draft_data.get("pre_analysis")
    return pre_analysis if isinstance(pre_analysis, dict) else None


def _pre_analysis_text(value) -> str | None:
    """把模型产出的前置分析字段归一化为可入库文本。"""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


LEVEL_ORDER = ("L1", "L2", "L3", "L4")
PARENT_LEVEL: dict[str, str | None] = {
    "L1": None,
    "L2": "L1",
    "L3": "L2",
    "L4": "L3",
}


def _spec_temp_id(spec: dict, fallback_index: int) -> str:
    value = spec.get("temp_id") or spec.get("tempId")
    if value:
        return str(value)
    level = spec.get("level", "L1")
    return f"__auto_{level}_{fallback_index}"


def _spec_parent_temp_id(spec: dict) -> str | None:
    value = (
        spec.get("parent_temp_id")
        or spec.get("parentTempId")
        or spec.get("parent_tempId")
    )
    return str(value) if value else None


def _spec_parent_name(spec: dict) -> str | None:
    value = spec.get("parent_name") or spec.get("parentName")
    payload = spec.get("payload")
    if not value and isinstance(payload, dict):
        value = payload.get("parentName") or payload.get("parent_name")
    return str(value) if value else None


def _resolve_parent_id(
    spec: dict,
    *,
    level: str,
    temp_id_to_db_id: dict[str, int],
    name_to_db_id: dict[tuple[str, str], int],
) -> int | None:
    expected_parent_level = PARENT_LEVEL.get(level)
    if expected_parent_level is None:
        return None

    parent_temp_id = _spec_parent_temp_id(spec)
    if parent_temp_id:
        parent_id = temp_id_to_db_id.get(parent_temp_id)
        if parent_id is None:
            raise ValueError(
                f"{level} 节点「{spec.get('name', '未命名')}」的 parent_temp_id={parent_temp_id} 未找到对应父节点"
            )
        return parent_id

    raw_parent_id = spec.get("parent_id")
    if isinstance(raw_parent_id, int):
        return raw_parent_id

    parent_name = _spec_parent_name(spec)
    if parent_name:
        parent_id = name_to_db_id.get((expected_parent_level, parent_name))
        if parent_id is not None:
            return parent_id

    raise ValueError(
        f"{level} 节点「{spec.get('name', '未命名')}」缺少有效父级关系。"
        "请重新生成草稿，确保 L2/L3/L4 均包含 parent_temp_id。"
    )


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
    # 过期校验（§7.1.6）：adopt 是写路径，须主动把已过期的 active 草稿标记 expired，
    # 不能依赖 get/upsert 时的懒标记——否则一个 expires_at 已过但未被访问过的草稿
    # 仍 status=active，会被错误采纳。标记后 refresh 复验状态。
    await _mark_expired_drafts(db, project_id)
    await db.refresh(draft)
    if draft.status != "active":
        raise ValueError(f"草稿当前状态为 {draft.status}，不能采纳")
    if not is_draft_ready_for_adoption(draft.draft_data):
        raise ValueError("该业务地图草稿仍在分阶段生成中，尚未完成，不能采纳")

    pre_analysis_spec = _extract_pre_analysis_spec(draft.draft_data)
    if pre_analysis_spec is not None:
        await _apply_pre_analysis(
            db,
            project_id,
            PreAnalysisInput(
                industry_value_chain=_pre_analysis_text(pre_analysis_spec.get("industry_value_chain")),
                customer_position=_pre_analysis_text(pre_analysis_spec.get("customer_position")),
                industry_trends=_pre_analysis_text(pre_analysis_spec.get("industry_trends")),
                strategic_positioning=_pre_analysis_text(pre_analysis_spec.get("strategic_positioning")),
                digitalization_drivers=_pre_analysis_text(pre_analysis_spec.get("digitalization_drivers")),
            ),
            user,
        )

    specs = _extract_object_specs(draft.draft_data)
    created_count = 0
    temp_id_to_db_id: dict[str, int] = {}
    name_to_db_id: dict[tuple[str, str], int] = {}
    indexed_specs = list(enumerate(specs))
    for level in LEVEL_ORDER:
        for spec_index, spec in indexed_specs:
            if spec.get("level", "L1") != level:
                continue
            parent_id = _resolve_parent_id(
                spec,
                level=level,
                temp_id_to_db_id=temp_id_to_db_id,
                name_to_db_id=name_to_db_id,
            )
            obj = BusinessMapObject(
                project_id=project_id,
                level=level,
                name=spec.get("name", "未命名"),
                parent_id=parent_id,
                map_type=spec.get("map_type", "hypothesis"),
                verification_status=spec.get("verification_status", "未验证"),
                linked_hypothesis_id=spec.get("linked_hypothesis_id"),
                payload=_payload_with_health_source(spec.get("payload")),
                review_status=target_review_status,
                generated_by_ai=1 if spec.get("generated_by_ai") else 0,
                created_by=user.id,
                is_public=1 if spec.get("is_public") else 0,
                shared_with=spec.get("shared_with"),
                sensitivity_level=spec.get("sensitivity_level", "internal"),
            )
            db.add(obj)
            await db.flush()
            temp_id_to_db_id[_spec_temp_id(spec, spec_index)] = obj.id
            name_to_db_id[(level, obj.name)] = obj.id
            created_count += 1

    # 采纳后对 reviewed 正式数据生成版本快照
    version_no = await _next_version_number(db, project_id)
    await db.flush()
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
    if draft.source_session_id:
        session = await db.get(ChatSession, draft.source_session_id)
        if session is not None and session.workflow_status == "active":
            session.workflow_status = "adopted"
            session.workflow_stage = "done"
    await db.commit()
    # 审计埋点（决策 #64）
    from app.modules.audit.service import log_audit

    await log_audit(
        db, user.id, "adopt", "business_map", str(project_id),
        detail={"before": {"draft_id": draft_id, "draft_status": "active"},
                "after": {"draft_status": "adopted", "version": version_no,
                          "object_count": created_count,
                          "pre_analysis": bool(pre_analysis_spec),
                          "review_status": target_review_status}},
    )

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
    # 审计埋点（决策 #64）
    from app.modules.audit.service import log_audit

    await log_audit(
        db, user.id, "rollback", "business_map", str(project_id),
        detail={"after": {"rolled_back_to_version": target.version_number}},
    )
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


# ─── 版本对比（M5.3.2）──────────────────────────────────────────


def _snapshot_objects(version: BusinessMapVersion) -> list[dict]:
    """从版本快照中抽取对象列表（兼容空快照）。"""
    objs = (version.snapshot_data or {}).get("objects") if version.snapshot_data else None
    if not isinstance(objs, list):
        return []
    return [o for o in objs if isinstance(o, dict)]


def _diff_key(obj: dict) -> tuple[str, str]:
    """diff 比对键：(level, name)。同名同层视为同一节点。"""
    return (obj.get("level") or "", obj.get("name") or "")


async def diff_version_against_current(
    db: AsyncSession, project_id: int, version_id: int
) -> VersionDiffOut | None:
    """版本快照 vs 当前 reviewed 数据的对比（§7.4 M5.3.2）。

    按 (level, name) 键比对：added（当前有快照无）/ removed（快照有当前无）/
    changed（两边都有但 map_type / verification_status 变化）。
    不比 payload（含五维健康派生数据，噪声大）；仅结构性字段差异。
    """
    version = await db.get(BusinessMapVersion, version_id)
    if version is None or version.project_id != project_id:
        return None
    snap = _snapshot_objects(version)
    current = await _snapshot_reviewed_objects(db, project_id)
    snap_map = {_diff_key(o): o for o in snap}
    cur_map = {_diff_key(o): o for o in current}

    added = [
        VersionDiffItem(level=o.get("level"), name=o.get("name"))
        for k, o in cur_map.items()
        if k not in snap_map
    ]
    removed = [
        VersionDiffItem(level=o.get("level"), name=o.get("name"))
        for k, o in snap_map.items()
        if k not in cur_map
    ]
    changed: list[VersionDiffChangedItem] = []
    for k, cur_o in cur_map.items():
        snap_o = snap_map.get(k)
        if snap_o is None:
            continue
        for field in ("map_type", "verification_status"):
            sv = snap_o.get(field)
            cv = cur_o.get(field)
            if sv != cv:
                changed.append(
                    VersionDiffChangedItem(
                        level=cur_o.get("level"),
                        name=cur_o.get("name"),
                        field=field,
                        snapshot=sv,
                        current=cv,
                    )
                )
    return VersionDiffOut(
        version_number=version.version_number,
        snapshot_count=len(snap),
        current_count=len(current),
        added=added,
        removed=removed,
        changed=changed,
    )


# ─── 五维健康 ──────────────────────────────────────────────────


async def compute_node_health(
    db: AsyncSession, project_id: int, object_id: int
) -> FiveDimHealthOut | None:
    """规则版五维健康计算已停用。

    当前口径：五维健康只来自 agent 假设诊断或人工调整，后端不再基于字段完整度自动计算。
    """
    return None


async def recompute_project_health(
    db: AsyncSession, project_id: int
) -> list[FiveDimHealthOut]:
    """规则版批量重评估已停用。"""
    return []


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


def _is_valid_five_dim_health(value: object) -> bool:
    """校验 agent/人工提交的五维健康结构是否完整。"""
    if not isinstance(value, dict):
        return False
    for dim in FIVE_DIM_KEYS:
        item = value.get(dim)
        if not isinstance(item, dict):
            return False
        score = item.get("score")
        if not isinstance(score, int) or score < 1 or score > 5:
            return False
        desc = item.get("desc")
        if not isinstance(desc, str) or not desc.strip():
            return False
    return True


def _payload_with_health_source(payload: dict | None, source: str = "ai_hypothesis") -> dict | None:
    """保留结构完整的五维健康，并标记来源；不做后端自动计算。"""
    if payload is None:
        return None
    health = payload.get("fiveDimHealth")
    if not _is_valid_five_dim_health(health):
        out = dict(payload)
        out.pop("fiveDimHealth", None)
        out.pop("_healthSource", None)
        return out
    current_source = payload.get("_healthSource")
    return merge_health_into_payload(
        payload,
        health,  # type: ignore[arg-type]
        source=current_source if current_source in ("ai_hypothesis", "manual") else source,
    )


def _merge_updated_payload(prev_payload: dict | None, new_payload: dict | None) -> dict | None:
    """更新对象 payload 时保留既有五维健康，不做规则重算。"""
    if new_payload is None:
        return prev_payload
    if _is_valid_five_dim_health(new_payload.get("fiveDimHealth")):
        return _payload_with_health_source(new_payload)
    prev_health = (prev_payload or {}).get("fiveDimHealth")
    prev_source = (prev_payload or {}).get("_healthSource")
    if _is_valid_five_dim_health(prev_health):
        return merge_health_into_payload(
            new_payload,
            prev_health,  # type: ignore[arg-type]
            source=prev_source if prev_source in ("ai_hypothesis", "manual") else "ai_hypothesis",
        )
    return _payload_with_health_source(new_payload)
