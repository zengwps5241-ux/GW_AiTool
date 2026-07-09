"""统一采纳/审批 API（M2.4）。

挂在 /api/projects/{project_id} 下，受项目级权限保护（§3.3/§3.4）：
- GET /pending-reviews：待审批列表（require_project_member，项目内透明）
- POST /adopt：统一采纳（require_project_member；Owner→直接发布 / Deputy→待审核）
- POST /reviews/{entity_type}/{entity_id}/approve | reject：Owner 审批（require_project_owner）
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.api.project_deps import require_project_member, require_project_owner
from app.db.session import get_db
from app.models import Project, User
from app.modules.reviews import service as reviews_service
from app.schemas.business_map import AdoptResult
from app.schemas.reviews import AdoptRequest, PendingReviewItem, RejectRequest

router = APIRouter(prefix="/api/projects/{project_id}")


@router.get("/pending-reviews", response_model=list[PendingReviewItem])
async def list_pending_reviews(
    project_id: int,
    entity_type: str | None = Query(None, description="按实体类型筛选"),
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> list[PendingReviewItem]:
    """待审批列表：跨模块汇总 pending_review 实体（§3.4 待主手审核区）。"""
    try:
        return await reviews_service.list_pending_reviews(
            db, project_id, entity_type=entity_type
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/adopt", response_model=AdoptResult)
async def adopt(
    project_id: int,
    payload: AdoptRequest,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> AdoptResult:
    """统一采纳：Owner 直接发布；Deputy 进入 pending_review（§3.4）。"""
    project, user = project_and_user
    try:
        return await reviews_service.adopt(db, project_id, payload, user)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/reviews/{entity_type}/{entity_id}/approve",
    response_model=PendingReviewItem,
)
async def approve_review(
    project_id: int,
    entity_type: str,
    entity_id: int,
    project_and_user: tuple[Project, User] = Depends(require_project_owner),
    db: AsyncSession = Depends(get_db),
) -> PendingReviewItem:
    """Owner 通过待审批项 → 发布（reviewed，§7.3 页面立即可见）。"""
    project, user = project_and_user
    try:
        return await reviews_service.approve_review(
            db, project_id, entity_type, entity_id, user
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/reviews/{entity_type}/{entity_id}/reject",
    response_model=PendingReviewItem,
)
async def reject_review(
    project_id: int,
    entity_type: str,
    entity_id: int,
    payload: RejectRequest | None = None,
    project_and_user: tuple[Project, User] = Depends(require_project_owner),
    db: AsyncSession = Depends(get_db),
) -> PendingReviewItem:
    """Owner 驳回待审批项 → 退回（rejected，§3.4）。"""
    project, user = project_and_user
    comment = payload.comment if payload else None
    try:
        return await reviews_service.reject_review(
            db, project_id, entity_type, entity_id, user, comment=comment
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
