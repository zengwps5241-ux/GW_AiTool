"""登录白名单业务逻辑。"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Department, LoginWhitelistDepartment, LoginWhitelistUser


WHITELIST_DENIED_MESSAGE = "当前账号未在登录白名单中，请联系管理员"


@dataclass(frozen=True)
class LoginWhitelistCheckResult:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class DepartmentSearchItem:
    department_id: int
    name: str
    path: str


async def check_wechat_login_allowed(
    db: AsyncSession,
    name: str | None,
    department_ids: list[int] | None,
) -> LoginWhitelistCheckResult:
    """判断企业微信用户是否命中登录白名单。"""
    user_names = set(await _list_user_names(db))
    whitelist_department_ids = set(await _list_department_ids(db))
    if not user_names and not whitelist_department_ids:
        return LoginWhitelistCheckResult(True, "empty_whitelist")

    normalized_name = (name or "").strip()
    if normalized_name and normalized_name in user_names:
        return LoginWhitelistCheckResult(True, "user_name")

    if whitelist_department_ids:
        departments = await _load_departments(db)
        for department_id in department_ids or []:
            if _department_or_ancestor_allowed(
                int(department_id), whitelist_department_ids, departments
            ):
                return LoginWhitelistCheckResult(True, "department")

    return LoginWhitelistCheckResult(False, "not_matched")


async def search_departments(
    db: AsyncSession,
    keyword: str,
) -> list[DepartmentSearchItem]:
    """按名称模糊搜索部门，并返回完整路径。"""
    keyword = keyword.strip()
    if not keyword:
        return []

    result = await db.execute(select(Department).order_by(Department.id))
    departments = {department.id: department for department in result.scalars().all()}
    matches = [
        department
        for department in departments.values()
        if keyword in department.name
    ]
    return [
        DepartmentSearchItem(
            department_id=department.id,
            name=department.name,
            path=_department_path(department.id, departments),
        )
        for department in matches
    ]


async def department_path(db: AsyncSession, department_id: int) -> str:
    """返回单个部门路径，找不到时回退为部门 ID 字符串。"""
    departments = await _load_departments(db)
    return _department_path(department_id, departments)


async def _list_user_names(db: AsyncSession) -> list[str]:
    result = await db.execute(select(LoginWhitelistUser.name))
    return [name for name in result.scalars().all()]


async def _list_department_ids(db: AsyncSession) -> list[int]:
    result = await db.execute(select(LoginWhitelistDepartment.department_id))
    return [department_id for department_id in result.scalars().all()]


async def _load_departments(db: AsyncSession) -> dict[int, Department]:
    result = await db.execute(select(Department))
    return {department.id: department for department in result.scalars().all()}


def _department_or_ancestor_allowed(
    department_id: int,
    whitelist_department_ids: set[int],
    departments: dict[int, Department],
) -> bool:
    current_id: int | None = department_id
    seen: set[int] = set()
    while current_id and current_id not in seen:
        if current_id in whitelist_department_ids:
            return True
        seen.add(current_id)
        current = departments.get(current_id)
        current_id = current.parent_id if current else None
    return False


def _department_path(
    department_id: int,
    departments: dict[int, Department],
) -> str:
    names: list[str] = []
    current_id: int | None = department_id
    seen: set[int] = set()
    while current_id and current_id not in seen:
        seen.add(current_id)
        current = departments.get(current_id)
        if current is None:
            names.append(str(current_id))
            break
        names.append(current.name)
        current_id = current.parent_id
    return " / ".join(reversed(names))
