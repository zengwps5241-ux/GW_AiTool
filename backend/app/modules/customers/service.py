"""客户（Customer）业务服务层。

职责：
- Customer CRUD
- 可见性过滤：admin 看全部；普通用户仅看「自己参与的项目」所属的客户（M1.3.5）
- 编辑/删除权限：admin 或创建者；删除时若存在项目则拒绝（RESTRICT）

权限模型见需求规格 §3。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer, Project, User
from app.modules.projects.access import get_accessible_project_ids
from app.schemas.customers import CustomerCreate, CustomerOut, CustomerUpdate


async def _user_display_name(db: AsyncSession, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = await db.get(User, user_id)
    if user is None:
        return None
    return user.display_name or user.username


def _to_out(
    customer: Customer,
    created_by_name: str | None,
    project_count: int = 0,
) -> CustomerOut:
    return CustomerOut(
        id=customer.id,
        name=customer.name,
        industry=customer.industry,
        scale=customer.scale,
        region=customer.region,
        description=customer.description,
        created_by=customer.created_by,
        created_by_name=created_by_name,
        visibility=customer.visibility,
        sensitivity_level=customer.sensitivity_level,
        project_count=project_count,
        created_at=customer.created_at.isoformat() if customer.created_at else None,
        updated_at=customer.updated_at.isoformat() if customer.updated_at else None,
    )


async def _project_counts(db: AsyncSession, customer_ids: list[int]) -> dict[int, int]:
    """按 customer_id 统计项目数。"""
    if not customer_ids:
        return {}
    rows = (
        await db.execute(
            select(Project.customer_id, func.count(Project.id))
            .where(Project.customer_id.in_(customer_ids))
            .group_by(Project.customer_id)
        )
    ).all()
    return {cid: cnt for cid, cnt in rows}


async def list_customers(db: AsyncSession, user: User) -> list[CustomerOut]:
    """列出客户。admin 看全部；普通用户看「自己创建的」∪「可访问项目所属」客户。"""
    if user.role in ("admin", "super"):
        customers = (
            await db.execute(select(Customer).order_by(Customer.id))
        ).scalars().all()
    else:
        customer_ids: set[int] = set()
        # 自己创建的客户
        created = (
            await db.execute(select(Customer.id).where(Customer.created_by == user.id))
        ).scalars().all()
        customer_ids.update(created)
        # 可访问项目所属客户
        accessible = await get_accessible_project_ids(db, user)
        if accessible:
            via_project = (
                await db.execute(
                    select(Project.customer_id)
                    .where(Project.id.in_(accessible))
                    .distinct()
                )
            ).scalars().all()
            customer_ids.update(via_project)
        if not customer_ids:
            return []
        customers = (
            await db.execute(
                select(Customer).where(Customer.id.in_(customer_ids)).order_by(Customer.id)
            )
        ).scalars().all()

    ids = [c.id for c in customers]
    counts = await _project_counts(db, ids)
    out: list[CustomerOut] = []
    for c in customers:
        name = await _user_display_name(db, c.created_by)
        out.append(_to_out(c, name, counts.get(c.id, 0)))
    return out


async def get_customer(
    db: AsyncSession, customer_id: int, user: User
) -> CustomerOut | None:
    """获取单个客户。无权限或不存在返回 None。"""
    customer = await db.get(Customer, customer_id)
    if customer is None:
        return None
    # 普通用户需通过项目参与获得访问权
    if user.role not in ("admin", "super") and customer.created_by != user.id:
        accessible = await get_accessible_project_ids(db, user)
        has_project = (
            await db.execute(
                select(Project.id)
                .where(Project.customer_id == customer_id, Project.id.in_(accessible))
                .limit(1)
            )
        ).scalar_one_or_none()
        if has_project is None:
            return None
    counts = await _project_counts(db, [customer_id])
    name = await _user_display_name(db, customer.created_by)
    return _to_out(customer, name, counts.get(customer_id, 0))


async def create_customer(
    db: AsyncSession, payload: CustomerCreate, user: User
) -> CustomerOut:
    """创建客户（任何已登录用户均可）。"""
    customer = Customer(
        name=payload.name,
        industry=payload.industry,
        scale=payload.scale,
        region=payload.region,
        description=payload.description,
        created_by=user.id,
        visibility=payload.visibility,
        sensitivity_level=payload.sensitivity_level,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    name = await _user_display_name(db, customer.created_by)
    return _to_out(customer, name, 0)


async def update_customer(
    db: AsyncSession, customer_id: int, payload: CustomerUpdate, user: User
) -> CustomerOut:
    """更新客户。仅 admin 或创建者可改。"""
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise ValueError("客户不存在")
    if user.role not in ("admin", "super") and customer.created_by != user.id:
        raise PermissionError("无权修改该客户")

    if payload.name is not None:
        customer.name = payload.name
    if payload.industry is not None:
        customer.industry = payload.industry
    if payload.scale is not None:
        customer.scale = payload.scale
    if payload.region is not None:
        customer.region = payload.region
    if payload.description is not None:
        customer.description = payload.description
    if payload.visibility is not None:
        customer.visibility = payload.visibility
    if payload.sensitivity_level is not None:
        customer.sensitivity_level = payload.sensitivity_level

    await db.commit()
    await db.refresh(customer)
    counts = await _project_counts(db, [customer_id])
    name = await _user_display_name(db, customer.created_by)
    return _to_out(customer, name, counts.get(customer_id, 0))


async def delete_customer(db: AsyncSession, customer_id: int, user: User) -> None:
    """删除客户。仅 admin 或创建者可删；存在项目时拒绝。"""
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise ValueError("客户不存在")
    if user.role not in ("admin", "super") and customer.created_by != user.id:
        raise PermissionError("无权删除该客户")

    # 存在项目则拒绝（与 FK RESTRICT 双保险）
    has_project = (
        await db.execute(
            select(Project.id).where(Project.customer_id == customer_id).limit(1)
        )
    ).scalar_one_or_none()
    if has_project is not None:
        raise ValueError("该客户下存在项目，不能删除（请先处理项目）")

    await db.delete(customer)
    await db.commit()
