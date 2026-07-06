"""管理员使用统计 API。"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import Department, UsageEvent, User
from app.modules.usage.service import build_usage_summary
from app.schemas import UsageSummaryOut, UsageUserOut

router = APIRouter(prefix="/api/admin/usage", dependencies=[Depends(require_admin)])


@router.get("/summary", response_model=UsageSummaryOut)
async def usage_summary(
    range: str = Query("today", pattern="^(today|7d|30d|custom)$"),
    start: date | None = None,
    end: date | None = None,
    user: str | None = Query(None, description="按用户id精确过滤"),
    department: str | None = Query(None, description="按部门模糊过滤"),
    db: AsyncSession = Depends(get_db),
) -> UsageSummaryOut:
    try:
        data = await build_usage_summary(
            db,
            range_name=range,
            start=start,
            end=end,
            username_filter=user,
            department_filter=department,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UsageSummaryOut.model_validate(data)


@router.get("/users", response_model=list[UsageUserOut])
async def usage_users(
    q: str = Query("", description="搜索关键词"),
    db: AsyncSession = Depends(get_db),
) -> list[UsageUserOut]:
    """返回有使用记录的用户列表（姓名+部门+id），支持按姓名模糊搜索。"""
    from sqlalchemy import func

    stmt = (
        select(User.display_name, User.department, User.username)
        .join(UsageEvent, UsageEvent.user_id == User.id)
        .where(func.coalesce(User.display_name, User.username).ilike(f"%{q}%"))
        .distinct()
        .order_by(User.display_name)
        .limit(20)
    )
    rows = (await db.execute(stmt)).mappings().all()
    return [
        UsageUserOut(
            display_name=row["display_name"] or row["username"],
            department=row["department"],
            username=row["username"],
        )
        for row in rows
    ]


@router.get("/departments", response_model=list[str])
async def usage_departments(
    q: str = Query("", description="搜索关键词"),
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    """返回部门列表，支持从部门表模糊搜索。"""
    stmt = select(Department.name)
    if q:
        stmt = stmt.where(Department.name.ilike(f"%{q}%"))
    stmt = stmt.order_by(Department.name).limit(20)
    rows = (await db.execute(stmt)).scalars().all()
    user_stmt = (
        select(distinct(User.department))
        .join(UsageEvent, UsageEvent.user_id == User.id)
        .where(User.department.is_not(None))
    )
    if q:
        user_stmt = user_stmt.where(User.department.ilike(f"%{q}%"))
    user_rows = (await db.execute(user_stmt.limit(20))).scalars().all()
    return sorted({name for name in [*rows, *user_rows] if name})[:20]
