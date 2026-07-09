"""客户管理 API（M1.3.5）。

权限（§3.2）：
- 任何已登录用户可创建客户、查看自己参与项目所属的客户
- admin/super 可见全部
- 编辑/删除仅限 admin 或客户创建者
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.db.session import get_db
from app.models import User
from app.modules.customers import service as customer_service
from app.schemas.customers import CustomerCreate, CustomerOut, CustomerUpdate

router = APIRouter(prefix="/api/customers")


@router.get("", response_model=list[CustomerOut])
async def list_customers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[CustomerOut]:
    """列出客户（admin 全部；普通用户按项目参与过滤）。"""
    return await customer_service.list_customers(db, user)


@router.post(
    "",
    response_model=CustomerOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer(
    payload: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> CustomerOut:
    """创建客户。"""
    return await customer_service.create_customer(db, payload, user)


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> CustomerOut:
    """获取单个客户。无权限视为不存在 → 404。"""
    out = await customer_service.get_customer(db, customer_id, user)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客户不存在")
    return out


@router.put("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> CustomerOut:
    """更新客户（admin 或创建者）。"""
    try:
        return await customer_service.update_customer(db, customer_id, payload, user)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        msg = str(exc)
        if msg == "客户不存在":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    """删除客户（admin 或创建者；存在项目时拒绝）。"""
    try:
        await customer_service.delete_customer(db, customer_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        msg = str(exc)
        if msg == "客户不存在":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
