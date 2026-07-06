# Login Whitelist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-managed login whitelist that allows enterprise WeChat users to log in by exact display name or by department including all descendant departments.

**Architecture:** Backend adds focused whitelist models, schemas, service functions, and admin routes, then calls the service from both enterprise WeChat login paths before local user/session creation. Frontend adds an admin-only sidebar entry and a management page backed by typed API client methods, plus login-page handling for whitelist denial errors.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic, pytest, React, TypeScript, Vite.

---

## File Structure

- Create `backend/app/models/login_whitelist.py`: SQLAlchemy models for user-name and department whitelist rows.
- Modify `backend/app/models/__init__.py`: export the new models for `Base.metadata.create_all`.
- Modify `backend/app/db/migrations.py`: create whitelist tables in existing startup migration flow.
- Create `backend/app/schemas/login_whitelist.py`: Pydantic request/response models for admin API.
- Create `backend/app/modules/auth/login_whitelist.py`: whitelist listing, department path/search, and login authorization rules.
- Create `backend/app/api/routes/admin_login_whitelist.py`: admin CRUD and department search endpoints.
- Modify `backend/app/api/router.py`: include the new admin router.
- Modify `backend/app/api/routes/auth.py`: call whitelist authorization in SSO and QR-code login before syncing local user.
- Create `backend/tests/test_login_whitelist_service.py`: rule-level tests.
- Create `backend/tests/test_admin_login_whitelist_api.py`: admin API tests.
- Modify `backend/tests/test_auth_api.py`: login denial and empty-whitelist behavior tests.
- Modify `backend/tests/conftest.py`: reload new modules during test environment setup.
- Modify `frontend/src/types/index.ts`: add whitelist types and `ViewName`.
- Modify `frontend/src/api/client.ts`: add admin whitelist API calls and attach status to HTTP errors.
- Modify `frontend/src/components/Sidebar.tsx`: add admin-only sidebar entry.
- Modify `frontend/src/App.tsx`: route to the new page and breadcrumb.
- Create `frontend/src/pages/LoginWhitelistPage.tsx`: admin management UI.
- Modify `frontend/src/pages/LoginPage.tsx`: show whitelist denial errors.

---

### Task 1: Backend Data Model and Migration

**Files:**
- Create: `backend/app/models/login_whitelist.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_login_whitelist_service.py`

- [ ] **Step 1: Write the failing migration/model test**

Create `backend/tests/test_login_whitelist_service.py` with this initial content:

```python
from sqlalchemy import select


async def test_login_whitelist_tables_exist(client, app_env):
    """启动迁移后应创建登录白名单表。"""
    from app.db.session import async_session
    from app.models import LoginWhitelistDepartment, LoginWhitelistUser

    async with async_session() as db:
        user_row = LoginWhitelistUser(name="张三")
        dept_row = LoginWhitelistDepartment(department_id=100)
        db.add_all([user_row, dept_row])
        await db.commit()

    async with async_session() as db:
        users = (await db.execute(select(LoginWhitelistUser))).scalars().all()
        departments = (
            await db.execute(select(LoginWhitelistDepartment))
        ).scalars().all()
        assert [u.name for u in users] == ["张三"]
        assert [d.department_id for d in departments] == [100]
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd backend && uv run pytest tests/test_login_whitelist_service.py::test_login_whitelist_tables_exist -q
```

Expected: FAIL because `LoginWhitelistUser` and `LoginWhitelistDepartment` are not defined/exported.

- [ ] **Step 3: Add the SQLAlchemy models**

Create `backend/app/models/login_whitelist.py`:

```python
"""登录白名单 ORM 模型。"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LoginWhitelistUser(Base):
    __tablename__ = "login_whitelist_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )


class LoginWhitelistDepartment(Base):
    __tablename__ = "login_whitelist_departments"
    __table_args__ = (
        UniqueConstraint("department_id", name="uq_login_whitelist_department_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )
```

Modify `backend/app/models/__init__.py`:

```python
from app.db.base import Base
from app.models.agent import Agent
from app.models.category import Category, PluginBinding, SkillBinding
from app.models.conversion_task import ConversionTask
from app.models.department import Department
from app.models.feedback import FeedbackAttachment, FeedbackIssue
from app.models.login_whitelist import LoginWhitelistDepartment, LoginWhitelistUser
from app.models.session import ChatSession
from app.models.usage import UsageEvent, UsageResourceEvent
from app.models.user import User

__all__ = [
    "Base",
    "Agent",
    "Category",
    "ChatSession",
    "ConversionTask",
    "Department",
    "FeedbackAttachment",
    "FeedbackIssue",
    "LoginWhitelistDepartment",
    "LoginWhitelistUser",
    "PluginBinding",
    "SkillBinding",
    "UsageEvent",
    "UsageResourceEvent",
    "User",
]
```

