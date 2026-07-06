# Team Space Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the team space service layer with member roles, space-level locks, shared team sessions, workspace-bound Claude cwd, and workspace-scoped file/task APIs.

**Architecture:** Add `TeamSpace`/`TeamSpaceMember` plus a `WorkspaceScope` resolver that centralizes personal/team workspace root, visibility, write permission, lock state, and read-only reason. Existing workspace file services stay reusable; routes, upload/conversion tasks, sessions, and Claude runner route through scope. Frontend work is intentionally split into `docs/superpowers/plans/2026-06-04-team-space-frontend.md`.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic, pytest/httpx, Claude Agent SDK hooks.

---

## File Structure

- Create `backend/app/models/team_space.py`: `TeamSpace` and `TeamSpaceMember` ORM models.
- Modify `backend/app/models/__init__.py`: export team space models.
- Modify `backend/app/models/session.py`: add workspace binding fields and creator/message attribution support used by sessions.
- Modify `backend/app/models/upload_task.py`: add workspace scope fields.
- Modify `backend/app/models/conversion_task.py`: add workspace scope fields.
- Modify `backend/app/db/migrations.py`: add team tables and compatible column/index migrations.
- Create `backend/app/schemas/team_spaces.py`: team space, member, lock, transfer schemas.
- Modify `backend/app/schemas/sessions.py`: add workspace fields, creator fields, and create request fields.
- Modify `backend/app/schemas/upload_tasks.py`, `backend/app/schemas/conversion_tasks.py`, `backend/app/schemas/workspace_tasks.py`: expose workspace scope fields.
- Modify `backend/app/schemas/__init__.py`: export new schemas.
- Create `backend/app/modules/team_spaces/service.py`: team space CRUD, membership, owner transfer, lock/unlock.
- Create `backend/app/modules/workspace/scope.py`: personal/team workspace scope resolver and permission guards.
- Modify `backend/app/api/routes/workspace.py`: keep personal workspace routes compatible while team routes call the same workspace service functions.
- Create `backend/app/api/routes/team_spaces.py`: team space and team workspace routes.
- Modify `backend/app/api/routes/sessions.py`: workspace-scoped list/create/access/delete/chat/history/running behavior.
- Modify `backend/app/modules/sessions/service.py`: personal/team session listing and access rules.
- Modify `backend/app/modules/sessions/streaming.py`: run with `WorkspaceScope.root`, actor user, and write permission.
- Modify `backend/app/integrations/claude/guard.py`: deny write tools when `can_write=False`.
- Modify `backend/app/integrations/claude/runner.py`: accept workspace root/scope options already prepared by streaming.
- Modify `backend/app/api/routes/upload_tasks.py`, `backend/app/modules/uploads/tasks.py`: workspace-scoped upload task creation and upload.
- Modify `backend/app/api/routes/conversion_tasks.py`, `backend/app/modules/conversions/service.py`: workspace-scoped conversion retry/list/path update.
- Modify `backend/app/api/routes/workspace_tasks.py`, `backend/app/modules/workspace/tasks.py`: workspace-scoped unified task list.
- Modify `backend/app/api/router.py`: register team space routes.
- Modify `backend/tests/conftest.py`: reload new modules/models/routes.
- Create `backend/tests/test_team_spaces_api.py`: team space CRUD, membership, owner transfer, lock tests.
- Create `backend/tests/test_team_workspace_api.py`: team file API visibility/write tests.
- Create `backend/tests/test_team_sessions_api.py`: shared team session list/history/access tests.
- Create `backend/tests/test_team_workspace_agent_hooks.py`: Claude hook write denial tests.
- Modify `backend/tests/test_workspace_upload_tasks.py`, `backend/tests/test_workspace_tasks.py`, `backend/tests/test_conversion_tasks_api.py`: workspace scope coverage.

---

### Task 1: Team Space Models, Schemas, and Migrations

**Files:**
- Create: `backend/app/models/team_space.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/session.py`
- Modify: `backend/app/models/upload_task.py`
- Modify: `backend/app/models/conversion_task.py`
- Modify: `backend/app/db/migrations.py`
- Create: `backend/app/schemas/team_spaces.py`
- Modify: `backend/app/schemas/sessions.py`
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_team_spaces_api.py`

- [ ] **Step 1: Write failing model/schema tests**

Create `backend/tests/test_team_spaces_api.py` with the first persistence and schema assertions:

```python
import pytest
from sqlalchemy import select

from app.models import TeamSpace, TeamSpaceMember


@pytest.mark.asyncio
async def test_team_space_models_create_owner_member(db_session, test_user):
    space = TeamSpace(
        name="客户试点资料",
        description="试点材料",
        owner_user_id=test_user.id,
        created_by_user_id=test_user.id,
    )
    db_session.add(space)
    await db_session.flush()
    db_session.add(
        TeamSpaceMember(
            space_id=space.id,
            user_id=test_user.id,
            role="editor",
            added_by_user_id=test_user.id,
        )
    )
    await db_session.commit()

    saved = (await db_session.execute(select(TeamSpace))).scalar_one()
    member = (await db_session.execute(select(TeamSpaceMember))).scalar_one()
    assert saved.name == "客户试点资料"
    assert saved.owner_user_id == test_user.id
    assert member.role == "editor"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend && pytest tests/test_team_spaces_api.py::test_team_space_models_create_owner_member -v
