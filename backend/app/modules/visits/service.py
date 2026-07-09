"""拜访记录业务服务层（M2.3）。

职责：
- VisitRecord CRUD（按 visitType/角色/日期 筛选；时间倒序；默认只查 reviewed，§7.3）
- EvidenceSource CRUD（按 类型/强度/角色/关联假设 多维筛选）
- 证据验证联动（§7.5）：证据关联假设节点 → 建议验证状态 → 人工确认 → 更新 verificationStatus + 推翻时自动新增偏差池条目
- 态度变化自动记录（§7.6）：角色态度信号类证据关联角色卡 → 调 marketing_map.record_stance_change

权限：路由层 require_project_member 保证项目隔离；本层只做业务。
派生统计（evidenceCount/verifiedHypotheses）读取时按关联证据计算，不落库。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BusinessMapObject,
    EvidenceSource,
    StakeholderCard,
    User,
    VisitRecord,
)
from app.modules.marketing_map import service as mm_service
from app.schemas.visit import (
    EvidenceSourceCreate,
    EvidenceSourceOut,
    EvidenceSourceUpdate,
    VerificationConfirmIn,
    VerificationConfirmOut,
    VerificationSuggestionOut,
    VisitRecordCreate,
    VisitRecordOut,
    VisitRecordUpdate,
    iso,
)

# §7.5.1 阈值：强证据数达到此值 → 建议标记为「成立」
STRONG_FOR_ESTABLISHED = 3


# ─── 工具 ──────────────────────────────────────────────────────


async def _user_name(db: AsyncSession, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    u = await db.get(User, user_id)
    return (u.display_name or u.username) if u else None


async def _card_name(db: AsyncSession, card_id: int | None) -> str | None:
    if card_id is None:
        return None
    c = await db.get(StakeholderCard, card_id)
    return c.name if c else None


async def _hypothesis_name(db: AsyncSession, hyp_id: int | None) -> str | None:
    if hyp_id is None:
        return None
    o = await db.get(BusinessMapObject, hyp_id)
    return o.name if o else None


async def _visit_stats(
    db: AsyncSession, project_id: int, visit_id: int
) -> tuple[int, int]:
    """单次拜访的派生统计：(证据总数, 关联的假设数)。

    verifiedHypotheses = 该拜访 reviewed 证据中 distinct 非空 relatedHypothesisId 的数量。
    """
    rows = (
        await db.execute(
            select(EvidenceSource.related_hypothesis_id).where(
                EvidenceSource.project_id == project_id,
                EvidenceSource.visit_record_id == visit_id,
                EvidenceSource.review_status == "reviewed",
            )
        )
    ).scalars().all()
    evidence_count = len(rows)
    verified = len({h for h in rows if h is not None})
    return evidence_count, verified


def _visit_to_out(
    v: VisitRecord,
    created_by_name: str | None,
    reviewed_by_name: str | None,
    evidence_count: int,
    verified_hypotheses: int,
) -> VisitRecordOut:
    return VisitRecordOut(
        id=v.id,
        project_id=v.project_id,
        visit_date=v.visit_date,
        visit_type=v.visit_type,
        participants_our=v.participants_our,
        participants_client=v.participants_client,
        location=v.location,
        duration=v.duration,
        summary=v.summary,
        next_steps=v.next_steps,
        key_takeaways=v.key_takeaways,
        related_card_ids=v.related_card_ids,
        evidence_count=evidence_count,
        verified_hypotheses=verified_hypotheses,
        review_status=v.review_status,
        reviewed_by=v.reviewed_by,
        reviewed_by_name=reviewed_by_name,
        reviewed_at=iso(v.reviewed_at),
        created_by=v.created_by,
        created_by_name=created_by_name,
        is_public=bool(v.is_public),
        shared_with=v.shared_with,
        sensitivity_level=v.sensitivity_level,
        created_at=iso(v.created_at),
        updated_at=iso(v.updated_at),
    )


async def _enrich_visit(db: AsyncSession, v: VisitRecord) -> VisitRecordOut:
    evidence_count, verified = await _visit_stats(db, v.project_id, v.id)
    return _visit_to_out(
        v,
        await _user_name(db, v.created_by),
        await _user_name(db, v.reviewed_by),
        evidence_count,
        verified,
    )


def _evidence_to_out(
    e: EvidenceSource,
    created_by_name: str | None,
    reviewed_by_name: str | None,
) -> EvidenceSourceOut:
    return EvidenceSourceOut(
        id=e.id,
        project_id=e.project_id,
        visit_record_id=e.visit_record_id,
        evidence_type=e.evidence_type,
        strength=e.strength,
        strength_note=e.strength_note,
        content=e.content,
        source_role_id=e.source_role_id,
        source_role_name=e.source_role_name,
        related_hypothesis_id=e.related_hypothesis_id,
        related_hypothesis_name=e.related_hypothesis_name,
        implied_from_stance=e.implied_from_stance,
        implied_to_stance=e.implied_to_stance,
        review_status=e.review_status,
        reviewed_by=e.reviewed_by,
        reviewed_by_name=reviewed_by_name,
        reviewed_at=iso(e.reviewed_at),
        created_by=e.created_by,
        created_by_name=created_by_name,
        created_at=iso(e.created_at),
        updated_at=iso(e.updated_at),
    )


async def _enrich_evidence(db: AsyncSession, e: EvidenceSource) -> EvidenceSourceOut:
    return _evidence_to_out(
        e,
        await _user_name(db, e.created_by),
        await _user_name(db, e.reviewed_by),
    )


# ─── 拜访记录 CRUD ─────────────────────────────────────────────


async def list_visits(
    db: AsyncSession,
    project_id: int,
    *,
    visit_type: str | None = None,
    card_id: int | None = None,
    review_status: str | None = None,
    include_drafts: bool = False,
) -> list[VisitRecordOut]:
    """列出拜访记录（时间倒序；按类型/角色筛选；默认只查 reviewed）。"""
    stmt = select(VisitRecord).where(VisitRecord.project_id == project_id)
    if review_status is not None:
        stmt = stmt.where(VisitRecord.review_status == review_status)
    elif not include_drafts:
        stmt = stmt.where(VisitRecord.review_status == "reviewed")
    if visit_type is not None:
        stmt = stmt.where(VisitRecord.visit_type == visit_type)
    if card_id is not None:
        # 命中 participants_client 或 related_card_ids 中含该角色卡
        # 用 JSONB @> 数组包含：'[1,2]' @> '[1]' = true（避免 '1' 误匹配 '[11]'）
        cond = cast([card_id], JSONB)
        stmt = stmt.where(
            VisitRecord.participants_client.op("@>")(cond)
            | VisitRecord.related_card_ids.op("@>")(cond)
        )
    # 时间倒序（无日期的「一句话记录」排最后）
    stmt = stmt.order_by(VisitRecord.visit_date.desc().nullslast(), VisitRecord.id.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [await _enrich_visit(db, v) for v in rows]


async def get_visit(
    db: AsyncSession, project_id: int, visit_id: int
) -> VisitRecordOut | None:
    v = await db.get(VisitRecord, visit_id)
    if v is None or v.project_id != project_id:
        return None
    return await _enrich_visit(db, v)


async def create_visit(
    db: AsyncSession, project_id: int, payload: VisitRecordCreate, user: User
) -> VisitRecordOut:
    v = VisitRecord(
        project_id=project_id,
        visit_date=payload.visit_date,
        visit_type=payload.visit_type,
        participants_our=payload.participants_our,
        participants_client=payload.participants_client,
        location=payload.location,
        duration=payload.duration,
        summary=payload.summary,
        next_steps=payload.next_steps,
        key_takeaways=payload.key_takeaways,
        related_card_ids=payload.related_card_ids,
        review_status=payload.review_status,
        created_by=user.id,
        is_public=1 if payload.is_public else 0,
        shared_with=payload.shared_with,
        sensitivity_level=payload.sensitivity_level,
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return await _enrich_visit(db, v)


async def update_visit(
    db: AsyncSession, project_id: int, visit_id: int, payload: VisitRecordUpdate
) -> VisitRecordOut | None:
    v = await db.get(VisitRecord, visit_id)
    if v is None or v.project_id != project_id:
        return None
    if payload.visit_date is not None:
        v.visit_date = payload.visit_date
    if payload.visit_type is not None:
        v.visit_type = payload.visit_type
    if payload.participants_our is not None:
        v.participants_our = payload.participants_our
    if payload.participants_client is not None:
        v.participants_client = payload.participants_client
    if payload.location is not None:
        v.location = payload.location
    if payload.duration is not None:
        v.duration = payload.duration
    if payload.summary is not None:
        v.summary = payload.summary
    if payload.next_steps is not None:
        v.next_steps = payload.next_steps
    if payload.key_takeaways is not None:
        v.key_takeaways = payload.key_takeaways
    if payload.related_card_ids is not None:
        v.related_card_ids = payload.related_card_ids
    if payload.review_status is not None:
        v.review_status = payload.review_status
        v.reviewed_at = datetime.now(timezone.utc) if payload.review_status == "reviewed" else v.reviewed_at
    if payload.is_public is not None:
        v.is_public = 1 if payload.is_public else 0
    if payload.shared_with is not None:
        v.shared_with = payload.shared_with
    if payload.sensitivity_level is not None:
        v.sensitivity_level = payload.sensitivity_level
    await db.commit()
    await db.refresh(v)
    return await _enrich_visit(db, v)


async def delete_visit(db: AsyncSession, project_id: int, visit_id: int) -> bool:
    v = await db.get(VisitRecord, visit_id)
    if v is None or v.project_id != project_id:
        return False
    await db.delete(v)
    await db.commit()
    return True


# ─── 证据 CRUD ─────────────────────────────────────────────────


async def list_evidence(
    db: AsyncSession,
    project_id: int,
    *,
    visit_id: int | None = None,
    evidence_type: str | None = None,
    strength: str | None = None,
    source_role_id: int | None = None,
    related_hypothesis_id: int | None = None,
    review_status: str | None = None,
    include_drafts: bool = False,
) -> list[EvidenceSourceOut]:
    """列出证据（多维筛选：拜访/类型/强度/角色/假设；默认只查 reviewed）。"""
    stmt = select(EvidenceSource).where(EvidenceSource.project_id == project_id)
    if review_status is not None:
        stmt = stmt.where(EvidenceSource.review_status == review_status)
    elif not include_drafts:
        stmt = stmt.where(EvidenceSource.review_status == "reviewed")
    if visit_id is not None:
        stmt = stmt.where(EvidenceSource.visit_record_id == visit_id)
    if evidence_type is not None:
        stmt = stmt.where(EvidenceSource.evidence_type == evidence_type)
    if strength is not None:
        stmt = stmt.where(EvidenceSource.strength == strength)
    if source_role_id is not None:
        stmt = stmt.where(EvidenceSource.source_role_id == source_role_id)
    if related_hypothesis_id is not None:
        stmt = stmt.where(EvidenceSource.related_hypothesis_id == related_hypothesis_id)
    stmt = stmt.order_by(EvidenceSource.id)
    rows = (await db.execute(stmt)).scalars().all()
    return [await _enrich_evidence(db, e) for e in rows]


async def get_evidence(
    db: AsyncSession, project_id: int, evidence_id: int
) -> EvidenceSourceOut | None:
    e = await db.get(EvidenceSource, evidence_id)
    if e is None or e.project_id != project_id:
        return None
    return await _enrich_evidence(db, e)


async def _validate_evidence_links(
    db: AsyncSession, project_id: int, payload: EvidenceSourceCreate | EvidenceSourceUpdate
) -> None:
    """校验证据关联的拜访/角色卡/假设节点均属本项目。"""
    vid = getattr(payload, "visit_record_id", None)
    if vid is not None:
        v = await db.get(VisitRecord, vid)
        if v is None or v.project_id != project_id:
            raise ValueError("拜访记录不存在")
    rid = getattr(payload, "source_role_id", None)
    if rid is not None:
        c = await db.get(StakeholderCard, rid)
        if c is None or c.project_id != project_id:
            raise ValueError("角色卡不存在")
    hid = getattr(payload, "related_hypothesis_id", None)
    if hid is not None:
        h = await db.get(BusinessMapObject, hid)
        if h is None or h.project_id != project_id:
            raise ValueError("假设节点不存在")


async def create_evidence(
    db: AsyncSession, project_id: int, payload: EvidenceSourceCreate, user: User
) -> EvidenceSourceOut:
    await _validate_evidence_links(db, project_id, payload)
    e = EvidenceSource(
        project_id=project_id,
        visit_record_id=payload.visit_record_id,
        evidence_type=payload.evidence_type,
        strength=payload.strength,
        strength_note=payload.strength_note,
        content=payload.content,
        source_role_id=payload.source_role_id,
        source_role_name=payload.source_role_name,
        related_hypothesis_id=payload.related_hypothesis_id,
        related_hypothesis_name=payload.related_hypothesis_name,
        implied_from_stance=payload.implied_from_stance,
        implied_to_stance=payload.implied_to_stance,
        review_status=payload.review_status,
        created_by=user.id,
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)

    # §7.6 态度变化自动记录：角色态度信号类证据关联角色卡 + 携带立场变化 → 自动追加 stanceChangeLog
    await _maybe_trigger_stance_change(db, project_id, e)

    return await _enrich_evidence(db, e)


async def update_evidence(
    db: AsyncSession, project_id: int, evidence_id: int, payload: EvidenceSourceUpdate
) -> EvidenceSourceOut | None:
    e = await db.get(EvidenceSource, evidence_id)
    if e is None or e.project_id != project_id:
        return None
    await _validate_evidence_links(db, project_id, payload)
    if payload.visit_record_id is not None:
        e.visit_record_id = payload.visit_record_id
    if payload.evidence_type is not None:
        e.evidence_type = payload.evidence_type
    if payload.strength is not None:
        e.strength = payload.strength
    if payload.strength_note is not None:
        e.strength_note = payload.strength_note
    if payload.content is not None:
        e.content = payload.content
    if payload.source_role_id is not None:
        e.source_role_id = payload.source_role_id
    if payload.source_role_name is not None:
        e.source_role_name = payload.source_role_name
    if payload.related_hypothesis_id is not None:
        e.related_hypothesis_id = payload.related_hypothesis_id
    if payload.related_hypothesis_name is not None:
        e.related_hypothesis_name = payload.related_hypothesis_name
    if payload.implied_from_stance is not None:
        e.implied_from_stance = payload.implied_from_stance
    if payload.implied_to_stance is not None:
        e.implied_to_stance = payload.implied_to_stance
    if payload.review_status is not None:
        e.review_status = payload.review_status
        e.reviewed_at = datetime.now(timezone.utc) if payload.review_status == "reviewed" else e.reviewed_at
    await db.commit()
    await db.refresh(e)
    return await _enrich_evidence(db, e)


async def delete_evidence(
    db: AsyncSession, project_id: int, evidence_id: int
) -> bool:
    e = await db.get(EvidenceSource, evidence_id)
    if e is None or e.project_id != project_id:
        return False
    await db.delete(e)
    await db.commit()
    return True


# ─── §7.6 态度变化自动触发 ────────────────────────────────────


async def _maybe_trigger_stance_change(
    db: AsyncSession, project_id: int, e: EvidenceSource
) -> None:
    """角色态度信号类证据关联角色卡 + 携带 from/to 立场 → 自动记录态度变化。

    复用 marketing_map.record_stance_change（追加 stanceChangeLog + 联动主观层 stance）。
    仅在创建证据时触发一次（更新走手动），避免重复追加。
    """
    if e.evidence_type != "角色态度信号":
        return
    if e.source_role_id is None or not e.implied_from_stance or not e.implied_to_stance:
        return
    try:
        await mm_service.record_stance_change(
            db,
            project_id,
            e.source_role_id,
            e.implied_from_stance,
            e.implied_to_stance,
            reason=e.content,
        )
    except ValueError:
        # 角色卡被并发删除等边界：静默跳过，不阻断证据写入
        pass


# ─── §7.5 证据验证联动 ────────────────────────────────────────


async def suggest_verification_status(
    db: AsyncSession, project_id: int, hypothesis_id: int
) -> VerificationSuggestionOut:
    """按 §7.5.1 聚合同假设节点的 reviewed 证据 → 建议验证状态。

    规则（基于证据强度计数）：
    - 0 条 → 未验证
    - 强证据 ≥ 3 → 成立
    - 强证据 ≥ 1 或 中证据 ≥ 2 → 部分成立
    - 仅弱证据 → 待补充
    """
    h = await db.get(BusinessMapObject, hypothesis_id)
    if h is None or h.project_id != project_id:
        raise ValueError("假设节点不存在")

    rows = (
        await db.execute(
            select(EvidenceSource.id, EvidenceSource.strength).where(
                EvidenceSource.project_id == project_id,
                EvidenceSource.related_hypothesis_id == hypothesis_id,
                EvidenceSource.review_status == "reviewed",
            )
        )
    ).all()
    strong = sum(1 for _, s in rows if s == "强")
    medium = sum(1 for _, s in rows if s == "中")
    weak = sum(1 for _, s in rows if s == "弱")
    total = len(rows)

    if total == 0:
        suggested, reason = "未验证", "尚无关联证据"
    elif strong >= STRONG_FOR_ESTABLISHED:
        suggested, reason = "成立", f"{strong} 条强证据支持"
    elif strong >= 1 or medium >= 2:
        suggested, reason = "部分成立", f"强 {strong} / 中 {medium} 条证据支持"
    else:
        suggested, reason = "待补充", f"仅 {weak} 条弱证据，需补充更强证据"

    return VerificationSuggestionOut(
        hypothesis_id=hypothesis_id,
        hypothesis_name=h.name,
        suggested_status=suggested,
        strong_count=strong,
        medium_count=medium,
        weak_count=weak,
        total_count=total,
        evidence_ids=[eid for eid, _ in rows],
        reason=reason,
    )


async def confirm_verification(
    db: AsyncSession,
    project_id: int,
    hypothesis_id: int,
    payload: VerificationConfirmIn,
    user: User,
) -> VerificationConfirmOut:
    """人工确认验证状态（§7.5.2/§7.5.3）。

    1. 更新假设节点 verificationStatus（status 缺省时采纳建议）；
    2. 若确认为「推翻」→ 自动新增偏差池条目（current 节点，verificationStatus=推翻），
       已存在则复用不重复创建（§7.5.3 偏差池自动新增 + §7.5.4 现状从假设复制）。
    """
    suggestion = await suggest_verification_status(db, project_id, hypothesis_id)
    status = payload.status or suggestion.suggested_status

    h = await db.get(BusinessMapObject, hypothesis_id)
    h.verification_status = status

    deviation_id: int | None = None
    deviation_created = False
    if status == "推翻":
        # 已存在同假设的推翻型 current 节点则复用
        existing = (
            await db.execute(
                select(BusinessMapObject).where(
                    BusinessMapObject.project_id == project_id,
                    BusinessMapObject.linked_hypothesis_id == hypothesis_id,
                    BusinessMapObject.map_type == "current",
                    BusinessMapObject.verification_status == "推翻",
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            dev = BusinessMapObject(
                project_id=project_id,
                level=h.level,
                name=f"{h.name}（偏差）",
                map_type="current",
                verification_status="推翻",
                linked_hypothesis_id=hypothesis_id,
                payload={
                    "deviationNote": "假设与现状出现偏差，由证据验证联动自动生成",
                    "sourceEvidenceIds": suggestion.evidence_ids,
                },
                review_status="reviewed",
                created_by=user.id,
            )
            db.add(dev)
            await db.flush()
            deviation_id = dev.id
            deviation_created = True
        else:
            deviation_id = existing.id

    await db.commit()

    msg = "验证状态已更新"
    if deviation_created:
        msg = "验证状态已更新，偏差池已自动新增条目"
    elif status == "推翻":
        msg = "验证状态已更新（偏差池条目已存在，未重复创建）"

    return VerificationConfirmOut(
        hypothesis_id=hypothesis_id,
        verification_status=status,
        deviation_created=deviation_created,
        deviation_object_id=deviation_id,
        message=msg,
    )
