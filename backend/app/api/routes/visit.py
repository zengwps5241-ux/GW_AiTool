"""拜访记录 API（M2.3）。

挂在 /api/projects/{project_id} 下，受 require_project_member 保护（项目内全透明）：
- /visit-records 拜访记录 CRUD（时间线 + 按类型/角色筛选）
- /evidence-sources 证据 CRUD（多维筛选）
- /evidence-sources/hypotheses/{id}/suggestion §7.5 证据验证联动：建议验证状态
- /evidence-sources/hypotheses/{id}/confirm §7.5 人工确认 → 更新 verificationStatus + 偏差池
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_deps import require_project_member
from app.db.session import get_db
from app.models import Project, User
from app.modules.visits import service as visit_service
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
)

router = APIRouter(prefix="/api/projects/{project_id}")


# ─── 拜访记录 ──────────────────────────────────────────────────


@router.get("/visit-records", response_model=list[VisitRecordOut])
async def list_visits(
    project_id: int,
    visit_type: str | None = Query(None),
    card_id: int | None = Query(None, description="按参与/关联角色卡筛选"),
    review_status: str | None = Query(None),
    include_drafts: bool = Query(False),
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> list[VisitRecordOut]:
    return await visit_service.list_visits(
        db, project_id,
        visit_type=visit_type, card_id=card_id,
        review_status=review_status, include_drafts=include_drafts,
    )


@router.post("/visit-records", response_model=VisitRecordOut, status_code=status.HTTP_201_CREATED)
async def create_visit(
    project_id: int,
    payload: VisitRecordCreate,
    pu: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> VisitRecordOut:
    _, user = pu
    return await visit_service.create_visit(db, project_id, payload, user)


@router.get("/visit-records/{visit_id}", response_model=VisitRecordOut)
async def get_visit(
    project_id: int,
    visit_id: int,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> VisitRecordOut:
    out = await visit_service.get_visit(db, project_id, visit_id)
    if out is None:
        raise HTTPException(status_code=404, detail="拜访记录不存在")
    return out


@router.put("/visit-records/{visit_id}", response_model=VisitRecordOut)
async def update_visit(
    project_id: int,
    visit_id: int,
    payload: VisitRecordUpdate,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> VisitRecordOut:
    out = await visit_service.update_visit(db, project_id, visit_id, payload)
    if out is None:
        raise HTTPException(status_code=404, detail="拜访记录不存在")
    return out


@router.delete("/visit-records/{visit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_visit(
    project_id: int,
    visit_id: int,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not await visit_service.delete_visit(db, project_id, visit_id):
        raise HTTPException(status_code=404, detail="拜访记录不存在")


# ─── 证据 ──────────────────────────────────────────────────────


@router.get("/evidence-sources", response_model=list[EvidenceSourceOut])
async def list_evidence(
    project_id: int,
    visit_id: int | None = Query(None),
    evidence_type: str | None = Query(None),
    strength: str | None = Query(None),
    source_role_id: int | None = Query(None),
    related_hypothesis_id: int | None = Query(None),
    review_status: str | None = Query(None),
    include_drafts: bool = Query(False),
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> list[EvidenceSourceOut]:
    return await visit_service.list_evidence(
        db, project_id,
        visit_id=visit_id, evidence_type=evidence_type, strength=strength,
        source_role_id=source_role_id, related_hypothesis_id=related_hypothesis_id,
        review_status=review_status, include_drafts=include_drafts,
    )


@router.post("/evidence-sources", response_model=EvidenceSourceOut, status_code=status.HTTP_201_CREATED)
async def create_evidence(
    project_id: int,
    payload: EvidenceSourceCreate,
    pu: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> EvidenceSourceOut:
    try:
        _, user = pu
        return await visit_service.create_evidence(db, project_id, payload, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/evidence-sources/{evidence_id}", response_model=EvidenceSourceOut)
async def get_evidence(
    project_id: int,
    evidence_id: int,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> EvidenceSourceOut:
    out = await visit_service.get_evidence(db, project_id, evidence_id)
    if out is None:
        raise HTTPException(status_code=404, detail="证据不存在")
    return out


@router.put("/evidence-sources/{evidence_id}", response_model=EvidenceSourceOut)
async def update_evidence(
    project_id: int,
    evidence_id: int,
    payload: EvidenceSourceUpdate,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> EvidenceSourceOut:
    try:
        out = await visit_service.update_evidence(db, project_id, evidence_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if out is None:
        raise HTTPException(status_code=404, detail="证据不存在")
    return out


@router.delete("/evidence-sources/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evidence(
    project_id: int,
    evidence_id: int,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not await visit_service.delete_evidence(db, project_id, evidence_id):
        raise HTTPException(status_code=404, detail="证据不存在")


# ─── §7.5 证据验证联动 ────────────────────────────────────────


@router.get(
    "/evidence-sources/hypotheses/{hypothesis_id}/suggestion",
    response_model=VerificationSuggestionOut,
)
async def verification_suggestion(
    project_id: int,
    hypothesis_id: int,
    _=Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> VerificationSuggestionOut:
    """按证据聚合给出假设节点的建议验证状态（§7.5.1）。"""
    try:
        return await visit_service.suggest_verification_status(db, project_id, hypothesis_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post(
    "/evidence-sources/hypotheses/{hypothesis_id}/confirm",
    response_model=VerificationConfirmOut,
)
async def verification_confirm(
    project_id: int,
    hypothesis_id: int,
    payload: VerificationConfirmIn,
    pu: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> VerificationConfirmOut:
    """人工确认验证状态 → 更新 verificationStatus + 推翻时自动新增偏差池（§7.5.2/§7.5.3）。"""
    try:
        _, user = pu
        return await visit_service.confirm_verification(db, project_id, hypothesis_id, payload, user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
