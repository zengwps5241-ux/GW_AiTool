"""业务地图 API（M2.1）。

挂在 /api/projects/{project_id}/business-map 下，受项目级权限保护：
- 读取 / 对象 CRUD / 草稿 / 采纳 / 健康计算：require_project_member（项目内全透明）
- 版本回滚：require_project_owner（破坏性操作）
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.api.project_deps import require_project_member, require_project_owner
from app.db.session import get_db
from app.models import Project, User
from app.modules.business_map import service as bm_service
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
    VersionDiffOut,
)

router = APIRouter(prefix="/api/projects/{project_id}/business-map")


# ─── 业务地图对象 ──────────────────────────────────────────────


@router.get("/objects", response_model=list[BusinessMapObjectOut])
async def list_objects(
    project_id: int,
    level: str | None = Query(None),
    map_type: str | None = Query(None),
    review_status: str | None = Query(None),
    include_drafts: bool = Query(False),
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> list[BusinessMapObjectOut]:
    """列出业务地图对象（默认只返回 reviewed）。"""
    return await bm_service.list_objects(
        db,
        project_id,
        level=level,
        map_type=map_type,
        review_status=review_status,
        include_drafts=include_drafts,
    )


@router.post(
    "/objects",
    response_model=BusinessMapObjectOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_object(
    project_id: int,
    payload: BusinessMapObjectCreate,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> BusinessMapObjectOut:
    project, user = project_and_user
    return await bm_service.create_object(db, project_id, payload, user)


@router.get("/objects/{object_id}", response_model=BusinessMapObjectOut)
async def get_object(
    project_id: int,
    object_id: int,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> BusinessMapObjectOut:
    out = await bm_service.get_object(db, project_id, object_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对象不存在")
    return out


@router.put("/objects/{object_id}", response_model=BusinessMapObjectOut)
async def update_object(
    project_id: int,
    object_id: int,
    payload: BusinessMapObjectUpdate,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> BusinessMapObjectOut:
    out = await bm_service.update_object(db, project_id, object_id, payload)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对象不存在")
    return out


@router.delete("/objects/{object_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_object(
    project_id: int,
    object_id: int,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> None:
    ok = await bm_service.delete_object(db, project_id, object_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对象不存在")


# ─── 前置分析 ──────────────────────────────────────────────────


@router.get("/pre-analysis", response_model=PreAnalysisOut | None)
async def get_pre_analysis(
    project_id: int,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> PreAnalysisOut | None:
    """获取项目前置分析（不存在返回 null）。"""
    return await bm_service.get_pre_analysis(db, project_id)


@router.put("/pre-analysis", response_model=PreAnalysisOut)
async def upsert_pre_analysis(
    project_id: int,
    payload: PreAnalysisInput,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> PreAnalysisOut:
    project, user = project_and_user
    return await bm_service.upsert_pre_analysis(db, project_id, payload, user)


# ─── 草稿区 + 采纳 ─────────────────────────────────────────────


@router.get("/drafts", response_model=BusinessMapDraftOut | None)
async def get_draft(
    project_id: int,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> BusinessMapDraftOut | None:
    """获取当前 active 草稿（顺带标记已过期草稿）。"""
    return await bm_service.get_active_draft(db, project_id)


@router.put("/drafts", response_model=BusinessMapDraftOut)
async def upsert_draft(
    project_id: int,
    payload: BusinessMapDraftUpdate,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> BusinessMapDraftOut:
    project, user = project_and_user
    return await bm_service.upsert_draft(db, project_id, payload, user)


@router.post("/drafts/{draft_id}/adopt", response_model=AdoptResult)
async def adopt_draft(
    project_id: int,
    draft_id: int,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> AdoptResult:
    """采纳草稿：对象写入正式表 + 版本快照。Owner→直接发布；Deputy→待审核。"""
    project, user = project_and_user
    try:
        return await bm_service.adopt_draft(db, project_id, draft_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ─── 版本管理 + 回滚 ───────────────────────────────────────────


@router.get("/versions", response_model=list[BusinessMapVersionOut])
async def list_versions(
    project_id: int,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> list[BusinessMapVersionOut]:
    return await bm_service.list_versions(db, project_id)


@router.get("/versions/{version_id}", response_model=BusinessMapVersionOut)
async def get_version(
    project_id: int,
    version_id: int,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> BusinessMapVersionOut:
    out = await bm_service.get_version(db, project_id, version_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="版本不存在")
    return out


@router.get("/versions/{version_id}/diff", response_model=VersionDiffOut)
async def diff_version(
    project_id: int,
    version_id: int,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> VersionDiffOut:
    """对比历史版本快照与当前 reviewed 数据（M5.3.2）：added / removed / changed。"""
    out = await bm_service.diff_version_against_current(db, project_id, version_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="版本不存在")
    return out


@router.post("/versions/{version_id}/rollback", response_model=BusinessMapVersionOut)
async def rollback_version(
    project_id: int,
    version_id: int,
    project_and_user: tuple[Project, User] = Depends(require_project_owner),
    db: AsyncSession = Depends(get_db),
) -> BusinessMapVersionOut:
    """回滚到历史版本（仅 Owner / admin；自动留存回滚前审计快照）。"""
    project, user = project_and_user
    try:
        return await bm_service.rollback_to_version(db, project_id, version_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ─── 五维健康 ──────────────────────────────────────────────────


@router.post("/objects/{object_id}/health", response_model=FiveDimHealthOut)
async def compute_object_health(
    project_id: int,
    object_id: int,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> FiveDimHealthOut:
    """对单个节点重新计算五维健康（规则版）。L4 等无五维健康的节点返回 400。"""
    out = await bm_service.compute_node_health(db, project_id, object_id)
    if out is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该节点不存在或不支持五维健康计算",
        )
    return out


@router.post("/health/recompute", response_model=list[FiveDimHealthOut])
async def recompute_health(
    project_id: int,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> list[FiveDimHealthOut]:
    """批量重评估项目下所有 L1/L2/L3 节点的五维健康。"""
    return await bm_service.recompute_project_health(db, project_id)


@router.put("/objects/{object_id}/health", response_model=FiveDimHealthOut)
async def set_object_health(
    project_id: int,
    object_id: int,
    payload: dict,
    project_and_user: tuple[Project, User] = Depends(require_project_member),
    db: AsyncSession = Depends(get_db),
) -> FiveDimHealthOut:
    """手动覆盖某节点的五维健康评分（标记 manual）。"""
    project, user = project_and_user
    out = await bm_service.set_node_health(db, project_id, object_id, payload, user)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对象不存在")
    return out