```

Expected: FAIL with `ImportError` or `NameError` for `TeamSpace`.

- [ ] **Step 3: Add `TeamSpace` and `TeamSpaceMember` models**

Create `backend/app/models/team_space.py`:

```python
"""团队空间 ORM 模型。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TeamSpace(Base):
    """团队共享工作空间。"""

    __tablename__ = "team_spaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    lock_holder_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    lock_acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    members: Mapped[list["TeamSpaceMember"]] = relationship(cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_team_spaces_owner", "owner_user_id"),
        Index("idx_team_spaces_updated", "updated_at"),
    )


class TeamSpaceMember(Base):
    """团队空间成员及权限。"""

    __tablename__ = "team_space_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("team_spaces.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="reader")
    added_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("space_id", "user_id", name="uq_team_space_members_space_user"),
        Index("idx_team_space_members_user", "user_id"),
        Index("idx_team_space_members_space", "space_id"),
    )
```

Modify `backend/app/models/__init__.py`:

```python
from app.models.team_space import TeamSpace, TeamSpaceMember
```

Keep all existing imports in the file.

- [ ] **Step 4: Add session and task workspace fields**

Modify `backend/app/models/session.py` by adding columns to `ChatSession`:

```python
    workspace_kind: Mapped[str] = mapped_column(String, nullable=False, default="personal")
    team_space_id: Mapped[int | None] = mapped_column(
        ForeignKey("team_spaces.id", ondelete="CASCADE"), nullable=True
    )
```

Update `__table_args__`:

```python
    __table_args__ = (
        Index("idx_sessions_user", "user_id", "updated_at"),
        Index("idx_sessions_team_space", "team_space_id", "updated_at"),
        Index("idx_sessions_workspace", "workspace_kind", "team_space_id", "updated_at"),
    )
```

Modify `backend/app/models/upload_task.py` and `backend/app/models/conversion_task.py` by adding:

```python
    workspace_kind: Mapped[str] = mapped_column(String, nullable=False, default="personal")
    team_space_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

Add indexes:

```python
Index("idx_upload_tasks_workspace_created", "workspace_kind", "team_space_id", "created_at")
Index("idx_conversion_tasks_workspace_created", "workspace_kind", "team_space_id", "created_at")
```

- [ ] **Step 5: Add migration block**

Modify `backend/app/db/migrations.py` to create `team_spaces`, `team_space_members`, and add columns if missing:

```python
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS team_spaces ("
            "id SERIAL PRIMARY KEY, "
            "name VARCHAR NOT NULL, "
            "description TEXT NULL, "
            "owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT, "
            "created_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT, "
            "lock_holder_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL, "
            "lock_acquired_at TIMESTAMP WITH TIME ZONE NULL, "
            "lock_note TEXT NULL, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS team_space_members ("
            "id SERIAL PRIMARY KEY, "
            "space_id INTEGER NOT NULL REFERENCES team_spaces(id) ON DELETE CASCADE, "
            "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
            "role VARCHAR NOT NULL DEFAULT 'reader', "
            "added_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "CONSTRAINT uq_team_space_members_space_user UNIQUE(space_id, user_id)"
            ")"
        ))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_team_space_members_user ON team_space_members(user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_team_space_members_space ON team_space_members(space_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_team_spaces_owner ON team_spaces(owner_user_id)"))
```

Add compatible column creation for `chat_sessions`, `upload_tasks`, and `conversion_tasks` using the migration file’s existing “check column then add” pattern:

```sql
ALTER TABLE chat_sessions ADD COLUMN workspace_kind VARCHAR NOT NULL DEFAULT 'personal'
ALTER TABLE chat_sessions ADD COLUMN team_space_id INTEGER NULL
ALTER TABLE upload_tasks ADD COLUMN workspace_kind VARCHAR NOT NULL DEFAULT 'personal'
ALTER TABLE upload_tasks ADD COLUMN team_space_id INTEGER NULL
ALTER TABLE conversion_tasks ADD COLUMN workspace_kind VARCHAR NOT NULL DEFAULT 'personal'
ALTER TABLE conversion_tasks ADD COLUMN team_space_id INTEGER NULL
```

- [ ] **Step 6: Add schemas**

Create `backend/app/schemas/team_spaces.py`:

```python
"""团队空间 API schema。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


TeamMemberRole = Literal["reader", "editor"]


class TeamSpaceCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None


class TeamSpaceUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None


class TeamSpaceMemberAddIn(BaseModel):
    user_id: int
    role: TeamMemberRole = "reader"


class TeamSpaceMemberUpdateIn(BaseModel):
    role: TeamMemberRole


class TeamSpaceTransferOwnerIn(BaseModel):
    user_id: int