- [ ] **Step 4: Add startup migrations**

In `backend/app/db/migrations.py`, after the `departments` table block, add:

```python
        # 登录用户姓名白名单表
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='login_whitelist_users'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE login_whitelist_users ("
                "id SERIAL PRIMARY KEY, "
                "name VARCHAR UNIQUE NOT NULL, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))

        # 登录部门白名单表
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='login_whitelist_departments'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE login_whitelist_departments ("
                "id SERIAL PRIMARY KEY, "
                "department_id INTEGER UNIQUE NOT NULL, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))
```

- [ ] **Step 5: Reload new modules in test fixture**

In `backend/tests/conftest.py`, update the model imports and reloads:

```python
    from app.models import agent as model_agent, category as model_category, conversion_task as model_conversion_task, department as model_department, feedback as model_feedback, login_whitelist as model_login_whitelist, session as model_session, usage as model_usage, user as model_user
```

Add:

```python
    reload(model_login_whitelist)
```

- [ ] **Step 6: Run the focused test and commit**

Run:

```bash
cd backend && uv run pytest tests/test_login_whitelist_service.py::test_login_whitelist_tables_exist -q
```

Expected: PASS.

Commit:

```bash
git add backend/app/models/login_whitelist.py backend/app/models/__init__.py backend/app/db/migrations.py backend/tests/test_login_whitelist_service.py backend/tests/conftest.py
git commit -m "feat: 增加登录白名单数据模型"
```

---

### Task 2: Backend Whitelist Service Rules

**Files:**
- Create: `backend/app/modules/auth/login_whitelist.py`
- Modify: `backend/tests/test_login_whitelist_service.py`

- [ ] **Step 1: Add failing service rule tests**

Append to `backend/tests/test_login_whitelist_service.py`:

```python
import pytest


async def test_empty_whitelist_allows_login(client, app_env):
    """未配置白名单时不限制企微登录。"""
    from app.db.session import async_session
    from app.modules.auth.login_whitelist import check_wechat_login_allowed

    async with async_session() as db:
        allowed = await check_wechat_login_allowed(
            db, name="任何人", department_ids=[999]
        )

    assert allowed.allowed is True
    assert allowed.reason == "empty_whitelist"


async def test_user_name_requires_exact_match_after_trim(client, app_env):
    """姓名白名单应 trim 后完全匹配，不做包含匹配。"""
    from app.db.session import async_session
    from app.models import LoginWhitelistUser
    from app.modules.auth.login_whitelist import check_wechat_login_allowed

    async with async_session() as db:
        db.add(LoginWhitelistUser(name="张三"))
        await db.commit()

    async with async_session() as db:
        exact = await check_wechat_login_allowed(
            db, name=" 张三 ", department_ids=[]
        )
        partial = await check_wechat_login_allowed(
            db, name="张三天", department_ids=[]
        )

    assert exact.allowed is True
    assert exact.reason == "user_name"
    assert partial.allowed is False
    assert partial.reason == "not_matched"


async def test_department_whitelist_allows_descendant_departments(client, app_env):
    """部门白名单应允许本部门和所有多层后代部门。"""
    from app.db.session import async_session
    from app.models import Department, LoginWhitelistDepartment
    from app.modules.auth.login_whitelist import check_wechat_login_allowed

    async with async_session() as db:
        db.add_all([
            Department(id=1, name="集团", parent_id=0),
            Department(id=2, name="研发部", parent_id=1),
            Department(id=3, name="平台组", parent_id=2),
            Department(id=4, name="产品部", parent_id=1),
            LoginWhitelistDepartment(department_id=2),
        ])
        await db.commit()

    async with async_session() as db:
        same_department = await check_wechat_login_allowed(
            db, name="李四", department_ids=[2]
        )
        descendant = await check_wechat_login_allowed(
            db, name="王五", department_ids=[3]
        )
        sibling = await check_wechat_login_allowed(
            db, name="赵六", department_ids=[4]
        )
        parent = await check_wechat_login_allowed(
            db, name="钱七", department_ids=[1]
        )

    assert same_department.allowed is True
    assert descendant.allowed is True
    assert sibling.allowed is False
    assert parent.allowed is False


async def test_search_departments_returns_paths(client, app_env):
    """部门搜索应支持模糊匹配并返回部门路径。"""
    from app.db.session import async_session
    from app.models import Department
    from app.modules.auth.login_whitelist import search_departments

    async with async_session() as db:
        db.add_all([
            Department(id=1, name="集团", parent_id=0),
            Department(id=2, name="研发部", parent_id=1),
            Department(id=3, name="研发平台组", parent_id=2),
        ])
        await db.commit()

    async with async_session() as db:
        results = await search_departments(db, "研发")

    assert [
        (item.department_id, item.name, item.path) for item in results
    ] == [
        (2, "研发部", "集团 / 研发部"),
        (3, "研发平台组", "集团 / 研发部 / 研发平台组"),
    ]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd backend && uv run pytest tests/test_login_whitelist_service.py -q
```

