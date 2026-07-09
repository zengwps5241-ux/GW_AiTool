"""组织架构管理 API（自建三级架构：公司→部门→小组）。

仅 admin/super 可访问。提供：
- 组织节点 CRUD
- 树形结构查询（含成员）
- 成员管理（添加/移除）
- 批量导入（JSON / CSV）
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import User
from app.modules.organizations import service as org_service
from app.schemas.organizations import (
    OrganizationCreate,
    OrganizationImportResponse,
    OrganizationImportRow,
    OrganizationOut,
    OrganizationTreeNode,
    OrganizationUpdate,
    UserOrganizationCreate,
    UserOrganizationOut,
)

router = APIRouter(prefix="/api/admin/organizations")
logger = logging.getLogger(__name__)


@router.get("", response_model=list[OrganizationOut])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[OrganizationOut]:
    """列出全部组织节点（扁平列表）。"""
    return await org_service.list_organizations(db)


@router.get("/tree", response_model=list[OrganizationTreeNode])
async def get_organization_tree(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[OrganizationTreeNode]:
    """返回完整组织树（递归父子 + 成员）。"""
    return await org_service.get_organization_tree(db)


@router.post(
    "",
    response_model=OrganizationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization(
    payload: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> OrganizationOut:
    """创建组织节点。"""
    try:
        return await org_service.create_organization(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> OrganizationOut:
    """获取单个组织节点。"""
    out = await org_service.get_organization(db, org_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="组织不存在")
    return out


@router.put("/{org_id}", response_model=OrganizationOut)
async def update_organization(
    org_id: int,
    payload: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> OrganizationOut:
    """更新组织节点。"""
    try:
        return await org_service.update_organization(db, org_id, payload)
    except ValueError as exc:
        msg = str(exc)
        # 不存在 → 404，其余校验错误 → 400
        if msg == "组织不存在":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """删除组织节点（有子节点/成员时拒绝）。"""
    try:
        await org_service.delete_organization(db, org_id)
    except ValueError as exc:
        msg = str(exc)
        if msg == "组织不存在":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ─── 成员管理 ────────────────────────────────────────────────


@router.get("/{org_id}/members", response_model=list[UserOrganizationOut])
async def list_members(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[UserOrganizationOut]:
    """列出组织下的成员。"""
    tree = await org_service.get_organization_tree(db)
    # 在树中找到该节点
    def _find(nodes: list[OrganizationTreeNode]) -> OrganizationTreeNode | None:
        for n in nodes:
            if n.id == org_id:
                return n
            found = _find(n.children)
            if found:
                return found
        return None
    node = _find(tree)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="组织不存在")
    return node.members


@router.post(
    "/{org_id}/members",
    response_model=UserOrganizationOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    org_id: int,
    payload: UserOrganizationCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> UserOrganizationOut:
    """添加用户到组织。"""
    try:
        return await org_service.add_member(db, org_id, payload)
    except ValueError as exc:
        msg = str(exc)
        if msg == "组织不存在":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.delete(
    "/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_member(
    org_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """从组织移除用户。"""
    try:
        await org_service.remove_member(db, org_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ─── 批量导入 ────────────────────────────────────────────────


@router.post("/import", response_model=OrganizationImportResponse)
async def import_organizations(
    payload: list[OrganizationImportRow],
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> OrganizationImportResponse:
    """批量导入组织架构（JSON 数组）。

    请求体为 OrganizationImportRow 数组。也可通过 content_type=csv 上传 CSV 文本，
    该场景请使用 /import-csv 端点。
    """
    result = await org_service.import_organizations(db, payload)
    return OrganizationImportResponse(success=True, result=result)


@router.post("/import-csv", response_model=OrganizationImportResponse)
async def import_organizations_csv(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> OrganizationImportResponse:
    """批量导入组织架构（CSV 文本）。

    请求体: {"content": "name,type,parent_name,...\\n...", "content_type": "csv"}
    列名: name,type,parent_name,head_user_username,position_title,is_primary,sort_order
    """
    content = (payload or {}).get("content") or ""
    if not content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="导入内容为空")
    rows = org_service.parse_import_rows(content, content_type="csv")
    result = await org_service.import_organizations(db, rows)
    return OrganizationImportResponse(success=True, result=result)