class TeamSpaceLockIn(BaseModel):
    note: str | None = None


class TeamSpaceOut(BaseModel):
    id: int
    name: str
    description: str | None
    owner_user_id: int
    owner_name: str
    member_count: int
    locked_by_user_id: int | None
    locked_by_name: str | None
    lock_acquired_at: datetime | None
    lock_note: str | None
    member_role: TeamMemberRole
    can_write: bool
    is_owner: bool
    readonly_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeamSpaceMemberOut(BaseModel):
    id: int
    user_id: int
    username: str
    display_name: str | None
    role: TeamMemberRole
    is_owner: bool
    added_by_user_id: int
    created_at: datetime
    updated_at: datetime
```

Modify `backend/app/schemas/sessions.py` to extend `CreateSessionRequest` and `SessionOut`:

```python
workspace_kind: Literal["personal", "team"] = "personal"
team_space_id: int | None = None
created_by_user_id: int | None = None
created_by_name: str | None = None
team_space_name: str | None = None
workspace_member_role: Literal["reader", "editor"] | None = None
workspace_can_write: bool = True
workspace_readonly_reason: str | None = None
```

- [ ] **Step 7: Run model/schema tests**

Run:

```bash
cd backend && pytest tests/test_team_spaces_api.py::test_team_space_models_create_owner_member -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models backend/app/schemas backend/app/db/migrations.py backend/tests/test_team_spaces_api.py
git commit -m "feat:添加团队空间数据模型"
```

---

### Task 2: Team Space Service and Management API

**Files:**
- Create: `backend/app/modules/team_spaces/service.py`
- Create: `backend/app/api/routes/team_spaces.py`
- Modify: `backend/app/api/router.py`
- Test: `backend/tests/test_team_spaces_api.py`

- [ ] **Step 1: Add failing API tests**

Append to `backend/tests/test_team_spaces_api.py`:

```python
@pytest.mark.asyncio
async def test_create_space_auto_adds_owner_editor(logged_in_client):
    r = await logged_in_client.post("/api/team-spaces", json={"name": "客户试点资料", "description": "试点"})
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "客户试点资料"
    assert data["member_role"] == "editor"
    assert data["is_owner"] is True
    assert data["can_write"] is True