Expected: FAIL because `app.modules.auth.login_whitelist` does not exist.

- [ ] **Step 3: Implement the service module**

Create `backend/app/modules/auth/login_whitelist.py`:

```python
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
```

- [ ] **Step 4: Add module reload to test fixture**

In `backend/tests/conftest.py`, add the auth module import and reload described in Task 1 Step 5:

```python
    from app.modules.auth import service as auth_service, departments as auth_departments, login_whitelist as auth_login_whitelist
```

```python
    reload(auth_login_whitelist)
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
cd backend && uv run pytest tests/test_login_whitelist_service.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/app/modules/auth/login_whitelist.py backend/tests/test_login_whitelist_service.py backend/tests/conftest.py
git commit -m "feat: 增加登录白名单匹配规则"
```

---

### Task 3: Admin Whitelist API

**Files:**
- Create: `backend/app/schemas/login_whitelist.py`
- Create: `backend/app/api/routes/admin_login_whitelist.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_admin_login_whitelist_api.py`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/test_admin_login_whitelist_api.py`:

```python
async def test_admin_login_whitelist_user_crud(admin_client):
    """管理员可以添加、查看、删除用户姓名白名单。"""
    res = await admin_client.post(
        "/api/admin/login-whitelist/users",
        json={"name": " 张三 "},
    )
    assert res.status_code == 201
    user_item = res.json()
    assert user_item["name"] == "张三"

    duplicate = await admin_client.post(
        "/api/admin/login-whitelist/users",
        json={"name": "张三"},
    )
    assert duplicate.status_code == 409

    empty = await admin_client.post(
        "/api/admin/login-whitelist/users",
        json={"name": "   "},
    )
    assert empty.status_code == 400

    listing = await admin_client.get("/api/admin/login-whitelist")
    assert listing.status_code == 200
    assert listing.json()["users"] == [user_item]
    assert listing.json()["departments"] == []

    deleted = await admin_client.delete(
        f"/api/admin/login-whitelist/users/{user_item['id']}"
    )
    assert deleted.status_code == 204

    listing = await admin_client.get("/api/admin/login-whitelist")
    assert listing.json()["users"] == []


async def test_admin_login_whitelist_department_crud_and_search(admin_client):
    """管理员可以搜索、添加、查看、删除部门白名单。"""
    from app.db.session import async_session
    from app.models import Department

    async with async_session() as db:
        db.add_all([
            Department(id=1, name="集团", parent_id=0),
            Department(id=2, name="研发部", parent_id=1),
            Department(id=3, name="研发平台组", parent_id=2),
        ])
        await db.commit()

    search = await admin_client.get(
        "/api/admin/login-whitelist/departments/search?q=研发"
    )
    assert search.status_code == 200
    assert search.json() == [
        {"department_id": 2, "name": "研发部", "path": "集团 / 研发部"},
        {"department_id": 3, "name": "研发平台组", "path": "集团 / 研发部 / 研发平台组"},
    ]

    created = await admin_client.post(
        "/api/admin/login-whitelist/departments",
        json={"department_id": 2},
    )
    assert created.status_code == 201
    department_item = created.json()
    assert department_item["department_id"] == 2
    assert department_item["path"] == "集团 / 研发部"

    duplicate = await admin_client.post(
        "/api/admin/login-whitelist/departments",
        json={"department_id": 2},
    )
    assert duplicate.status_code == 409

    missing = await admin_client.post(
        "/api/admin/login-whitelist/departments",
        json={"department_id": 999},
    )
    assert missing.status_code == 404

    listing = await admin_client.get("/api/admin/login-whitelist")
    assert listing.status_code == 200
    assert listing.json()["departments"] == [department_item]

    deleted = await admin_client.delete(
        f"/api/admin/login-whitelist/departments/{department_item['id']}"
    )
    assert deleted.status_code == 204


