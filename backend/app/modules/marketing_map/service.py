"""营销地图业务服务层（M2.2）。

职责：
- StakeholderCard CRUD（按 department/role_type/stance 筛选；主观层综合评分自动计算，§5.2）
- StakeholderRelation CRUD + 关系网络图数据（节点=角色卡，边=关系）
- TalkScript CRUD（按 role_type/scenario 筛选）
- KnowledgeBase CRUD（按 category 筛选）
- 态度变化记录（§7.6：追加 stanceChangeLog；M2.3 证据联动会调用本服务）

权限：路由层 require_project_member 保证项目隔离；本层只做业务。
默认列表只查 reviewed（§7.3）。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    KnowledgeBase,
    PersonDisambiguationCandidate,
    ProcurementTimeline,
    StakeholderCard,
    StakeholderRelation,
    TalkScript,
    User,
)
from app.schemas.marketing_map import (
    DisambiguationCandidateCard,
    DisambiguationCandidateOut,
    DisambiguationResolveIn,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
    ProcurementStageIn,
    ProcurementStageOut,
    ProcurementTimelineInput,
    ProcurementTimelineOut,
    StakeholderCardCreate,
    StakeholderCardOut,
    StakeholderCardUpdate,
    StakeholderGraphEdge,
    StakeholderGraphNode,
    StakeholderGraphOut,
    StakeholderRelationCreate,
    StakeholderRelationOut,
    StanceChangeOut,
    TalkScriptCreate,
    TalkScriptOut,
    TalkScriptUpdate,
    iso,
)


# ─── 工具 ──────────────────────────────────────────────────────


async def _user_name(db: AsyncSession, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    u = await db.get(User, user_id)
    return (u.display_name or u.username) if u else None


def _compute_subjective(layer: dict | None) -> dict | None:
    """按 §5.2 公式计算主观层 compositeScore 与 gradeLevel，写回 layer。"""
    if not isinstance(layer, dict):
        return layer
    out = dict(layer)
    try:
        e = float(out.get("engagement") or 0)
        i = float(out.get("influence") or 0)
        s = float(out.get("support") or 0)
    except (TypeError, ValueError):
        return out
    composite = round(e * 0.3 + i * 0.4 + s * 0.3)
    out["compositeScore"] = composite
    if composite >= 8:
        grade = "Champion"
    elif composite >= 5:
        grade = "倾向我方"
    elif composite >= 3:
        grade = "中立"
    else:
        grade = "反对"
    out["gradeLevel"] = grade
    return out


def _card_to_out(card: StakeholderCard, created_by_name, reviewed_by_name) -> StakeholderCardOut:
    return StakeholderCardOut(
        id=card.id,
        project_id=card.project_id,
        name=card.name,
        position=card.position,
        department=card.department,
        reports_to=card.reports_to,
        contact_info=card.contact_info,
        role_type=card.role_type,
        decision_power=card.decision_power,
        objective_layer=card.objective_layer,
        subjective_layer=card.subjective_layer,
        behaviors=card.behaviors,
        stance_change_log=card.stance_change_log,
        review_status=card.review_status,
        reviewed_by=card.reviewed_by,
        reviewed_by_name=reviewed_by_name,
        reviewed_at=iso(card.reviewed_at),
        created_by=card.created_by,
        created_by_name=created_by_name,
        is_public=bool(card.is_public),
        shared_with=card.shared_with,
        sensitivity_level=card.sensitivity_level,
        source_session_id=card.source_session_id,
        created_at=iso(card.created_at),
        updated_at=iso(card.updated_at),
    )


async def _enrich_card(db, card: StakeholderCard) -> StakeholderCardOut:
    return _card_to_out(
        card,
        await _user_name(db, card.created_by),
        await _user_name(db, card.reviewed_by),
    )


# ─── 角色卡 CRUD ───────────────────────────────────────────────


async def list_cards(
    db: AsyncSession,
    project_id: int,
    *,
    department: str | None = None,
    role_type: str | None = None,
    stance: str | None = None,
    review_status: str | None = None,
    include_drafts: bool = False,
) -> list[StakeholderCardOut]:
    stmt = select(StakeholderCard).where(StakeholderCard.project_id == project_id)
    if review_status is not None:
        stmt = stmt.where(StakeholderCard.review_status == review_status)
    elif not include_drafts:
        stmt = stmt.where(StakeholderCard.review_status == "reviewed")
    if department is not None:
        stmt = stmt.where(StakeholderCard.department == department)
    if role_type is not None:
        stmt = stmt.where(StakeholderCard.role_type == role_type)
    if stance is not None:
        # stance 存在 subjective_layer JSONB 内
        stmt = stmt.where(StakeholderCard.subjective_layer["stance"].astext == stance)
    stmt = stmt.order_by(StakeholderCard.id)
    cards = (await db.execute(stmt)).scalars().all()
    return [await _enrich_card(db, c) for c in cards]


async def get_card(db, project_id, card_id) -> StakeholderCardOut | None:
    c = await db.get(StakeholderCard, card_id)
    if c is None or c.project_id != project_id:
        return None
    return await _enrich_card(db, c)


async def create_card(
    db, project_id, payload: StakeholderCardCreate, user: User,
    *, source_session_id: str | None = None,
) -> StakeholderCardOut:
    card = StakeholderCard(
        project_id=project_id,
        name=payload.name,
        position=payload.position,
        department=payload.department,
        reports_to=payload.reports_to,
        contact_info=payload.contact_info,
        role_type=payload.role_type,
        decision_power=payload.decision_power,
        objective_layer=payload.objective_layer,
        subjective_layer=_compute_subjective(payload.subjective_layer),
        behaviors=payload.behaviors,
        stance_change_log=payload.stance_change_log,
        review_status=payload.review_status,
        created_by=user.id,
        is_public=1 if payload.is_public else 0,
        shared_with=payload.shared_with,
        sensitivity_level=payload.sensitivity_level,
        source_session_id=source_session_id,
    )
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return await _enrich_card(db, card)


async def update_card(
    db, project_id, card_id, payload: StakeholderCardUpdate
) -> StakeholderCardOut | None:
    c = await db.get(StakeholderCard, card_id)
    if c is None or c.project_id != project_id:
        return None
    if payload.name is not None:
        c.name = payload.name
    if payload.position is not None:
        c.position = payload.position
    if payload.department is not None:
        c.department = payload.department
    if payload.reports_to is not None:
        c.reports_to = payload.reports_to
    if payload.contact_info is not None:
        c.contact_info = payload.contact_info
    if payload.role_type is not None:
        c.role_type = payload.role_type
    if payload.decision_power is not None:
        c.decision_power = payload.decision_power
    if payload.objective_layer is not None:
        c.objective_layer = payload.objective_layer
    if payload.subjective_layer is not None:
        c.subjective_layer = _compute_subjective(payload.subjective_layer)
    if payload.behaviors is not None:
        c.behaviors = payload.behaviors
    if payload.stance_change_log is not None:
        c.stance_change_log = payload.stance_change_log
    if payload.review_status is not None:
        c.review_status = payload.review_status
        c.reviewed_at = datetime.now(timezone.utc) if payload.review_status == "reviewed" else c.reviewed_at
    if payload.is_public is not None:
        c.is_public = 1 if payload.is_public else 0
    if payload.shared_with is not None:
        c.shared_with = payload.shared_with
    if payload.sensitivity_level is not None:
        c.sensitivity_level = payload.sensitivity_level
    await db.commit()
    await db.refresh(c)
    return await _enrich_card(db, c)


async def delete_card(db, project_id, card_id) -> bool:
    c = await db.get(StakeholderCard, card_id)
    if c is None or c.project_id != project_id:
        return False
    await db.delete(c)
    await db.commit()
    return True


# ─── 态度变化（§7.6） ─────────────────────────────────────────


async def record_stance_change(
    db: AsyncSession,
    project_id: int,
    card_id: int,
    from_stance: str,
    to_stance: str,
    reason: str,
) -> StanceChangeOut:
    """向角色卡追加一条 stanceChangeLog 记录（§7.6）。

    M2.3 证据关联角色卡时会调用本函数实现「自动记录」；此处亦供手动追加。
    """
    c = await db.get(StakeholderCard, card_id)
    if c is None or c.project_id != project_id:
        raise ValueError("角色卡不存在")
    log = list(c.stance_change_log or [])
    entry = {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "from": from_stance,
        "to": to_stance,
        "reason": reason,
    }
    log.append(entry)
    c.stance_change_log = log
    # 联动更新主观层当前 stance
    if isinstance(c.subjective_layer, dict):
        sl = dict(c.subjective_layer)
        sl["stance"] = to_stance
        c.subjective_layer = sl
    await db.commit()
    return StanceChangeOut(
        date=entry["date"], from_stance=from_stance, to_stance=to_stance, reason=reason
    )


# ─── 角色关系 ──────────────────────────────────────────────────


async def _relation_to_out(
    db: AsyncSession, r: StakeholderRelation
) -> StakeholderRelationOut:
    from_card = await db.get(StakeholderCard, r.from_card_id)
    to_card = await db.get(StakeholderCard, r.to_card_id)
    return StakeholderRelationOut(
        id=r.id,
        project_id=r.project_id,
        from_card_id=r.from_card_id,
        from_card_name=from_card.name if from_card else None,
        to_card_id=r.to_card_id,
        to_card_name=to_card.name if to_card else None,
        relation_type=r.relation_type,
        description=r.description,
        created_by=r.created_by,
        created_at=iso(r.created_at),
    )


async def list_relations(db, project_id) -> list[StakeholderRelationOut]:
    rows = (
        await db.execute(
            select(StakeholderRelation)
            .where(StakeholderRelation.project_id == project_id)
            .order_by(StakeholderRelation.id)
        )
    ).scalars().all()
    return [await _relation_to_out(db, r) for r in rows]


async def create_relation(
    db, project_id, payload: StakeholderRelationCreate, user: User
) -> StakeholderRelationOut:
    if payload.from_card_id == payload.to_card_id:
        raise ValueError("不能建立自环关系")
    for cid in (payload.from_card_id, payload.to_card_id):
        c = await db.get(StakeholderCard, cid)
        if c is None or c.project_id != project_id:
            raise ValueError("角色卡不存在")
    r = StakeholderRelation(
        project_id=project_id,
        from_card_id=payload.from_card_id,
        to_card_id=payload.to_card_id,
        relation_type=payload.relation_type,
        description=payload.description,
        created_by=user.id,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return await _relation_to_out(db, r)


async def delete_relation(db, project_id, relation_id) -> bool:
    r = await db.get(StakeholderRelation, relation_id)
    if r is None or r.project_id != project_id:
        return False
    await db.delete(r)
    await db.commit()
    return True


async def get_relation_graph(db, project_id) -> StakeholderGraphOut:
    """关系网络图数据：节点=项目 reviewed 角色卡，边=全部关系。"""
    cards = (
        await db.execute(
            select(StakeholderCard).where(
                StakeholderCard.project_id == project_id,
                StakeholderCard.review_status == "reviewed",
            )
        )
    ).scalars().all()
    rels = (
        await db.execute(
            select(StakeholderRelation).where(StakeholderRelation.project_id == project_id)
        )
    ).scalars().all()
    return StakeholderGraphOut(
        nodes=[
            StakeholderGraphNode(
                id=c.id, name=c.name, role_type=c.role_type, department=c.department
            )
            for c in cards
        ],
        edges=[
            StakeholderGraphEdge(
                id=r.id,
                source=r.from_card_id,
                target=r.to_card_id,
                relation_type=r.relation_type,
                description=r.description,
            )
            for r in rels
        ],
    )


# ─── 话术 ──────────────────────────────────────────────────────


async def _script_to_out(db, s: TalkScript) -> TalkScriptOut:
    card = await db.get(StakeholderCard, s.stakeholder_card_id) if s.stakeholder_card_id else None
    return TalkScriptOut(
        id=s.id,
        project_id=s.project_id,
        stakeholder_card_id=s.stakeholder_card_id,
        stakeholder_card_name=card.name if card else None,
        role_type=s.role_type,
        scenario=s.scenario,
        content=s.content,
        source_customer_quote=s.source_customer_quote,
        is_template=bool(s.is_template),
        created_by=s.created_by,
        created_at=iso(s.created_at),
        updated_at=iso(s.updated_at),
    )


async def list_scripts(
    db, project_id, *, role_type=None, scenario=None
) -> list[TalkScriptOut]:
    stmt = select(TalkScript).where(TalkScript.project_id == project_id)
    if role_type is not None:
        stmt = stmt.where(TalkScript.role_type == role_type)
    if scenario is not None:
        stmt = stmt.where(TalkScript.scenario == scenario)
    stmt = stmt.order_by(TalkScript.id)
    rows = (await db.execute(stmt)).scalars().all()
    return [await _script_to_out(db, s) for s in rows]


async def get_script(db, project_id, script_id) -> TalkScriptOut | None:
    s = await db.get(TalkScript, script_id)
    if s is None or s.project_id != project_id:
        return None
    return await _script_to_out(db, s)


async def create_script(
    db, project_id, payload: TalkScriptCreate, user: User
) -> TalkScriptOut:
    if payload.stakeholder_card_id is not None:
        c = await db.get(StakeholderCard, payload.stakeholder_card_id)
        if c is None or c.project_id != project_id:
            raise ValueError("角色卡不存在")
    s = TalkScript(
        project_id=project_id,
        stakeholder_card_id=payload.stakeholder_card_id,
        role_type=payload.role_type,
        scenario=payload.scenario,
        content=payload.content,
        source_customer_quote=payload.source_customer_quote,
        is_template=1 if payload.is_template else 0,
        created_by=user.id,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return await _script_to_out(db, s)


async def update_script(db, project_id, script_id, payload: TalkScriptUpdate) -> TalkScriptOut | None:
    s = await db.get(TalkScript, script_id)
    if s is None or s.project_id != project_id:
        return None
    if payload.stakeholder_card_id is not None:
        s.stakeholder_card_id = payload.stakeholder_card_id
    if payload.role_type is not None:
        s.role_type = payload.role_type
    if payload.scenario is not None:
        s.scenario = payload.scenario
    if payload.content is not None:
        s.content = payload.content
    if payload.source_customer_quote is not None:
        s.source_customer_quote = payload.source_customer_quote
    if payload.is_template is not None:
        s.is_template = 1 if payload.is_template else 0
    await db.commit()
    await db.refresh(s)
    return await _script_to_out(db, s)


async def delete_script(db, project_id, script_id) -> bool:
    s = await db.get(TalkScript, script_id)
    if s is None or s.project_id != project_id:
        return False
    await db.delete(s)
    await db.commit()
    return True


# ─── 知识库 ────────────────────────────────────────────────────


def _kb_to_out(kb: KnowledgeBase) -> KnowledgeBaseOut:
    return KnowledgeBaseOut(
        id=kb.id,
        project_id=kb.project_id,
        category=kb.category,
        title=kb.title,
        content=kb.content,
        created_by=kb.created_by,
        created_at=iso(kb.created_at),
        updated_at=iso(kb.updated_at),
    )


async def list_kb(db, project_id, *, category=None) -> list[KnowledgeBaseOut]:
    stmt = select(KnowledgeBase).where(KnowledgeBase.project_id == project_id)
    if category is not None:
        stmt = stmt.where(KnowledgeBase.category == category)
    stmt = stmt.order_by(KnowledgeBase.id)
    rows = (await db.execute(stmt)).scalars().all()
    return [_kb_to_out(k) for k in rows]


async def get_kb(db, project_id, kb_id) -> KnowledgeBaseOut | None:
    k = await db.get(KnowledgeBase, kb_id)
    if k is None or k.project_id != project_id:
        return None
    return _kb_to_out(k)


async def create_kb(
    db, project_id, payload: KnowledgeBaseCreate, user: User
) -> KnowledgeBaseOut:
    k = KnowledgeBase(
        project_id=project_id,
        category=payload.category,
        title=payload.title,
        content=payload.content,
        created_by=user.id,
    )
    db.add(k)
    await db.commit()
    await db.refresh(k)
    return _kb_to_out(k)


async def update_kb(
    db, project_id, kb_id, payload: KnowledgeBaseUpdate
) -> KnowledgeBaseOut | None:
    k = await db.get(KnowledgeBase, kb_id)
    if k is None or k.project_id != project_id:
        return None
    if payload.category is not None:
        k.category = payload.category
    if payload.title is not None:
        k.title = payload.title
    if payload.content is not None:
        k.content = payload.content
    await db.commit()
    await db.refresh(k)
    return _kb_to_out(k)


async def delete_kb(db, project_id, kb_id) -> bool:
    k = await db.get(KnowledgeBase, kb_id)
    if k is None or k.project_id != project_id:
        return False
    await db.delete(k)
    await db.commit()
    return True


# ─── 采购流程时间线（M4.2.5）───────────────────────────────────

#: 五阶段通用模板（需求识别→方案评估→供应商筛选→商务谈判→合同签署）
PROCUREMENT_STAGE_TEMPLATE: list[tuple[str, str]] = [
    ("need_identification", "需求识别"),
    ("solution_evaluation", "方案评估"),
    ("vendor_screening", "供应商筛选"),
    ("commercial_negotiation", "商务谈判"),
    ("contract_signing", "合同签署"),
]


def _default_procurement_stages() -> list[dict]:
    """生成五阶段默认模板（全部未开始、日期/说明/关键角色为空）。"""
    return [
        {
            "key": key,
            "name": name,
            "status": "not_started",
            "startDate": None,
            "endDate": None,
            "note": None,
            "ownerCardId": None,
        }
        for key, name in PROCUREMENT_STAGE_TEMPLATE
    ]


def _proc_to_out(
    pt: ProcurementTimeline, created_by_name: str | None
) -> ProcurementTimelineOut:
    """落库行 → 输出；stages 缺失时回退五阶段默认模板。"""
    stages = pt.stages if pt.stages else _default_procurement_stages()
    return ProcurementTimelineOut(
        id=pt.id,
        project_id=pt.project_id,
        stages=[ProcurementStageOut(**s) for s in stages],
        created_by=pt.created_by,
        created_by_name=created_by_name,
        created_at=iso(pt.created_at),
        updated_at=iso(pt.updated_at),
    )


async def get_procurement_timeline(
    db: AsyncSession, project_id: int
) -> ProcurementTimelineOut | None:
    """读取项目采购时间线（未建则返回 None，由前端用默认模板渲染）。"""
    pt = (
        await db.execute(
            select(ProcurementTimeline).where(
                ProcurementTimeline.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if pt is None:
        return None
    return _proc_to_out(pt, await _user_name(db, pt.created_by))


async def upsert_procurement_timeline(
    db: AsyncSession, project_id: int, payload: ProcurementTimelineInput, user: User
) -> ProcurementTimelineOut:
    """创建或更新采购时间线（一个项目一份，整体替换 stages）。"""
    pt = (
        await db.execute(
            select(ProcurementTimeline).where(
                ProcurementTimeline.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    stages = [s.model_dump() for s in payload.stages]
    if pt is None:
        pt = ProcurementTimeline(
            project_id=project_id, stages=stages, created_by=user.id
        )
        db.add(pt)
    else:
        pt.stages = stages
    await db.commit()
    await db.refresh(pt)
    return _proc_to_out(pt, await _user_name(db, pt.created_by))


# ─── 角色去重候选（M5.5.1 person_disambiguation，§7.1）─────────
#
# AI 新建角色卡草稿时检测项目内既有卡是否疑似同人，命中则生成去重候选供用户确认。
# 相似度评分（单一真源，name 为主信号）：
#   完全同名 1.0 / 姓名包含 0.6（双方长度均 ≥2）；同部门 +0.2 / 同角色类型 +0.2；上限 1.0。
#   阈值 ≥0.6 才生成候选——避免「姓名不同仅部门角色相同」的误报（此类仅 0.4）。

_DISAMBIGUATION_THRESHOLD = 0.6


def _draft_snapshot(card: StakeholderCard) -> dict:
    """抓取草稿卡关键展示字段快照（写入候选记录，供前端展示）。"""
    return {
        "name": card.name,
        "position": card.position,
        "department": card.department,
        "reports_to": card.reports_to,
        "contact_info": card.contact_info,
        "role_type": card.role_type,
        "decision_power": card.decision_power,
    }


def _name_score(a: str | None, b: str | None) -> float:
    """姓名相似度：完全相等 1.0 / 包含关系 0.6（要求双方均 ≥2 字）/ 否则 0。"""
    na = (a or "").strip()
    nb = (b or "").strip()
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if len(na) >= 2 and len(nb) >= 2 and (na in nb or nb in na):
        return 0.6
    return 0.0


def _similarity(draft: StakeholderCard, existing: StakeholderCard) -> tuple[float, list[str]]:
    """计算新草稿与既有卡的相似度评分与命中原因列表。"""
    reasons: list[str] = []
    score = 0.0
    ns = _name_score(draft.name, existing.name)
    if ns >= 1.0:
        score += 1.0
        reasons.append("完全同名")
    elif ns >= 0.6:
        score += 0.6
        reasons.append("姓名相似")
    if draft.department and existing.department and draft.department.strip() == existing.department.strip():
        score += 0.2
        reasons.append("同部门")
    if draft.role_type and existing.role_type and draft.role_type == existing.role_type:
        score += 0.2
        reasons.append("同角色类型")
    return min(score, 1.0), reasons


def _merge_draft_into_target(draft: StakeholderCard, target: StakeholderCard) -> None:
    """将草稿卡字段合并进既有目标卡（就地修改 target）。

    语义：目标卡为主、草稿填充缺失——目标已有值/键优先保留，草稿补齐空缺。
    - 标量字段：目标为空则用草稿值。
    - objective_layer / subjective_layer：浅合并，目标键优先；主观层重算 compositeScore/gradeLevel。
    - behaviors：按 observation 文本去重后追加。
    - stance_change_log：拼接（草稿在后）。
    """
    for f in ("position", "department", "reports_to", "contact_info", "role_type", "decision_power"):
        if not getattr(target, f) and getattr(draft, f):
            setattr(target, f, getattr(draft, f))

    if isinstance(draft.objective_layer, dict):
        merged = dict(target.objective_layer or {})
        for k, v in draft.objective_layer.items():
            merged.setdefault(k, v)
        target.objective_layer = merged

    if isinstance(draft.subjective_layer, dict):
        merged = dict(target.subjective_layer or {})
        for k, v in draft.subjective_layer.items():
            merged.setdefault(k, v)
        target.subjective_layer = _compute_subjective(merged)
    elif isinstance(target.subjective_layer, dict):
        target.subjective_layer = _compute_subjective(target.subjective_layer)

    if draft.behaviors:
        existing = list(target.behaviors or [])
        seen_obs = {
            (b.get("observation") if isinstance(b, dict) else None) for b in existing
        }
        for b in draft.behaviors:
            obs = b.get("observation") if isinstance(b, dict) else None
            if obs not in seen_obs:
                existing.append(b)
                seen_obs.add(obs)
        target.behaviors = existing

    if draft.stance_change_log:
        target.stance_change_log = list(target.stance_change_log or []) + list(draft.stance_change_log)


def _disambiguation_to_out(c: PersonDisambiguationCandidate) -> DisambiguationCandidateOut:
    """落库行 → 输出；candidates 列表逐项构造为 DisambiguationCandidateCard。"""
    cards: list[DisambiguationCandidateCard] = []
    for entry in (c.candidates or []):
        if not isinstance(entry, dict):
            continue
        cards.append(DisambiguationCandidateCard(
            id=entry.get("id"),
            name=entry.get("name") or "",
            position=entry.get("position"),
            department=entry.get("department"),
            role_type=entry.get("role_type"),
            score=entry.get("score") or 0.0,
            reasons=entry.get("reasons") or [],
        ))
    return DisambiguationCandidateOut(
        id=c.id,
        project_id=c.project_id,
        draft_card_id=c.draft_card_id,
        new_draft_snapshot=c.new_draft_snapshot or {},
        candidates=cards,
        status=c.status,
        decision=c.decision,
        merge_into_card_id=c.merge_into_card_id,
        resolved_by=c.resolved_by,
        created_at=iso(c.created_at),
        resolved_at=iso(c.resolved_at),
    )


async def detect_and_create_disambiguation(
    db: AsyncSession, project_id: int, draft_card_id: int
) -> bool:
    """新建草稿卡后检测项目内既有卡是否疑似同人；命中则创建去重候选。

    比对项目内全部既有卡（reviewed + draft，排除自身），相似度 ≥ 阈值者入选候选列表
    （按评分降序）。无命中则不落库、返回 False（避免噪声）。返回是否生成候选。
    """
    draft = await db.get(StakeholderCard, draft_card_id)
    if draft is None or draft.project_id != project_id:
        return False

    rows = (
        await db.execute(
            select(StakeholderCard).where(
                StakeholderCard.project_id == project_id,
                StakeholderCard.id != draft_card_id,
            )
        )
    ).scalars().all()

    scored: list[tuple[StakeholderCard, float, list[str]]] = []
    for ex in rows:
        score, reasons = _similarity(draft, ex)
        if score >= _DISAMBIGUATION_THRESHOLD:
            scored.append((ex, score, reasons))
    if not scored:
        return False
    scored.sort(key=lambda t: t[1], reverse=True)

    candidate = PersonDisambiguationCandidate(
        project_id=project_id,
        draft_card_id=draft_card_id,
        new_draft_snapshot=_draft_snapshot(draft),
        candidates=[
            {
                "id": ex.id,
                "name": ex.name,
                "position": ex.position,
                "department": ex.department,
                "role_type": ex.role_type,
                "score": round(score, 2),
                "reasons": reasons,
            }
            for ex, score, reasons in scored
        ],
        status="pending",
    )
    db.add(candidate)
    await db.commit()
    return True


async def list_disambiguation_candidates(
    db: AsyncSession, project_id: int, *, status: str | None = "pending"
) -> list[DisambiguationCandidateOut]:
    """列出项目下的去重候选（默认仅 pending）。"""
    stmt = select(PersonDisambiguationCandidate).where(
        PersonDisambiguationCandidate.project_id == project_id
    )
    if status is not None:
        stmt = stmt.where(PersonDisambiguationCandidate.status == status)
    stmt = stmt.order_by(PersonDisambiguationCandidate.id.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [_disambiguation_to_out(c) for c in rows]


async def resolve_disambiguation(
    db: AsyncSession,
    project_id: int,
    candidate_id: int,
    payload: DisambiguationResolveIn,
    user: User,
) -> DisambiguationCandidateOut:
    """用户确认去重候选（§7.1 角色去重）。

    - decision="new"：草稿确认为新人 → promote draft→reviewed（与统一采纳同语义，自确认发布）。
      若草稿已被采纳/删除则幂等（仅标记候选 resolved）。
    - decision="merge"：草稿实为既有卡同人 → 合并草稿字段进目标卡并删除草稿。
      merge_into_card_id 必须在候选列表内，且草稿仍为 draft 态。
    """
    c = await db.get(PersonDisambiguationCandidate, candidate_id)
    if c is None or c.project_id != project_id:
        raise LookupError("去重候选不存在")
    if c.status != "pending":
        raise ValueError(f"该候选当前状态为 {c.status}，已处理")

    now = datetime.now(timezone.utc)
    valid_ids = {
        entry.get("id") for entry in (c.candidates or []) if isinstance(entry, dict)
    }

    if payload.decision == "merge":
        if payload.merge_into_card_id is None:
            raise ValueError("合并决策需指定目标角色卡 merge_into_card_id")
        if payload.merge_into_card_id not in valid_ids:
            raise ValueError("目标角色卡不在去重候选列表中")
        draft = await db.get(StakeholderCard, c.draft_card_id) if c.draft_card_id else None
        if draft is None or draft.review_status != "draft":
            raise ValueError("草稿卡不存在或已处理，无法合并")
        target = await db.get(StakeholderCard, payload.merge_into_card_id)
        if target is None or target.project_id != project_id:
            raise ValueError("目标角色卡不存在")
        _merge_draft_into_target(draft, target)
        await db.delete(draft)
        c.merge_into_card_id = payload.merge_into_card_id
    else:  # new
        draft = await db.get(StakeholderCard, c.draft_card_id) if c.draft_card_id else None
        if draft is not None and draft.review_status == "draft":
            draft.review_status = "reviewed"
            draft.reviewed_by = user.id
            draft.reviewed_at = now

    c.status = "resolved"
    c.decision = payload.decision
    c.resolved_by = user.id
    c.resolved_at = now
    await db.commit()
    await db.refresh(c)
    return _disambiguation_to_out(c)