@pytest.mark.asyncio
async def test_reader_cannot_lock_team_space(logged_in_client, other_logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "共享材料"})
    space_id = created.json()["id"]
    me = (await other_logged_in_client.get("/api/auth/me")).json()
    add = await logged_in_client.post(
        f"/api/team-spaces/{space_id}/members",
        json={"user_id": me["id"], "role": "reader"},
    )
    assert add.status_code == 200

    locked = await other_logged_in_client.post(f"/api/team-spaces/{space_id}/lock", json={"note": "整理"})

    assert locked.status_code == 403
    assert "只读成员" in locked.json()["detail"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend && pytest tests/test_team_spaces_api.py -v
```

Expected: FAIL with 404 for `/api/team-spaces`.

- [ ] **Step 3: Implement team space service**

Create `backend/app/modules/team_spaces/service.py`:

```python
"""团队空间业务逻辑。"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import TeamSpace, TeamSpaceMember, User


def team_workspace(space_id: int) -> Path:
    root = get_settings().workspaces_dir.parent / "team_workspaces" / str(space_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / ".markdown").mkdir(parents=True, exist_ok=True)
    return root


async def get_membership(db: AsyncSession, user: User, space_id: int) -> TeamSpaceMember | None:
    return (
        await db.execute(
            select(TeamSpaceMember).where(
                TeamSpaceMember.space_id == space_id,
                TeamSpaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()


async def require_member(db: AsyncSession, user: User, space_id: int) -> tuple[TeamSpace, TeamSpaceMember]:
    space = await db.get(TeamSpace, space_id)
    member = await get_membership(db, user, space_id)
    if space is None or member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="空间不存在")
    return space, member


def can_write(space: TeamSpace, member: TeamSpaceMember) -> tuple[bool, str | None]:
    if member.role != "editor":
        return False, "只读成员不能编辑团队空间"
    if space.lock_holder_user_id is None:
        return True, None
    if space.lock_holder_user_id == member.user_id:
        return True, None
    return False, "当前空间已被其他成员锁定"


async def create_space(db: AsyncSession, user: User, name: str, description: str | None) -> TeamSpace:
    space = TeamSpace(name=name, description=description, owner_user_id=user.id, created_by_user_id=user.id)
    db.add(space)
    await db.flush()
    db.add(TeamSpaceMember(space_id=space.id, user_id=user.id, role="editor", added_by_user_id=user.id))
    await db.commit()
    team_workspace(space.id)
    await db.refresh(space)
    return space


async def add_member(db: AsyncSession, owner: User, space_id: int, user_id: int, role: str) -> TeamSpaceMember:
    space, owner_member = await require_member(db, owner, space_id)
    if space.owner_user_id != owner.id:
        raise HTTPException(status_code=403, detail="只有空间所有者可以管理成员")
    member = TeamSpaceMember(space_id=space_id, user_id=user_id, role=role, added_by_user_id=owner.id)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def lock_space(db: AsyncSession, user: User, space_id: int, note: str | None) -> TeamSpace:
    space, member = await require_member(db, user, space_id)
    if member.role != "editor":
        raise HTTPException(status_code=403, detail="只读成员不能锁定团队空间")
    if space.lock_holder_user_id not in (None, user.id):
        raise HTTPException(status_code=409, detail="当前空间已被锁定")
    space.lock_holder_user_id = user.id
    space.lock_acquired_at = datetime.now(timezone.utc)
    space.lock_note = note
    await db.commit()
    await db.refresh(space)
    return space


async def unlock_space(db: AsyncSession, user: User, space_id: int) -> TeamSpace:
    space, _member = await require_member(db, user, space_id)
    if space.lock_holder_user_id not in (None, user.id):
        raise HTTPException(status_code=403, detail="只有持锁人可以解除锁定")
    space.lock_holder_user_id = None
    space.lock_acquired_at = None
    space.lock_note = None
    await db.commit()
    await db.refresh(space)
    return space
```

- [ ] **Step 4: Implement routes**

Create `backend/app/api/routes/team_spaces.py` with management endpoints:

```python
"""团队空间 API。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.db.session import get_db
from app.models import User
from app.modules.team_spaces import service
from app.schemas.team_spaces import (
    TeamSpaceCreateIn,
    TeamSpaceLockIn,
    TeamSpaceMemberAddIn,
    TeamSpaceOut,
)

router = APIRouter(prefix="/api/team-spaces")


def _space_out(space, member, *, member_count: int = 1) -> TeamSpaceOut:
    can_write, readonly_reason = service.can_write(space, member)
    return TeamSpaceOut.model_validate({
        "id": space.id,
        "name": space.name,
        "description": space.description,
        "owner_user_id": space.owner_user_id,
        "owner_name": "",
        "member_count": member_count,
        "locked_by_user_id": space.lock_holder_user_id,
        "locked_by_name": None,
        "lock_acquired_at": space.lock_acquired_at,
        "lock_note": space.lock_note,
        "member_role": member.role,
        "can_write": can_write,
        "is_owner": space.owner_user_id == member.user_id,
        "readonly_reason": readonly_reason,
        "created_at": space.created_at,
        "updated_at": space.updated_at,
    })


@router.post("", response_model=TeamSpaceOut)
async def create_team_space(payload: TeamSpaceCreateIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    space = await service.create_space(db, user, payload.name, payload.description)
    _space, member = await service.require_member(db, user, space.id)
    return _space_out(space, member)


@router.post("/{space_id}/members")
async def add_team_space_member(space_id: int, payload: TeamSpaceMemberAddIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    member = await service.add_member(db, user, space_id, payload.user_id, payload.role)
    return {"id": member.id, "user_id": member.user_id, "role": member.role}


@router.post("/{space_id}/lock", response_model=TeamSpaceOut)
async def lock_team_space(space_id: int, payload: TeamSpaceLockIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    space = await service.lock_space(db, user, space_id, payload.note)
    _space, member = await service.require_member(db, user, space_id)
    return _space_out(space, member)


@router.delete("/{space_id}/lock", response_model=TeamSpaceOut)
async def unlock_team_space(space_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    space = await service.unlock_space(db, user, space_id)
    _space, member = await service.require_member(db, user, space_id)
    return _space_out(space, member)
```

Modify `backend/app/api/router.py`:

```python
from app.api.routes import team_spaces
api_router.include_router(team_spaces.router)
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd backend && pytest tests/test_team_spaces_api.py -v
```

Expected: PASS for current tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/team_spaces backend/app/api/routes/team_spaces.py backend/app/api/router.py backend/tests/test_team_spaces_api.py
git commit -m "feat:添加团队空间管理接口"
```

---

### Task 3: WorkspaceScope and Team Workspace File APIs

**Files:**
- Create: `backend/app/modules/workspace/scope.py`
- Modify: `backend/app/api/routes/team_spaces.py`
- Modify: `backend/app/api/routes/workspace.py`
- Test: `backend/tests/test_team_workspace_api.py`

- [ ] **Step 1: Write failing team workspace API tests**

Create `backend/tests/test_team_workspace_api.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_team_member_can_read_tree(logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "资料"})
    space_id = created.json()["id"]

    r = await logged_in_client.get(f"/api/team-spaces/{space_id}/workspace/tree")

    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_reader_cannot_create_file(logged_in_client, other_logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "资料"})
    space_id = created.json()["id"]
    me = (await other_logged_in_client.get("/api/auth/me")).json()
    await logged_in_client.post(f"/api/team-spaces/{space_id}/members", json={"user_id": me["id"], "role": "reader"})

    r = await other_logged_in_client.post(
        f"/api/team-spaces/{space_id}/workspace/file",
        json={"path": "README.md", "kind": "file", "content": "hello"},
    )

    assert r.status_code == 403
    assert "只读成员" in r.json()["detail"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend && pytest tests/test_team_workspace_api.py -v
```

Expected: FAIL with missing workspace routes.

- [ ] **Step 3: Implement `WorkspaceScope`**

Create `backend/app/modules/workspace/scope.py`:

```python
"""工作空间上下文解析。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import user_workspace
from app.models import User
from app.modules.team_spaces.service import require_member, team_workspace, can_write


@dataclass(frozen=True)
class WorkspaceScope:
    kind: Literal["personal", "team"]
    key: str
    root: Path
    display_name: str
    can_read: bool
    can_write: bool
    member_role: Literal["reader", "editor"] | None = None
    is_owner: bool = False
    locked_by_user_id: int | None = None
    readonly_reason: str | None = None


async def personal_workspace_scope(user: User) -> WorkspaceScope:
    return WorkspaceScope(
        kind="personal",
        key=user.username,
        root=user_workspace(user.username),
        display_name="个人空间",
        can_read=True,
        can_write=True,
    )


async def team_workspace_scope(db: AsyncSession, user: User, space_id: int) -> WorkspaceScope:
    space, member = await require_member(db, user, space_id)
    write, reason = can_write(space, member)
    return WorkspaceScope(
        kind="team",
        key=str(space.id),
        root=team_workspace(space.id),
        display_name=space.name,
        can_read=True,
        can_write=write,
        member_role=member.role,
        is_owner=space.owner_user_id == user.id,
        locked_by_user_id=space.lock_holder_user_id,
        readonly_reason=reason,
    )


def require_workspace_write(scope: WorkspaceScope) -> None:
    if not scope.can_write:
        raise HTTPException(status_code=403, detail=scope.readonly_reason or "当前工作空间不可写")
```

- [ ] **Step 4: Add team workspace route helpers**

Modify `backend/app/api/routes/team_spaces.py` and add workspace endpoints:

```python
from fastapi import Query
from app.modules.workspace.scope import require_workspace_write, team_workspace_scope
from app.modules.workspace.service import get_workspace_tree, preview_workspace_item, download_workspace_item
from app.modules.workspace.text_ops import create_workspace_item, save_content_file, rename_workspace_item, move_workspace_item
from app.modules.workspace.service import delete_workspace_item
from app.schemas import WorkspaceCreateIn, WorkspaceMoveIn, WorkspaceRenameIn, WorkspaceTextSaveIn


@router.get("/{space_id}/workspace/tree")
async def team_workspace_tree(space_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    scope = await team_workspace_scope(db, user, space_id)
    return get_workspace_tree(scope.root, {})


@router.post("/{space_id}/workspace/file")
async def team_create_workspace_item(space_id: int, payload: WorkspaceCreateIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    return create_workspace_item(scope.root, payload.path, payload.kind, payload.content)


@router.put("/{space_id}/workspace/content")
async def team_save_workspace_content(space_id: int, payload: WorkspaceTextSaveIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    return save_content_file(scope.root, payload.path, payload.content)


@router.get("/{space_id}/workspace/preview")
async def team_preview_workspace_item(space_id: int, path: str = Query(...), user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    scope = await team_workspace_scope(db, user, space_id)
    return preview_workspace_item(scope.root, path)
```

Add the remaining team workspace endpoints explicitly:

```python
@router.patch("/{space_id}/workspace/file/rename")
async def team_rename_workspace_item(space_id: int, payload: WorkspaceRenameIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    return rename_workspace_item(scope.root, payload.path, payload.new_name)


@router.patch("/{space_id}/workspace/file/move")
async def team_move_workspace_item(space_id: int, payload: WorkspaceMoveIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    return move_workspace_item(scope.root, payload.path, payload.target_dir)


@router.delete("/{space_id}/workspace/file", status_code=204)
async def team_delete_workspace_item(space_id: int, path: str = Query(...), user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    delete_workspace_item(scope.root, path)


@router.get("/{space_id}/workspace/download")
async def team_download_workspace_item(space_id: int, path: str = Query(...), user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    scope = await team_workspace_scope(db, user, space_id)
    return download_workspace_item(scope.root, path)
```

- [ ] **Step 5: Run team workspace API tests**

Run:

```bash
cd backend && pytest tests/test_team_workspace_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/workspace/scope.py backend/app/api/routes/team_spaces.py backend/tests/test_team_workspace_api.py
git commit -m "feat:支持团队空间文件接口"
```

---

### Task 4: Workspace-Scoped Sessions and Shared Team Session Access

**Files:**
- Modify: `backend/app/modules/sessions/service.py`
- Modify: `backend/app/api/routes/sessions.py`
- Modify: `backend/app/schemas/sessions.py`
- Test: `backend/tests/test_team_sessions_api.py`

- [ ] **Step 1: Write failing shared session tests**

Create `backend/tests/test_team_sessions_api.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_team_session_visible_to_team_member(logged_in_client, other_logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "团队资料"})
    space_id = created.json()["id"]
    other = (await other_logged_in_client.get("/api/auth/me")).json()
    await logged_in_client.post(f"/api/team-spaces/{space_id}/members", json={"user_id": other["id"], "role": "editor"})

    session = await logged_in_client.post(
        "/api/sessions",
        json={"agent_id": None, "workspace_kind": "team", "team_space_id": space_id},
    )
    assert session.status_code == 200

    listed = await other_logged_in_client.get(f"/api/sessions?workspace_kind=team&team_space_id={space_id}")

    assert listed.status_code == 200
    assert any(item["id"] == session.json()["id"] for item in listed.json())
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd backend && pytest tests/test_team_sessions_api.py::test_team_session_visible_to_team_member -v
```

Expected: FAIL because session routes ignore workspace query.

- [ ] **Step 3: Update session service access rules**

Modify `backend/app/modules/sessions/service.py`:

```python
from sqlalchemy import or_
from app.models import TeamSpaceMember


async def get_accessible_session(db: AsyncSession, session_id: str, user: User) -> ChatSession | None:
    cs = await db.get(ChatSession, session_id)
    if cs is None:
        return None
    if cs.workspace_kind == "personal":
        return cs if cs.user_id == user.id else None
    if cs.team_space_id is None:
        return None
    member = (
        await db.execute(
            select(TeamSpaceMember).where(
                TeamSpaceMember.space_id == cs.team_space_id,
                TeamSpaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    return cs if member else None


async def list_sessions(db: AsyncSession, user: User, workspace_kind: str = "personal", team_space_id: int | None = None):
    stmt = select(ChatSession, Agent.name.label("agent_name")).outerjoin(Agent, ChatSession.agent_id == Agent.id)
    if workspace_kind == "team":
        stmt = stmt.join(TeamSpaceMember, TeamSpaceMember.space_id == ChatSession.team_space_id).where(
            ChatSession.workspace_kind == "team",
            ChatSession.team_space_id == team_space_id,
            TeamSpaceMember.user_id == user.id,
        )
    else:
        stmt = stmt.where(ChatSession.user_id == user.id, ChatSession.workspace_kind == "personal")
    return (await db.execute(stmt.order_by(desc(ChatSession.updated_at)))).all()
```

Modify `create_session()` signature:

```python
async def create_session(
    db: AsyncSession,
    user: User,
    title: str | None,
    agent_id: int | None,
    workspace_kind: str = "personal",
    team_space_id: int | None = None,
) -> ChatSession:
    cs = ChatSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        agent_id=agent_id,
        title=title or "新会话",
        workspace_kind=workspace_kind,
        team_space_id=team_space_id,
    )
```

- [ ] **Step 4: Update routes**

Modify `backend/app/api/routes/sessions.py`:

```python
@router.get("", response_model=list[SessionOut])
async def list_sessions(
    workspace_kind: str = Query("personal"),
    team_space_id: int | None = Query(None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionOut]:
    rows = await list_sessions_svc(db, user, workspace_kind, team_space_id)
```

In `create_session()`, validate team membership:

```python
if payload.workspace_kind == "team":
    if payload.team_space_id is None:
        raise HTTPException(status_code=400, detail="团队空间会话必须指定团队空间")
    await team_workspace_scope(db, user, payload.team_space_id)
cs = await create_session_svc(db, user, payload.title, payload.agent_id, payload.workspace_kind, payload.team_space_id)
```

Replace all `get_owned_session_svc()` calls in routes with `get_accessible_session_svc()`. For rename/delete, add:

```python
if cs.workspace_kind == "team" and cs.user_id != user.id:
    scope = await team_workspace_scope(db, user, cs.team_space_id)
    if not scope.is_owner:
        raise HTTPException(status_code=403, detail="只有会话创建者或空间所有者可以操作会话")
```

- [ ] **Step 5: Run session tests**

Run:

```bash
cd backend && pytest tests/test_team_sessions_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/sessions/service.py backend/app/api/routes/sessions.py backend/app/schemas/sessions.py backend/tests/test_team_sessions_api.py
git commit -m "feat:支持团队空间共享会话"
```

---

### Task 5: Claude Runner Workspace Scope and Write Guards

**Files:**
- Modify: `backend/app/modules/sessions/streaming.py`
- Modify: `backend/app/integrations/claude/guard.py`
- Modify: `backend/app/integrations/claude/runner.py`
- Test: `backend/tests/test_team_workspace_agent_hooks.py`

- [ ] **Step 1: Write failing hook tests**

Create `backend/tests/test_team_workspace_agent_hooks.py`:

```python
import pytest

from app.integrations.claude.guard import build_pre_tool_use_hooks


@pytest.mark.asyncio
async def test_write_tool_denied_when_workspace_readonly(tmp_path):
    hooks = build_pre_tool_use_hooks(tmp_path, can_write=False, readonly_reason="空间已锁定")
    guard = hooks[0].hooks[0]

    result = await guard(
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "a.md")}},
        "toolu_1",
        {},
    )

    output = result["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "空间已锁定" in output["permissionDecisionReason"]
```

- [ ] **Step 2: Run hook test to verify failure**

Run:

```bash
cd backend && pytest tests/test_team_workspace_agent_hooks.py -v
```

Expected: FAIL because `build_pre_tool_use_hooks()` does not accept `can_write`.

- [ ] **Step 3: Update Claude guard**

Modify `backend/app/integrations/claude/guard.py`:

```python
def build_pre_tool_use_hooks(
    user_workspace: Path,
    *,
    can_write: bool = True,
    readonly_reason: str | None = None,
    agent_workdir: Path | None = None,
) -> list[HookMatcher]:
    hooks = [
        HookMatcher(matcher="Bash", hooks=[_bash_safety_hook(user_workspace, can_write=can_write, readonly_reason=readonly_reason)]),
    ]
    if not can_write:
        hooks.insert(
            0,
            HookMatcher(
                matcher="Write|Edit|MultiEdit|NotebookEdit",
                hooks=[_readonly_tool_hook(readonly_reason or "当前工作空间不可写")],
            ),
        )
    return hooks


def _readonly_tool_hook(reason: str):
    async def guard(input_data, _tool_use_id, _context):
        return _deny(reason)
    return guard
```

Update `_bash_safety_hook()` signature and body:

```python
def _bash_safety_hook(user_workspace: Path, *, can_write: bool = True, readonly_reason: str | None = None):
    async def guard(input_data, _tool_use_id, _context):
        if input_data.get("tool_name") != "Bash":
            return _allow()
        command = input_data.get("tool_input", {}).get("command", "")
        if not can_write and isinstance(command, str) and _bash_command_may_write(command):
            return _deny(readonly_reason or "当前工作空间不可写")
        if isinstance(command, str) and _bash_command_is_allowed(command):
            return _allow()
        return _deny(f"Bash 禁止执行黑名单命令({user_workspace})。")
    return guard
```

Add:

```python
_BASH_WRITE_COMMANDS = {"rm", "mv", "cp", "mkdir", "touch", "tee", "cat", "sed", "python", "python3", "node"}


def _bash_command_may_write(command: str) -> bool:
    if ">" in command or ">>" in command:
        return True
    tokens = _split_shell_tokens(command)
    if tokens is None:
        return True
    for segment in _split_shell_segments(tokens):
        name = _command_name(segment)
        if name in {"rm", "mv", "cp", "mkdir", "touch", "tee"}:
            return True
    return False
```

- [ ] **Step 4: Update streaming to resolve scope**

Modify `backend/app/modules/sessions/streaming.py`:

```python
from app.modules.workspace.scope import personal_workspace_scope, team_workspace_scope


async def _scope_for_session(db, user, cs):
    if cs.workspace_kind == "team":
        return await team_workspace_scope(db, user, cs.team_space_id)
    return await personal_workspace_scope(user)
```

Inside `stream_session_chat()` replace:

```python
ws = user_workspace(user.username)
```

with:

```python
async with async_session() as s:
    fresh = await s.get(ChatSession, cs.id)
    scope = await _scope_for_session(s, user, fresh or cs)
ws = scope.root
```

Pass `scope.can_write` and `scope.readonly_reason` into the runner call where `stream_chat()` is invoked.

- [ ] **Step 5: Update runner signature**

Modify `backend/app/integrations/claude/runner.py` so its hook creation receives `can_write` and `readonly_reason`:

```python
hooks = build_pre_tool_use_hooks(
    workspace,
    can_write=can_write,
    readonly_reason=readonly_reason,
    agent_workdir=agent_workdir,
)
```

Keep `scope.root` in sandbox `allowWrite` for both writable and readonly scopes so the SDK still reaches `PreToolUse`; rely on the hook to make the final business decision. Add a short code comment beside the sandbox setting: `# 业务写权限由 PreToolUse hook 按 WorkspaceScope.can_write 裁决。`

- [ ] **Step 6: Run hook and session tests**

Run:

```bash
cd backend && pytest tests/test_team_workspace_agent_hooks.py tests/test_team_sessions_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/integrations/claude backend/app/modules/sessions/streaming.py backend/tests/test_team_workspace_agent_hooks.py
git commit -m "feat:按团队空间权限限制agent写入"
```

---

### Task 6: Workspace-Scoped Upload, Conversion, and Task Lists

**Files:**
- Modify: `backend/app/modules/uploads/tasks.py`
- Modify: `backend/app/api/routes/upload_tasks.py`
- Modify: `backend/app/modules/conversions/service.py`
- Modify: `backend/app/api/routes/conversion_tasks.py`
- Modify: `backend/app/modules/workspace/tasks.py`
- Modify: `backend/app/api/routes/workspace_tasks.py`
- Test: `backend/tests/test_workspace_upload_tasks.py`
- Test: `backend/tests/test_workspace_tasks.py`
- Test: `backend/tests/test_conversion_tasks_api.py`

- [ ] **Step 1: Add failing scoped task tests**

Append to `backend/tests/test_workspace_tasks.py`:

```python
@pytest.mark.asyncio
async def test_team_workspace_tasks_are_isolated(logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "任务空间"})
    space_id = created.json()["id"]
    payload = {"target_dir": "", "items": [{"filename": "a.txt", "relative_path": "a.txt", "size": 1}]}

    personal = await logged_in_client.post("/api/upload-tasks", json=payload)
    team = await logged_in_client.post(f"/api/team-spaces/{space_id}/upload-tasks", json=payload)

    assert personal.status_code == 200
    assert team.status_code == 200
    personal_tasks = await logged_in_client.get("/api/workspace-tasks")
    team_tasks = await logged_in_client.get(f"/api/team-spaces/{space_id}/workspace-tasks")
    assert all(item["workspace_kind"] == "personal" for item in personal_tasks.json())
    assert all(item["workspace_kind"] == "team" for item in team_tasks.json())
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd backend && pytest tests/test_workspace_tasks.py::test_team_workspace_tasks_are_isolated -v
```

Expected: FAIL with missing team upload/tasks routes or missing fields.

- [ ] **Step 3: Add workspace scope params to upload/conversion services**

Modify upload task creation functions in `backend/app/modules/uploads/tasks.py` to accept:

```python
workspace_kind: str = "personal"
team_space_id: int | None = None
workspace_root: Path | None = None
```

When creating `UploadTask`, set:

```python
task.workspace_kind = workspace_kind
task.team_space_id = team_space_id
```

Use `workspace_root or user_workspace(username)` for file writes.

- [ ] **Step 4: Add team upload/task routes**

In `backend/app/api/routes/team_spaces.py`, add:

```python
@router.post("/{space_id}/upload-tasks")
async def create_team_upload_tasks(space_id: int, payload: UploadTaskCreateIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    return await create_upload_tasks(db, user.username, payload, workspace_kind="team", team_space_id=space_id, workspace_root=scope.root)


@router.get("/{space_id}/workspace-tasks")
async def list_team_workspace_tasks(space_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    scope = await team_workspace_scope(db, user, space_id)
    return await list_workspace_tasks(db, user.username, workspace_kind="team", team_space_id=space_id)
```

Expose these helper names from their modules while preserving existing personal-space callers:

```python
async def create_upload_tasks(db, username, payload, *, workspace_kind="personal", team_space_id=None, workspace_root=None):
    return await create_upload_tasks_for_workspace(
        db,
        username,
        payload,
        workspace_kind=workspace_kind,
        team_space_id=team_space_id,
        workspace_root=workspace_root,
    )


async def upload_task_file(db, username, task_id, file, *, workspace_root=None):
    return await upload_task_file_for_workspace(
        db,
        username,
        task_id,
        file,
        workspace_root=workspace_root,
    )


async def list_workspace_tasks(db, username, *, workspace_kind="personal", team_space_id=None, limit=20, offset=0):
    return await list_workspace_tasks_for_workspace(
        db,
        username,
        workspace_kind=workspace_kind,
        team_space_id=team_space_id,
        limit=limit,
        offset=offset,
    )
```

- [ ] **Step 5: Update conversion service**

Modify conversion task list/retry functions to filter by:

```python
workspace_kind == requested_kind
team_space_id == requested_team_space_id
```

When retrying from a team route, call `require_workspace_write(scope)` before creating or restarting conversion because conversion writes `.markdown`.

- [ ] **Step 6: Run task tests**

Run:

```bash
cd backend && pytest tests/test_workspace_upload_tasks.py tests/test_workspace_tasks.py tests/test_conversion_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/uploads backend/app/api/routes/upload_tasks.py backend/app/modules/conversions backend/app/api/routes/conversion_tasks.py backend/app/modules/workspace/tasks.py backend/app/api/routes/workspace_tasks.py backend/app/api/routes/team_spaces.py backend/tests
git commit -m "feat:隔离团队空间任务归属"
```

---

### Task 7: Server Verification and Regression Sweep

**Files:**
- Modify only backend files required by failures found in this task.

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
cd backend && pytest tests/test_team_spaces_api.py tests/test_team_workspace_api.py tests/test_team_sessions_api.py tests/test_team_workspace_agent_hooks.py tests/test_workspace_upload_tasks.py tests/test_workspace_tasks.py tests/test_conversion_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run backend full test suite**

Run:

```bash
cd backend && pytest -q
```

Expected: PASS.

- [ ] **Step 3: Run backend manual smoke**

Run:

```bash
cd backend && uvicorn app.main:app --reload
```

Verify through API client or browser devtools:

1. Owner can create a team space and is inserted as `editor`.
2. Owner can add `reader` and `editor` members.
3. Reader can list/read team workspace files but cannot upload/edit/delete/lock.
4. Editor can lock, write while holding lock, and unlock.
5. Another editor cannot write while lock is held.
6. Team session list is visible to current members.
7. Team session run uses `team_workspaces/<space_id>` as cwd.
8. Claude write tools are denied for readonly members or locked spaces.

- [ ] **Step 4: Commit final server fixes when files changed**

When previous verification steps required code changes, commit those specific files:

```bash
git status --short
git add backend
git commit -m "fix:完善团队空间服务端回归问题"
```

When `git status --short` is empty after verification, skip this commit step.