async def test_login_whitelist_requires_admin(logged_in_client):
    """普通用户不能访问登录白名单管理接口。"""
    res = await logged_in_client.get("/api/admin/login-whitelist")
    assert res.status_code == 403
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd backend && uv run pytest tests/test_admin_login_whitelist_api.py -q
```

Expected: FAIL because the route is not registered.

- [ ] **Step 3: Add Pydantic schemas**

Create `backend/app/schemas/login_whitelist.py`:

```python
"""登录白名单 API 模型。"""

from pydantic import BaseModel


class LoginWhitelistUserCreate(BaseModel):
    name: str


class LoginWhitelistUserOut(BaseModel):
    id: int
    name: str


class LoginWhitelistDepartmentCreate(BaseModel):
    department_id: int


class LoginWhitelistDepartmentOut(BaseModel):
    id: int
    department_id: int
    name: str
    path: str


class LoginWhitelistDepartmentSearchOut(BaseModel):
    department_id: int
    name: str
    path: str


class LoginWhitelistOut(BaseModel):
    users: list[LoginWhitelistUserOut]
    departments: list[LoginWhitelistDepartmentOut]
```

- [ ] **Step 4: Implement admin route**

Create `backend/app/api/routes/admin_login_whitelist.py`:

```python
"""管理员登录白名单 API。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
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
    _admin=Depends(require_admin),
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
    _admin=Depends(require_admin),
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
    _admin=Depends(require_admin),
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
    _admin=Depends(require_admin),
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
    _admin=Depends(require_admin),
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
    _admin=Depends(require_admin),
) -> None:
    row = await db.get(LoginWhitelistDepartment, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="部门白名单不存在")
    await db.delete(row)
    await db.commit()
```

- [ ] **Step 5: Register route and reload it in tests**

Modify `backend/app/api/router.py` import tuple:

```python
    admin_login_whitelist,
```

Add router registration near other admin routes:

```python
router.include_router(admin_login_whitelist.router)
```

In `backend/tests/conftest.py`, add the API route import and reload described in Task 1 Step 5.

- [ ] **Step 6: Run tests and commit**

Run:

```bash
cd backend && uv run pytest tests/test_admin_login_whitelist_api.py tests/test_login_whitelist_service.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/app/schemas/login_whitelist.py backend/app/api/routes/admin_login_whitelist.py backend/app/api/router.py backend/tests/test_admin_login_whitelist_api.py backend/tests/conftest.py
git commit -m "feat: 增加登录白名单管理接口"
```

---

### Task 4: Enforce Whitelist During Enterprise WeChat Login

**Files:**
- Modify: `backend/app/api/routes/auth.py`
- Modify: `backend/tests/test_auth_api.py`

- [ ] **Step 1: Add failing auth tests**

Append to `backend/tests/test_auth_api.py`:

```python
async def test_wechat_work_login_by_code_denied_by_whitelist(client, monkeypatch, app_env):
    """未命中白名单时二维码登录应返回 403 且不创建用户。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    from unittest.mock import AsyncMock, patch
    from sqlalchemy import select
    from app.db.session import async_session
    from app.models import LoginWhitelistUser, User
    from app.modules.auth import wechat_work

    async with async_session() as db:
        db.add(LoginWhitelistUser(name="允许用户"))
        await db.commit()

    res = await client.get("/api/auth/wechat-work/qrcode-config")
    state = res.json()["state"]
    await client.get(f"/api/auth/wechat-work/callback?code=deny_code&state={state}")
    res = await client.get(f"/api/auth/wechat-work/poll-code?state={state}")
    assert res.json()["code"] == "deny_code"

    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "auth_get_user_info", new=AsyncMock(return_value={
             "userid": "DeniedUser",
             "user_ticket": "ticket_denied",
         })), \
         patch.object(wechat_work, "auth_get_user_detail", new=AsyncMock(return_value={
             "userid": "DeniedUser",
             "name": "拒绝用户",
         })), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": "DeniedUser",
             "name": "拒绝用户",
             "department": [],
             "position": None,
         })):
        res = await client.post(
            "/api/auth/wechat-work/login-by-code",
            json={"code": "deny_code"},
        )

    assert res.status_code == 403
    assert res.json()["detail"] == "当前账号未在登录白名单中，请联系管理员"
    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "DeniedUser"))
        assert result.scalar_one_or_none() is None


