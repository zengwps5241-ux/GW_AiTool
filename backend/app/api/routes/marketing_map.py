"""营销地图 API（M2.2）。

挂在 /api/projects/{project_id} 下，受 require_project_member 保护（项目内全透明）：
- /stakeholder-cards 角色卡 CRUD + 态度变化
- /stakeholder-relations 角色关系 CRUD + 关系网络图
- /talk-scripts 话术 CRUD
- /knowledge-base 知识库 CRUD
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_deps import require_project_member
from app.db.session import get_db
from app.models import Project, User
from app.modules.marketing_map import service as mm_service
from app.schemas.marketing_map import (
    DisambiguationCandidateOut,
    DisambiguationResolveIn,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
    ProcurementTimelineInput,
    ProcurementTimelineOut,
    StakeholderCardCreate,
    StakeholderCardOut,
    StakeholderCardUpdate,
    StakeholderGraphOut,
    StakeholderRelationCreate,
    StakeholderRelationOut,
    StanceChangeIn,
    StanceChangeOut,
    TalkScriptCreate,
    TalkScriptOut,
    TalkScriptUpdate,
)

router = APIRouter(prefix="/api/projects/{project_id}")


# ─── 角色卡 ────────────────────────────────────────────────────


@router.get("/stakeholder-cards", response_model=list[StakeholderCardOut])
async def list_cards(
    project_id: int,
    department: str | None = Query(None),
    role_type: str | None = Query(None),
    stance: str | None = Query(None),
    review_status: str | None = Query(None),
    include_drafts: bool = Query(False),
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> list[StakeholderCardOut]:
    return await mm_service.list_cards(
        db, project_id,
        department=department, role_type=role_type, stance=stance,
        review_status=review_status, include_drafts=include_drafts,
    )


@router.post("/stakeholder-cards", response_model=StakeholderCardOut, status_code=status.HTTP_201_CREATED)
async def create_card(
    project_id: int,
    payload: StakeholderCardCreate,
    pu: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> StakeholderCardOut:
    _, user = pu
    return await mm_service.create_card(db, project_id, payload, user)


@router.get("/stakeholder-cards/{card_id}", response_model=StakeholderCardOut)
async def get_card(
    project_id: int,
    card_id: int,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> StakeholderCardOut:
    out = await mm_service.get_card(db, project_id, card_id)
    if out is None:
        raise HTTPException(status_code=404, detail="角色卡不存在")
    return out


@router.put("/stakeholder-cards/{card_id}", response_model=StakeholderCardOut)
async def update_card(
    project_id: int,
    card_id: int,
    payload: StakeholderCardUpdate,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> StakeholderCardOut:
    out = await mm_service.update_card(db, project_id, card_id, payload)
    if out is None:
        raise HTTPException(status_code=404, detail="角色卡不存在")
    return out


@router.delete("/stakeholder-cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(
    project_id: int,
    card_id: int,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not await mm_service.delete_card(db, project_id, card_id):
        raise HTTPException(status_code=404, detail="角色卡不存在")


@router.post(
    "/stakeholder-cards/{card_id}/stance-changes",
    response_model=StanceChangeOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_stance_change(
    project_id: int,
    card_id: int,
    payload: StanceChangeIn,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> StanceChangeOut:
    """手动追加态度变化记录（§7.6；M2.3 证据联动会复用同一服务函数）。"""
    try:
        return await mm_service.record_stance_change(
            db, project_id, card_id, payload.from_stance, payload.to_stance, payload.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ─── 角色关系 ──────────────────────────────────────────────────


@router.get("/stakeholder-relations", response_model=list[StakeholderRelationOut])
async def list_relations(
    project_id: int,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> list[StakeholderRelationOut]:
    return await mm_service.list_relations(db, project_id)


@router.post(
    "/stakeholder-relations",
    response_model=StakeholderRelationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_relation(
    project_id: int,
    payload: StakeholderRelationCreate,
    pu: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> StakeholderRelationOut:
    try:
        _, user = pu
        return await mm_service.create_relation(db, project_id, payload, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete(
    "/stakeholder-relations/{relation_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_relation(
    project_id: int,
    relation_id: int,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not await mm_service.delete_relation(db, project_id, relation_id):
        raise HTTPException(status_code=404, detail="关系不存在")


@router.get("/stakeholder-relations/graph", response_model=StakeholderGraphOut)
async def relation_graph(
    project_id: int,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> StakeholderGraphOut:
    """关系网络图数据（节点=角色卡，边=关系，§2.4 / §5.2）。"""
    return await mm_service.get_relation_graph(db, project_id)


# ─── 话术 ──────────────────────────────────────────────────────


@router.get("/talk-scripts", response_model=list[TalkScriptOut])
async def list_scripts(
    project_id: int,
    role_type: str | None = Query(None),
    scenario: str | None = Query(None),
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> list[TalkScriptOut]:
    return await mm_service.list_scripts(db, project_id, role_type=role_type, scenario=scenario)


@router.post("/talk-scripts", response_model=TalkScriptOut, status_code=status.HTTP_201_CREATED)
async def create_script(
    project_id: int,
    payload: TalkScriptCreate,
    pu: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> TalkScriptOut:
    try:
        _, user = pu
        return await mm_service.create_script(db, project_id, payload, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/talk-scripts/{script_id}", response_model=TalkScriptOut)
async def get_script(
    project_id: int, script_id: int, _=Depends(require_project_member), db: AsyncSession = Depends(get_db)
) -> TalkScriptOut:
    out = await mm_service.get_script(db, project_id, script_id)
    if out is None:
        raise HTTPException(status_code=404, detail="话术不存在")
    return out


@router.put("/talk-scripts/{script_id}", response_model=TalkScriptOut)
async def update_script(
    project_id: int,
    script_id: int,
    payload: TalkScriptUpdate,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> TalkScriptOut:
    out = await mm_service.update_script(db, project_id, script_id, payload)
    if out is None:
        raise HTTPException(status_code=404, detail="话术不存在")
    return out


@router.delete("/talk-scripts/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_script(
    project_id: int, script_id: int, _=Depends(require_project_member), db: AsyncSession = Depends(get_db)
) -> None:
    if not await mm_service.delete_script(db, project_id, script_id):
        raise HTTPException(status_code=404, detail="话术不存在")


# ─── 知识库 ────────────────────────────────────────────────────


@router.get("/knowledge-base", response_model=list[KnowledgeBaseOut])
async def list_kb(
    project_id: int,
    category: str | None = Query(None),
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeBaseOut]:
    return await mm_service.list_kb(db, project_id, category=category)


@router.post("/knowledge-base", response_model=KnowledgeBaseOut, status_code=status.HTTP_201_CREATED)
async def create_kb(
    project_id: int,
    payload: KnowledgeBaseCreate,
    pu: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeBaseOut:
    _, user = pu
    return await mm_service.create_kb(db, project_id, payload, user)


@router.get("/knowledge-base/{kb_id}", response_model=KnowledgeBaseOut)
async def get_kb(
    project_id: int, kb_id: int, _=Depends(require_project_member), db: AsyncSession = Depends(get_db)
) -> KnowledgeBaseOut:
    out = await mm_service.get_kb(db, project_id, kb_id)
    if out is None:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return out


@router.put("/knowledge-base/{kb_id}", response_model=KnowledgeBaseOut)
async def update_kb(
    project_id: int,
    kb_id: int,
    payload: KnowledgeBaseUpdate,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeBaseOut:
    out = await mm_service.update_kb(db, project_id, kb_id, payload)
    if out is None:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return out


@router.delete("/knowledge-base/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb(
    project_id: int, kb_id: int, _=Depends(require_project_member), db: AsyncSession = Depends(get_db)
) -> None:
    if not await mm_service.delete_kb(db, project_id, kb_id):
        raise HTTPException(status_code=404, detail="知识条目不存在")


# ─── 采购流程时间线（M4.2.5）───────────────────────────────────


@router.get("/procurement-timeline", response_model=ProcurementTimelineOut | None)
async def get_procurement_timeline(
    project_id: int,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> ProcurementTimelineOut | None:
    """读取项目采购时间线（五阶段通用模板；未建返回 None，前端用默认模板渲染）。"""
    return await mm_service.get_procurement_timeline(db, project_id)


@router.put("/procurement-timeline", response_model=ProcurementTimelineOut)
async def upsert_procurement_timeline(
    project_id: int,
    payload: ProcurementTimelineInput,
    pu: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> ProcurementTimelineOut:
    """创建或更新采购时间线（一个项目一份，整体替换五阶段）。"""
    _, user = pu
    return await mm_service.upsert_procurement_timeline(db, project_id, payload, user)


# ─── 角色去重候选（M5.5.1 person_disambiguation，§7.1）─────────


@router.get(
    "/disambiguation-candidates", response_model=list[DisambiguationCandidateOut]
)
async def list_disambiguation_candidates(
    project_id: int,
    status: str | None = Query("pending"),
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> list[DisambiguationCandidateOut]:
    """列出项目下的角色去重候选（默认仅 pending，供前端确认 UI 消费）。"""
    return await mm_service.list_disambiguation_candidates(db, project_id, status=status)


@router.post(
    "/disambiguation-candidates/{candidate_id}/resolve",
    response_model=DisambiguationCandidateOut,
)
async def resolve_disambiguation_candidate(
    project_id: int,
    candidate_id: int,
    payload: DisambiguationResolveIn,
    pu: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> DisambiguationCandidateOut:
    """用户确认去重候选：new（草稿独立建卡→reviewed）/ merge（合并进既有卡，删除草稿）。"""
    _, user = pu
    try:
        return await mm_service.resolve_disambiguation(
            db, project_id, candidate_id, payload, user
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
