"""管理员登录白名单 API。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_super
from app.db.session import get_db
from app.models import Department, LoginWhitelistDepartment, LoginWhitelistUser
from app.modules.auth.login_whitelist import department_path, search_departments
from app.schemas.login_whitelist import (
    LoginWhitelistDepartmentCreate,
    LoginWhitelistDepartmentOut,
    LoginWhitelistDepartmentSearchOut,
    LoginWhitelistOut,
    LoginWhitelistUserCreate,
    LoginWhitelistUserOut,
)

router = APIRouter(prefix="/api/admin/login-whitelist")


@router.get("", response_model=LoginWhitelistOut)
async def get_login_whitelist(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_super),
) -> LoginWhitelistOut:
    user_rows = (
        await db.execute(select(LoginWhitelistUser).order_by(LoginWhitelistUser.id))
    ).scalars().all()
    department_rows = (
        await db.execute(
            select(LoginWhitelistDepartment).order_by(LoginWhitelistDepartment.id)
        )
    ).scalars().all()
    departments: list[LoginWhitelistDepartmentOut] = []
    for row in department_rows:
        department = await db.get(Department, row.department_id)
        departments.append(
            LoginWhitelistDepartmentOut(
                id=row.id,
                department_id=row.department_id,
                name=department.name if department else str(row.department_id),
                path=await department_path(db, row.department_id),
            )
        )
    return LoginWhitelistOut(
        users=[LoginWhitelistUserOut(id=row.id, name=row.name) for row in user_rows],
        departments=departments,
    )


@router.post(
    "/users",
    response_model=LoginWhitelistUserOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_whitelist_user(
    payload: LoginWhitelistUserCreate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_super),
) -> LoginWhitelistUserOut:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="姓名不能为空")
    existing = await db.execute(
        select(LoginWhitelistUser).where(LoginWhitelistUser.name == name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="用户姓名已存在")
    row = LoginWhitelistUser(name=name)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return LoginWhitelistUserOut(id=row.id, name=row.name)


@router.delete("/users/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_whitelist_user(
    row_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_super),
) -> None:
    row = await db.get(LoginWhitelistUser, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="用户白名单不存在")
    await db.delete(row)
    await db.commit()


@router.get(
    "/departments/search",
    response_model=list[LoginWhitelistDepartmentSearchOut],
)
async def search_whitelist_departments(
    q: str = "",
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_super),
) -> list[LoginWhitelistDepartmentSearchOut]:
    return [
        LoginWhitelistDepartmentSearchOut(
            department_id=item.department_id,
            name=item.name,
            path=item.path,
        )
        for item in await search_departments(db, q)
    ]


@router.post(
    "/departments",
    response_model=LoginWhitelistDepartmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_whitelist_department(
    payload: LoginWhitelistDepartmentCreate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_super),
) -> LoginWhitelistDepartmentOut:
    department = await db.get(Department, payload.department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="部门不存在")
    existing = await db.execute(
        select(LoginWhitelistDepartment).where(
            LoginWhitelistDepartment.department_id == payload.department_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="部门白名单已存在")
    row = LoginWhitelistDepartment(department_id=payload.department_id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return LoginWhitelistDepartmentOut(
        id=row.id,
        department_id=row.department_id,
        name=department.name,
        path=await department_path(db, row.department_id),
    )


@router.delete("/departments/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_whitelist_department(
    row_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_super),
) -> None:
    row = await db.get(LoginWhitelistDepartment, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="部门白名单不存在")
    await db.delete(row)
    await db.commit()