async def test_wechat_work_login_by_code_allows_department_descendant(client, monkeypatch, app_env):
    """命中白名单部门的后代部门时应允许二维码登录。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    from unittest.mock import AsyncMock, patch
    from app.db.session import async_session
    from app.models import Department, LoginWhitelistDepartment
    from app.modules.auth import wechat_work

    async with async_session() as db:
        db.add_all([
            Department(id=1, name="集团", parent_id=0),
            Department(id=2, name="研发部", parent_id=1),
            Department(id=3, name="平台组", parent_id=2),
            LoginWhitelistDepartment(department_id=2),
        ])
        await db.commit()

    res = await client.get("/api/auth/wechat-work/qrcode-config")
    state = res.json()["state"]
    await client.get(f"/api/auth/wechat-work/callback?code=allow_code&state={state}")
    res = await client.get(f"/api/auth/wechat-work/poll-code?state={state}")
    assert res.json()["code"] == "allow_code"

    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "auth_get_user_info", new=AsyncMock(return_value={
             "userid": "DeptUser",
             "user_ticket": "ticket_dept",
         })), \
         patch.object(wechat_work, "auth_get_user_detail", new=AsyncMock(return_value={
             "userid": "DeptUser",
             "name": "部门用户",
         })), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": "DeptUser",
             "name": "部门用户",
             "department": [3],
             "position": "工程师",
         })):
        res = await client.post(
            "/api/auth/wechat-work/login-by-code",
            json={"code": "allow_code"},
        )

    assert res.status_code == 200
    assert res.json()["success"] is True
```

- [ ] **Step 2: Run tests and verify denial test fails**

Run:

```bash
cd backend && uv run pytest tests/test_auth_api.py::test_wechat_work_login_by_code_denied_by_whitelist tests/test_auth_api.py::test_wechat_work_login_by_code_allows_department_descendant -q
```

Expected: first test FAIL because login is still allowed; second may PASS after service exists.

- [ ] **Step 3: Add auth helper and enforce QR-code login**

In `backend/app/api/routes/auth.py`, add imports:

```python
import logging
from app.modules.auth.login_whitelist import (
    WHITELIST_DENIED_MESSAGE,
    check_wechat_login_allowed,
)
```

Add module logger near `_auth_code_store`:

```python
logger = logging.getLogger(__name__)
```

Add helper below `_sync_user_from_detail`:

```python
async def _ensure_wechat_login_allowed(
    db: AsyncSession,
    user_id: str,
    user_detail: dict,
) -> None:
    """在写入本地用户前执行企微登录白名单校验。"""
    department_ids = [int(did) for did in user_detail.get("department") or []]
    result = await check_wechat_login_allowed(
        db,
        name=user_detail.get("name"),
        department_ids=department_ids,
    )
    if result.allowed:
        return
    logger.warning(
        "企微用户未命中登录白名单: userid=%s name=%s department_ids=%s",
        user_id,
        user_detail.get("name"),
        department_ids,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=WHITELIST_DENIED_MESSAGE,
    )
```

In `wechat_work_login_by_code`, before `_sync_user_from_detail`, add:

```python
        await _ensure_wechat_login_allowed(db, user_id, user_detail)
```

- [ ] **Step 4: Enforce SSO and preserve redirect behavior**

In `_sso_callback`, before `_sync_user_from_detail`, add:

```python
        try:
            await _ensure_wechat_login_allowed(db, user_id, user_detail)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                return RedirectResponse(url="/login?error=login_whitelist_denied")
            raise
```

In the broad `except Exception:` blocks, replace inline logging import usage with:

```python
        logger.exception("企微 SSO 登录失败")
```

and:

```python
        logger.exception("企微登录失败")
```

- [ ] **Step 5: Run targeted auth tests and commit**

Run:

```bash
cd backend && uv run pytest tests/test_auth_api.py tests/test_login_whitelist_service.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/app/api/routes/auth.py backend/tests/test_auth_api.py
git commit -m "feat: 登录时校验企业微信白名单"
```

---

### Task 5: Frontend API Types, Routing, and Sidebar Entry

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add frontend types**

In `frontend/src/types/index.ts`, add:

```ts
export interface LoginWhitelistUser {
  id: number;
  name: string;
}

export interface LoginWhitelistDepartment {
  id: number;
  department_id: number;
  name: string;
  path: string;
}

export interface LoginWhitelistDepartmentSearchItem {
  department_id: number;
  name: string;
  path: string;
}

export interface LoginWhitelistConfig {
  users: LoginWhitelistUser[];
  departments: LoginWhitelistDepartment[];
}
```

Change `ViewName` to include the new route:

```ts
export type ViewName = "new" | "chat" | "workspace" | "agents" | "skills" | "feedback" | "usage" | "loginWhitelist";
```

- [ ] **Step 2: Add API client methods and HTTP status metadata**

In `frontend/src/api/client.ts`, import the new types:

```ts
  LoginWhitelistConfig,
  LoginWhitelistDepartment,
  LoginWhitelistDepartmentSearchItem,
  LoginWhitelistUser,
```

Modify the non-OK error block in `request<T>`:

```ts
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    const err = new Error(`HTTP ${res.status}: ${text || res.statusText}`) as Error & {
      status?: number;
      responseText?: string;
    };
    err.status = res.status;
    err.responseText = text;
    throw err;
  }
```

Add admin methods inside `api`:

```ts
  loginWhitelist: () =>
    request<LoginWhitelistConfig>("/api/admin/login-whitelist"),

  createLoginWhitelistUser: (name: string) =>
    request<LoginWhitelistUser>("/api/admin/login-whitelist/users", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  deleteLoginWhitelistUser: (id: number) =>
    request<void>(`/api/admin/login-whitelist/users/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  searchLoginWhitelistDepartments: (q: string) =>
    request<LoginWhitelistDepartmentSearchItem[]>(
      `/api/admin/login-whitelist/departments/search?q=${encodeURIComponent(q)}`,
    ),

  createLoginWhitelistDepartment: (departmentId: number) =>
    request<LoginWhitelistDepartment>("/api/admin/login-whitelist/departments", {
      method: "POST",
      body: JSON.stringify({ department_id: departmentId }),
    }),

  deleteLoginWhitelistDepartment: (id: number) =>
    request<void>(
      `/api/admin/login-whitelist/departments/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    ),
```

- [ ] **Step 3: Add sidebar entry**

In `frontend/src/components/Sidebar.tsx`, inside the admin block, add:

```tsx
    items.push({ id: "loginWhitelist", label: "用户白名单", icon: I.Users, group: "管理" });
```

- [ ] **Step 4: Wire App routing to a temporary page**

In `frontend/src/App.tsx`, add a temporary placeholder component above `export default function App()`:

```tsx
function LoginWhitelistPagePlaceholder() {
  return (
    <div style={{ flex: 1, padding: "24px 28px", color: "var(--ink)" }}>
      用户白名单
    </div>
  );
}
```

Add breadcrumb branch before `usage`:

```ts
      : view === "loginWhitelist"
      ? ["管理", "用户白名单"]
```

Add render branch before the default `ChatWorkspace` branch:

```tsx
          ) : view === "loginWhitelist" && auth.me.role === "admin" ? (
            <LoginWhitelistPagePlaceholder />
```

This placeholder is removed in Task 6 when the real page is created.

- [ ] **Step 5: Run build and commit**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

Commit:

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/components/Sidebar.tsx frontend/src/App.tsx
git commit -m "feat: 增加用户白名单前端入口"
```

---

### Task 6: Frontend Whitelist Management Page

**Files:**
- Create: `frontend/src/pages/LoginWhitelistPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create the management page**

Create `frontend/src/pages/LoginWhitelistPage.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "@/api/client";
import type {
  LoginWhitelistConfig,
  LoginWhitelistDepartmentSearchItem,
} from "@/types";
import { I } from "@/icons";
import { Btn, Card, Input, Spinner, Tag, useToast } from "@/components/ui";

function formatError(error: unknown): string {
  return error instanceof Error ? error.message : "未知错误";
}

export default function LoginWhitelistPage() {
  const { showToast } = useToast();
  const [config, setConfig] = useState<LoginWhitelistConfig>({
    users: [],
    departments: [],
  });
  const [loading, setLoading] = useState(true);
  const [userName, setUserName] = useState("");
  const [savingUser, setSavingUser] = useState(false);
  const [departmentKeyword, setDepartmentKeyword] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<LoginWhitelistDepartmentSearchItem[]>([]);

  const totalCount = useMemo(
    () => config.users.length + config.departments.length,
    [config],
  );

  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      setConfig(await api.loginWhitelist());
    } catch (error) {
      showToast(`加载白名单失败：${formatError(error)}`, "error");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  const addUser = async () => {
    const name = userName.trim();
    if (!name) {
      showToast("请输入用户姓名", "error");
      return;
    }
    setSavingUser(true);
    try {
      const created = await api.createLoginWhitelistUser(name);
      setConfig((prev) => ({ ...prev, users: [...prev.users, created] }));
      setUserName("");
      showToast("用户白名单已添加", "success");
    } catch (error) {
      showToast(`添加用户失败：${formatError(error)}`, "error");
    } finally {
      setSavingUser(false);
    }
  };

  const deleteUser = async (id: number) => {
    try {
      await api.deleteLoginWhitelistUser(id);
      setConfig((prev) => ({
        ...prev,
        users: prev.users.filter((item) => item.id !== id),
      }));
      showToast("用户白名单已删除", "success");
    } catch (error) {
      showToast(`删除用户失败：${formatError(error)}`, "error");
    }
  };

  const searchDepartments = async () => {
    const keyword = departmentKeyword.trim();
    if (!keyword) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    try {
      setSearchResults(await api.searchLoginWhitelistDepartments(keyword));
    } catch (error) {
      showToast(`搜索部门失败：${formatError(error)}`, "error");
    } finally {
      setSearching(false);
    }
  };

  const addDepartment = async (departmentId: number) => {
    try {
      const created = await api.createLoginWhitelistDepartment(departmentId);
      setConfig((prev) => ({
        ...prev,
        departments: [...prev.departments, created],
      }));
      showToast("部门白名单已添加", "success");
    } catch (error) {
      showToast(`添加部门失败：${formatError(error)}`, "error");
    }
  };

  const deleteDepartment = async (id: number) => {
    try {
      await api.deleteLoginWhitelistDepartment(id);
      setConfig((prev) => ({
        ...prev,
        departments: prev.departments.filter((item) => item.id !== id),
      }));
      showToast("部门白名单已删除", "success");
    } catch (error) {
      showToast(`删除部门失败：${formatError(error)}`, "error");
    }
  };

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "24px 28px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 18 }}>
        <div>
          <h1 style={{ fontFamily: "var(--serif)", fontSize: 24, fontWeight: 500, marginBottom: 4, color: "var(--ink)" }}>
            用户白名单 <span style={{ fontSize: 14, color: "var(--ink-3)", fontFamily: "var(--sans)" }}>· 共 {totalCount} 项</span>
          </h1>
          <div style={{ fontSize: 13, color: "var(--ink-3)" }}>
            配置允许登录本系统的企业微信用户和部门。
          </div>
        </div>
        <Btn variant="secondary" icon={<I.Refresh size={14} />} onClick={() => void loadConfig()} disabled={loading}>
          刷新
        </Btn>
      </div>

      {loading ? (
        <StateBlock icon={<Spinner />} text="正在加载白名单" />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 360px), 1fr))", gap: 16 }}>
          <Card style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
            <SectionTitle title="用户姓名" count={config.users.length} />
            <div style={{ display: "flex", gap: 8 }}>
              <Input
                value={userName}
                onChange={(event) => setUserName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void addUser();
                }}
                placeholder="输入企业微信姓名"
              />
              <Btn onClick={() => void addUser()} disabled={savingUser}>添加</Btn>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {config.users.length === 0 ? (
                <EmptyText text="暂无用户姓名白名单" />
              ) : config.users.map((item) => (
                <ListRow key={item.id} title={item.name} onDelete={() => void deleteUser(item.id)} />
              ))}
            </div>
          </Card>

          <Card style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
            <SectionTitle title="部门" count={config.departments.length} />
            <div style={{ display: "flex", gap: 8 }}>
              <Input
                value={departmentKeyword}
                onChange={(event) => setDepartmentKeyword(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void searchDepartments();
                }}
                placeholder="搜索部门名称"
              />
              <Btn variant="secondary" onClick={() => void searchDepartments()} disabled={searching}>
                搜索
              </Btn>
            </div>
            {searchResults.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {searchResults.map((item) => (
                  <button
                    key={item.department_id}
                    type="button"
                    onClick={() => void addDepartment(item.department_id)}
                    className="focus-ring"
                    style={{
                      textAlign: "left",
                      border: "1px solid var(--line)",
                      background: "var(--bg)",
                      borderRadius: 8,
                      padding: "9px 10px",
                      cursor: "pointer",
                      color: "var(--ink-2)",
                    }}
                  >
                    {item.path}
                  </button>
                ))}
              </div>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {config.departments.length === 0 ? (
                <EmptyText text="暂无部门白名单" />
              ) : config.departments.map((item) => (
                <ListRow key={item.id} title={item.path} onDelete={() => void deleteDepartment(item.id)} />
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function SectionTitle({ title, count }: { title: string; count: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)" }}>{title}</div>
      <Tag tone="neutral">{count} 项</Tag>
    </div>
  );
}

function EmptyText({ text }: { text: string }) {
  return <div style={{ fontSize: 13, color: "var(--ink-3)", padding: "10px 0" }}>{text}</div>;
}

function ListRow({ title, onDelete }: { title: string; onDelete: () => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, border: "1px solid var(--line)", borderRadius: 8, padding: "9px 10px" }}>
      <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--ink-2)", fontSize: 13 }}>
        {title}
      </span>
      <Btn variant="ghost" size="sm" icon={<I.Trash size={14} />} onClick={onDelete} title="删除">
        删除
      </Btn>
    </div>
  );
}

function StateBlock({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <div style={{ minHeight: 260, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, color: "var(--ink-3)", fontSize: 13 }}>
      {icon}
      {text}
    </div>
  );
}
```

- [ ] **Step 2: Replace placeholder route with real page**

In `frontend/src/App.tsx`, import the page:

```tsx
import LoginWhitelistPage from "@/pages/LoginWhitelistPage";
```

Remove `LoginWhitelistPagePlaceholder`.

Replace the placeholder render branch with:

```tsx
          ) : view === "loginWhitelist" && auth.me.role === "admin" ? (
            <LoginWhitelistPage />
```

- [ ] **Step 3: Build and commit**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

Commit:

```bash
git add frontend/src/pages/LoginWhitelistPage.tsx frontend/src/App.tsx
git commit -m "feat: 增加用户白名单管理页面"
```

---

### Task 7: Frontend Login Denial Message

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx`

- [ ] **Step 1: Add whitelist denial constant and initial URL error handling**

In `frontend/src/pages/LoginPage.tsx`, add near the type definition:

```tsx
const LOGIN_WHITELIST_DENIED_MESSAGE = "当前账号未在登录白名单中，请联系管理员";
```

Inside `LoginPage`, initialize `errorMsg` from URL:

```tsx
  const initialError =
    new URLSearchParams(window.location.search).get("error") === "login_whitelist_denied"
      ? LOGIN_WHITELIST_DENIED_MESSAGE
      : "";
  const [status, setStatus] = useState<LoginStatus>(initialError ? "error" : "loading");
  const [errorMsg, setErrorMsg] = useState(initialError);
```

Replace the existing `status` and `errorMsg` state declarations with the above.

- [ ] **Step 2: Handle QR-code login 403**

In `doLogin`, replace `catch { ... }` with:

```tsx
    } catch (error) {
      const statusCode = (error as { status?: number }).status;
      setStatus("error");
      setErrorMsg(
        statusCode === 403
          ? LOGIN_WHITELIST_DENIED_MESSAGE
          : "登录失败，请刷新二维码重试",
      );
    }
```

- [ ] **Step 3: Do not auto-refresh QR when URL already has denial error**

In the first `useEffect`, before `refreshQrCode();`, add:

```tsx
    if (initialError) return;
```

The effect becomes:

```tsx
  useEffect(() => {
    abortRef.current = false;
    if (initialError) return;
    refreshQrCode();
    return () => {
      abortRef.current = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
```

- [ ] **Step 4: Build and commit**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

Commit:

```bash
git add frontend/src/pages/LoginPage.tsx
git commit -m "feat: 登录页展示白名单拒绝提示"
```

---

### Task 8: Final Verification

**Files:**
- Verify all task-related files.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
cd backend && uv run pytest tests/test_login_whitelist_service.py tests/test_admin_login_whitelist_api.py tests/test_auth_api.py tests/test_departments_sync.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Inspect git status**

Run:

```bash
git status --short
```

Expected: only intentionally modified task files are present, plus the pre-existing untracked `design/动态多智能体编排系统设计文档-v2.md` remains uncommitted.

- [ ] **Step 4: Commit any remaining task-related changes**

If final verification changed generated build metadata or formatting in task-related files, stage only relevant files:

```bash
git add backend/app backend/tests frontend/src
git commit -m "chore: 完成用户白名单验证"
```

If there are no remaining task-related changes, do not create an empty commit.

---

## Self-Review Notes

- Spec coverage: the plan covers admin sidebar entry, user-name CRUD, department search/CRUD, exact name matching, department descendant matching, empty-whitelist allow behavior, local-account exemption by limiting checks to enterprise WeChat login paths, SSO/QR denial handling, and frontend denial messages.
- Placeholder scan: no task contains open-ended placeholders.
- Type consistency: backend response fields use `department_id`, `name`, and `path` consistently with frontend types and API client methods.
