# Workspace Upload Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build persistent asynchronous upload tasks for personal workspace uploads and replace the right conversion drawer with a unified upload/conversion task list.

**Architecture:** Keep existing `conversion_tasks` unchanged. Add independent `upload_tasks` persistence and APIs, then expose `/api/workspace-tasks` as the unified display layer. The frontend creates upload tasks, uploads one file at a time with XHR progress, and renders the compact mixed task list.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic, pytest/httpx, React 18, TypeScript, Vite, XMLHttpRequest upload progress.

---

## File Structure

- Create `backend/app/models/upload_task.py`: ORM model for persisted upload tasks.
- Modify `backend/app/models/__init__.py`: export `UploadTask`.
- Modify `backend/app/db/migrations.py`: create `upload_tasks` and indexes for existing deployments.
- Create `backend/app/schemas/upload_tasks.py`: request/response schemas for upload task APIs.
- Create `backend/app/schemas/workspace_tasks.py`: unified task response schema.
- Modify `backend/app/schemas/__init__.py`: export new schemas.
- Create `backend/app/modules/uploads/tasks.py`: upload task creation, claiming, progress, abandon, file write, and auto conversion scheduling logic.
- Create `backend/app/modules/workspace/tasks.py`: aggregation of upload and conversion tasks.
- Create `backend/app/api/routes/upload_tasks.py`: upload task API routes.
- Create `backend/app/api/routes/workspace_tasks.py`: unified task API route.
- Modify `backend/app/api/router.py`: include new routers.
- Modify `backend/tests/conftest.py`: reload new modules/models/schemas/routes.
- Create `backend/tests/test_workspace_upload_tasks.py`: backend task API tests.
- Create `backend/tests/test_workspace_tasks.py`: unified task list tests.
- Modify `frontend/src/types/index.ts`: add `UploadTask`, `WorkspaceTask`, request/response types.
- Modify `frontend/src/api/client.ts`: add upload task and workspace task APIs.
- Create `frontend/src/components/workspace/WorkspaceTaskDrawer.tsx`: compact unified task list.
- Modify `frontend/src/pages/WorkspacePage.tsx`: replace direct batch upload with queued task upload and replace conversion drawer.
- Modify or create `frontend/tests/workspaceTasks.test.ts`: type/mapper-level assertions if the existing test setup can run them; otherwise rely on `npm run build`.

---

### Task 1: Backend Upload Task Persistence

**Files:**
- Create: `backend/app/models/upload_task.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/db/migrations.py`
- Create: `backend/app/schemas/upload_tasks.py`
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_workspace_upload_tasks.py`

- [ ] **Step 1: Write failing model/schema tests**

Create `backend/tests/test_workspace_upload_tasks.py` with:

```python
import pytest


async def test_create_upload_tasks_persists_queued_items(logged_in_client):
    payload = {
        "target_dir": "docs",
        "items": [
            {"filename": "a.txt", "relative_path": "a.txt", "size": 12},
            {"filename": "b.pdf", "relative_path": "nested/b.pdf", "size": 34},
        ],
    }

    r = await logged_in_client.post("/api/upload-tasks", json=payload)

    assert r.status_code == 200
    data = r.json()
    assert [item["filename"] for item in data] == ["a.txt", "b.pdf"]
    assert [item["status"] for item in data] == ["queued", "queued"]
    assert [item["progress"] for item in data] == [0, 0]
    assert data[0]["target_dir"] == "docs"
    assert data[0]["relative_path"] == "a.txt"
    assert data[0]["saved_path"] == "docs/a.txt"
    assert data[1]["saved_path"] == "docs/nested/b.pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend && pytest tests/test_workspace_upload_tasks.py::test_create_upload_tasks_persists_queued_items -v
```

Expected: FAIL with 404 for `/api/upload-tasks` or import errors for missing modules.

- [ ] **Step 3: Add `UploadTask` model**

Create `backend/app/models/upload_task.py`:

```python
"""Workspace upload task ORM model."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UploadTask(Base):
    """个人空间上传任务。"""

    __tablename__ = "upload_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, nullable=False)
    target_dir: Mapped[str] = mapped_column(String, nullable=False, default="")
    relative_path: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    saved_path: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_upload_tasks_user_created", "username", "created_at"),
        Index("idx_upload_tasks_user_status", "username", "status"),
        Index("idx_upload_tasks_status", "status"),
    )
```

Modify `backend/app/models/__init__.py`:

```python
from app.models.upload_task import UploadTask
```

Keep existing exports intact.

- [ ] **Step 4: Add migration compatibility**

In `backend/app/db/migrations.py`, after the `conversion_tasks` migration block, add:

```python
        # upload_tasks 表迁移
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='upload_tasks'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE upload_tasks ("
                "id SERIAL PRIMARY KEY, "
                "username VARCHAR NOT NULL, "
                "target_dir VARCHAR NOT NULL DEFAULT '', "
                "relative_path VARCHAR NOT NULL, "
                "filename VARCHAR NOT NULL, "
                "status VARCHAR NOT NULL DEFAULT 'queued', "
                "progress INTEGER NOT NULL DEFAULT 0, "
                "size INTEGER NOT NULL DEFAULT 0, "
                "saved_path VARCHAR NULL, "
                "error_message TEXT NULL, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "started_at TIMESTAMP WITH TIME ZONE NULL, "
                "finished_at TIMESTAMP WITH TIME ZONE NULL, "
                "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_upload_tasks_user_created "
                "ON upload_tasks (username, created_at)"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_upload_tasks_user_status "
                "ON upload_tasks (username, status)"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_upload_tasks_status "
                "ON upload_tasks (status)"
            ))
```

- [ ] **Step 5: Add upload task schemas**

Create `backend/app/schemas/upload_tasks.py`:

```python
"""上传任务 API 模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class UploadTaskCreateItemIn(BaseModel):
    filename: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    size: int = Field(ge=0)


class UploadTaskCreateIn(BaseModel):
    target_dir: str = ""
    items: list[UploadTaskCreateItemIn]


class UploadTaskProgressIn(BaseModel):
    progress: int = Field(ge=0, le=100)


class UploadTaskAbandonIn(BaseModel):
    ids: list[int]


class UploadTaskOut(BaseModel):
    id: int
    target_dir: str
    relative_path: str
    filename: str
    status: str
    progress: int
    size: int
    saved_path: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}
```

Modify `backend/app/schemas/__init__.py`:

```python
from app.schemas.upload_tasks import (
    UploadTaskAbandonIn,
    UploadTaskCreateIn,
    UploadTaskOut,
    UploadTaskProgressIn,
)
```

Add these names to `__all__`.

- [ ] **Step 6: Update test reload fixture**

In `backend/tests/conftest.py`, add reloads for:

```python
from app.models import upload_task as model_upload_task
from app.schemas import upload_tasks as schema_upload_tasks
from app.modules.uploads import tasks as upload_tasks_service
from app.api.routes import upload_tasks as upload_tasks_routes
```

Call `reload(...)` in the matching model/schema/module/api sections.

- [ ] **Step 7: Implement minimal route/service for task creation**

Create `backend/app/modules/uploads/tasks.py` with:

```python
"""个人空间上传任务服务。"""

from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import safe_filename
from app.models.upload_task import UploadTask
from app.modules.uploads.service import _dedupe_path, _safe_relative_parts
from app.modules.workspace.paths import resolve_inside_workspace
from app.schemas.upload_tasks import UploadTaskCreateIn


def _target_path_for_task(workspace: Path, target_dir: str, relative_path: str) -> tuple[str, str, Path]:
    base_dir = workspace if not target_dir else resolve_inside_workspace(workspace, target_dir)
    parts = _safe_relative_parts(relative_path)
    parts[-1] = safe_filename(parts[-1])
    if not parts[-1]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件名不能为空")
    target = _dedupe_path(base_dir.joinpath(*parts))
    rel_path = target.resolve().relative_to(workspace.resolve()).as_posix()
    return base_dir.relative_to(workspace.resolve()).as_posix() if base_dir != workspace else "", rel_path, target


async def create_upload_tasks(
    session: AsyncSession,
    *,
    username: str,
    workspace: Path,
    data: UploadTaskCreateIn,
) -> list[UploadTask]:
    if not data.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未提供任何文件")

    tasks: list[UploadTask] = []
    for item in data.items:
        target_dir, saved_path, _target = _target_path_for_task(workspace, data.target_dir, item.relative_path)
        task = UploadTask(
            username=username,
            target_dir=target_dir,
            relative_path=item.relative_path,
            filename=safe_filename(item.filename) or "file",
            status="queued",
            progress=0,
            size=item.size,
            saved_path=saved_path,
        )
        session.add(task)
        tasks.append(task)
    await session.commit()
    for task in tasks:
        await session.refresh(task)
    return tasks
```

Create `backend/app/api/routes/upload_tasks.py`:

```python
"""上传任务路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core.config import user_workspace
from app.db.session import get_db
from app.models import User
from app.modules.uploads.tasks import create_upload_tasks
from app.schemas import UploadTaskCreateIn, UploadTaskOut

router = APIRouter(prefix="/api/upload-tasks")


@router.post("", response_model=list[UploadTaskOut])
async def create_upload_tasks_route(
    data: UploadTaskCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[UploadTaskOut]:
    return await create_upload_tasks(
        session,
        username=user.username,
        workspace=user_workspace(user.username),
        data=data,
    )
```

Modify `backend/app/api/router.py`:

```python
from app.api.routes import upload_tasks

router.include_router(upload_tasks.router)
```

- [ ] **Step 8: Run task creation test**

Run:

```bash
cd backend && pytest tests/test_workspace_upload_tasks.py::test_create_upload_tasks_persists_queued_items -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/upload_task.py backend/app/models/__init__.py backend/app/db/migrations.py backend/app/schemas/upload_tasks.py backend/app/schemas/__init__.py backend/app/modules/uploads/tasks.py backend/app/api/routes/upload_tasks.py backend/app/api/router.py backend/tests/conftest.py backend/tests/test_workspace_upload_tasks.py
git commit -m "feat:添加上传任务模型"
```

---

### Task 2: Backend Upload Execution, Progress, Abandon, and Conversion Hook

**Files:**
- Modify: `backend/app/modules/uploads/tasks.py`
- Modify: `backend/app/api/routes/upload_tasks.py`
- Test: `backend/tests/test_workspace_upload_tasks.py`

- [ ] **Step 1: Add failing upload execution tests**

Append to `backend/tests/test_workspace_upload_tasks.py`:

```python
async def test_upload_task_file_saves_file_and_marks_success(logged_in_client):
    create = await logged_in_client.post("/api/upload-tasks", json={
        "target_dir": "docs",
        "items": [{"filename": "a.txt", "relative_path": "a.txt", "size": 5}],
    })
    task_id = create.json()[0]["id"]

    r = await logged_in_client.post(
        f"/api/upload-tasks/{task_id}/file",
        files={"file": ("a.txt", b"hello", "text/plain")},
    )

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "succeeded"
    assert data["progress"] == 100
    assert data["saved_path"] == "docs/a.txt"

    from app.core.config import user_workspace
    assert (user_workspace("alice") / "docs" / "a.txt").read_bytes() == b"hello"


async def test_upload_progress_updates_running_task(logged_in_client):
    create = await logged_in_client.post("/api/upload-tasks", json={
        "target_dir": "",
        "items": [{"filename": "a.bin", "relative_path": "a.bin", "size": 10}],
    })
    task_id = create.json()[0]["id"]

    started = await logged_in_client.patch(f"/api/upload-tasks/{task_id}/progress", json={"progress": 45})

    assert started.status_code == 409
```

The second test establishes that progress cannot be updated before a task is running.

- [ ] **Step 2: Run upload execution tests to verify failure**

Run:

```bash
cd backend && pytest tests/test_workspace_upload_tasks.py::test_upload_task_file_saves_file_and_marks_success tests/test_workspace_upload_tasks.py::test_upload_progress_updates_running_task -v
```

Expected: FAIL with 404 for missing routes.

- [ ] **Step 3: Implement upload execution**

In `backend/app/modules/uploads/tasks.py`, add:

```python
from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy import select, update

from app.modules.conversions.service import create_conversion_task, is_convertible_path, schedule_conversion_task
from app.modules.uploads.service import _MAX_FILE_SIZE, _upload_tmp_path


async def _claim_upload_task(session: AsyncSession, *, username: str, task_id: int) -> UploadTask:
    running = await session.execute(
        select(UploadTask.id).where(
            UploadTask.username == username,
            UploadTask.status == "running",
            UploadTask.id != task_id,
        )
    )
    if running.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已有上传任务正在执行")

    result = await session.execute(
        update(UploadTask)
        .where(
            UploadTask.id == task_id,
            UploadTask.username == username,
            UploadTask.status == "queued",
        )
        .values(status="running", started_at=datetime.now(UTC), finished_at=None, error_message=None)
        .returning(UploadTask.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="上传任务状态不可执行")
    await session.commit()
    task = await session.get(UploadTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="上传任务不存在")
    return task


async def upload_task_file(
    session: AsyncSession,
    *,
    username: str,
    workspace: Path,
    task_id: int,
    file: UploadFile,
    background_tasks=None,
) -> UploadTask:
    task = await _claim_upload_task(session, username=username, task_id=task_id)
    assert task.saved_path is not None
    target = resolve_inside_workspace(workspace, task.saved_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_target = _upload_tmp_path(target)
    total = 0
    try:
        with tmp_target.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_FILE_SIZE:
                    raise ValueError(f"文件 {task.filename} 超过 {_MAX_FILE_SIZE // (1024 * 1024)} MB 上限")
                out.write(chunk)
        tmp_target.replace(target)
        task.status = "succeeded"
        task.progress = 100
        task.size = total
        task.error_message = None
        task.finished_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(task)
        if is_convertible_path(target):
            try:
                conversion = await create_conversion_task(
                    session,
                    username=username,
                    workspace=workspace,
                    source_path=task.saved_path,
                )
                schedule_conversion_task(background_tasks, conversion.id)
            except HTTPException as exc:
                if exc.status_code != status.HTTP_409_CONFLICT:
                    raise
        return task
    except Exception as exc:
        tmp_target.unlink(missing_ok=True)
        task.status = "failed"
        task.error_message = str(exc)
        task.finished_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(task)
        raise
    finally:
        await file.close()


async def update_upload_task_progress(
    session: AsyncSession,
    *,
    username: str,
    task_id: int,
    progress: int,
) -> UploadTask:
    task = await session.get(UploadTask, task_id)
    if task is None or task.username != username:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="上传任务不存在")
    if task.status != "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="上传任务未在执行中")
    task.progress = progress
    await session.commit()
    await session.refresh(task)
    return task
```

In `backend/app/api/routes/upload_tasks.py`, add:

```python
from fastapi import BackgroundTasks, File, UploadFile
from app.modules.uploads.tasks import update_upload_task_progress, upload_task_file
from app.schemas import UploadTaskProgressIn


@router.post("/{task_id}/file", response_model=UploadTaskOut)
async def upload_task_file_route(
    task_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> UploadTaskOut:
    return await upload_task_file(
        session,
        username=user.username,
        workspace=user_workspace(user.username),
        task_id=task_id,
        file=file,
        background_tasks=background_tasks,
    )


@router.patch("/{task_id}/progress", response_model=UploadTaskOut)
async def update_upload_task_progress_route(
    task_id: int,
    data: UploadTaskProgressIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> UploadTaskOut:
    return await update_upload_task_progress(
        session,
        username=user.username,
        task_id=task_id,
        progress=data.progress,
    )
```

- [ ] **Step 4: Run upload success tests**

Run:

```bash
cd backend && pytest tests/test_workspace_upload_tasks.py::test_upload_task_file_saves_file_and_marks_success tests/test_workspace_upload_tasks.py::test_upload_progress_updates_running_task -v
```

Expected: PASS.

- [ ] **Step 5: Add failing abandon and auto-conversion tests**

Append:

```python
async def test_abandon_marks_unfinished_upload_tasks_failed(logged_in_client):
    create = await logged_in_client.post("/api/upload-tasks", json={
        "target_dir": "",
        "items": [{"filename": "a.txt", "relative_path": "a.txt", "size": 5}],
    })
    task_id = create.json()[0]["id"]

    r = await logged_in_client.post("/api/upload-tasks/abandon", json={"ids": [task_id]})

    assert r.status_code == 200
    data = r.json()
    assert data[0]["status"] == "failed"
    assert "页面刷新导致上传中断" in data[0]["error_message"]


async def test_upload_success_creates_conversion_task_for_convertible_file(logged_in_client):
    create = await logged_in_client.post("/api/upload-tasks", json={
        "target_dir": "",
        "items": [{"filename": "a.pdf", "relative_path": "a.pdf", "size": 4}],
    })
    task_id = create.json()[0]["id"]

    uploaded = await logged_in_client.post(
        f"/api/upload-tasks/{task_id}/file",
        files={"file": ("a.pdf", b"%PDF", "application/pdf")},
    )
    tasks = await logged_in_client.get("/api/conversion-tasks")

    assert uploaded.status_code == 200
    assert any(task["source_path"] == "a.pdf" for task in tasks.json())
```

- [ ] **Step 6: Run abandon/conversion tests to verify failure**

Run:

```bash
cd backend && pytest tests/test_workspace_upload_tasks.py::test_abandon_marks_unfinished_upload_tasks_failed tests/test_workspace_upload_tasks.py::test_upload_success_creates_conversion_task_for_convertible_file -v
```

Expected: abandon test fails with 404 until route is added; conversion test should pass if Step 3 hook is complete.

- [ ] **Step 7: Implement abandon**

In `backend/app/modules/uploads/tasks.py`, add:

```python
async def abandon_upload_tasks(
    session: AsyncSession,
    *,
    username: str,
    ids: list[int],
) -> list[UploadTask]:
    if not ids:
        return []
    await session.execute(
        update(UploadTask)
        .where(
            UploadTask.username == username,
            UploadTask.id.in_(ids),
            UploadTask.status.in_(("queued", "running")),
        )
        .values(
            status="failed",
            error_message="页面刷新导致上传中断，请重新上传",
            finished_at=datetime.now(UTC),
        )
    )
    await session.commit()
    result = await session.execute(
        select(UploadTask)
        .where(UploadTask.username == username, UploadTask.id.in_(ids))
        .order_by(UploadTask.created_at.desc(), UploadTask.id.desc())
    )
    return list(result.scalars().all())
```

In `backend/app/api/routes/upload_tasks.py`, add:

```python
from app.modules.uploads.tasks import abandon_upload_tasks
from app.schemas import UploadTaskAbandonIn


@router.post("/abandon", response_model=list[UploadTaskOut])
async def abandon_upload_tasks_route(
    data: UploadTaskAbandonIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[UploadTaskOut]:
    return await abandon_upload_tasks(session, username=user.username, ids=data.ids)
```

Place this static route before `/{task_id}/file` to avoid path conflicts.

- [ ] **Step 8: Run full upload task backend tests**

Run:

```bash
cd backend && pytest tests/test_workspace_upload_tasks.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/uploads/tasks.py backend/app/api/routes/upload_tasks.py backend/tests/test_workspace_upload_tasks.py
git commit -m "feat:实现上传任务执行"
```

---

### Task 3: Unified Workspace Task API

**Files:**
- Create: `backend/app/schemas/workspace_tasks.py`
- Modify: `backend/app/schemas/__init__.py`
- Create: `backend/app/modules/workspace/tasks.py`
- Create: `backend/app/api/routes/workspace_tasks.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_workspace_tasks.py`

- [ ] **Step 1: Write failing aggregation test**

Create `backend/tests/test_workspace_tasks.py`:

```python
async def test_workspace_tasks_mixes_upload_and_conversion_tasks(logged_in_client):
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "manual.pdf").write_bytes(b"%PDF")

    upload_create = await logged_in_client.post("/api/upload-tasks", json={
        "target_dir": "",
        "items": [{"filename": "a.txt", "relative_path": "a.txt", "size": 5}],
    })
    await logged_in_client.post("/api/conversion-tasks/retry", json={"source_path": "manual.pdf"})

    r = await logged_in_client.get("/api/workspace-tasks")

    assert r.status_code == 200
    data = r.json()
    assert {item["type"] for item in data} == {"upload", "conversion"}
    upload = next(item for item in data if item["type"] == "upload")
    conversion = next(item for item in data if item["type"] == "conversion")
    assert upload["id"] == upload_create.json()[0]["id"]
    assert upload["name"] == "a.txt"
    assert upload["progress"] == 0
    assert conversion["name"] == "manual.pdf"
    assert conversion["progress"] is None
```

- [ ] **Step 2: Run aggregation test to verify failure**

Run:

```bash
cd backend && pytest tests/test_workspace_tasks.py::test_workspace_tasks_mixes_upload_and_conversion_tasks -v
```

Expected: FAIL with 404 for `/api/workspace-tasks`.

- [ ] **Step 3: Add unified schema**

Create `backend/app/schemas/workspace_tasks.py`:

```python
"""个人空间通用任务 API 模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class WorkspaceTaskOut(BaseModel):
    type: Literal["upload", "conversion"]
    id: int
    name: str
    path: str
    status: str
    progress: int | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
```

Modify `backend/app/schemas/__init__.py`:

```python
from app.schemas.workspace_tasks import WorkspaceTaskOut
```

Add `WorkspaceTaskOut` to `__all__`.

- [ ] **Step 4: Implement aggregation service and route**

Create `backend/app/modules/workspace/tasks.py`:

```python
"""个人空间通用任务聚合服务。"""

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversion_task import ConversionTask
from app.models.upload_task import UploadTask
from app.schemas.workspace_tasks import WorkspaceTaskOut


async def list_workspace_tasks(
    session: AsyncSession,
    username: str,
    *,
    limit: int = 10,
    offset: int = 0,
) -> list[WorkspaceTaskOut]:
    upload_result = await session.execute(
        select(UploadTask)
        .where(UploadTask.username == username)
        .order_by(desc(UploadTask.created_at), desc(UploadTask.id))
        .limit(limit + offset)
    )
    conversion_result = await session.execute(
        select(ConversionTask)
        .where(ConversionTask.username == username)
        .order_by(desc(ConversionTask.created_at), desc(ConversionTask.id))
        .limit(limit + offset)
    )

    items: list[WorkspaceTaskOut] = []
    for task in upload_result.scalars().all():
        items.append(WorkspaceTaskOut(
            type="upload",
            id=task.id,
            name=task.filename,
            path=task.saved_path or task.relative_path,
            status=task.status,
            progress=task.progress,
            error_message=task.error_message,
            created_at=task.created_at,
            started_at=task.started_at,
            finished_at=task.finished_at,
        ))
    for task in conversion_result.scalars().all():
        items.append(WorkspaceTaskOut(
            type="conversion",
            id=task.id,
            name=task.source_name,
            path=task.source_path,
            status=task.status,
            progress=None,
            error_message=task.error_message,
            created_at=task.created_at,
            started_at=task.started_at,
            finished_at=task.finished_at,
        ))

    items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
    return items[offset:offset + limit]
```

Create `backend/app/api/routes/workspace_tasks.py`:

```python
"""个人空间通用任务路由。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.db.session import get_db
from app.models import User
from app.modules.workspace.tasks import list_workspace_tasks
from app.schemas import WorkspaceTaskOut

router = APIRouter(prefix="/api/workspace-tasks")


@router.get("", response_model=list[WorkspaceTaskOut])
async def workspace_tasks_route(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[WorkspaceTaskOut]:
    return await list_workspace_tasks(session, user.username, limit=limit, offset=offset)
```

Modify `backend/app/api/router.py`:

```python
from app.api.routes import workspace_tasks
router.include_router(workspace_tasks.router)
```

Modify `backend/tests/conftest.py` to reload `app.modules.workspace.tasks` and `app.api.routes.workspace_tasks`.

- [ ] **Step 5: Run aggregation tests**

Run:

```bash
cd backend && pytest tests/test_workspace_tasks.py -v
```

Expected: PASS.

- [ ] **Step 6: Run backend related tests**

Run:

```bash
cd backend && pytest tests/test_workspace_upload_tasks.py tests/test_workspace_tasks.py tests/test_workspace_office_preview.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/workspace_tasks.py backend/app/schemas/__init__.py backend/app/modules/workspace/tasks.py backend/app/api/routes/workspace_tasks.py backend/app/api/router.py backend/tests/conftest.py backend/tests/test_workspace_tasks.py
git commit -m "feat:添加个人空间通用任务接口"
```

---

### Task 4: Frontend Types, API Client, and Upload Queue

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Test/Verify: `frontend/tests/workspacePreview.test.ts` or new `frontend/tests/workspaceTasks.test.ts`, plus `npm run build`

- [ ] **Step 1: Add TypeScript types**

Modify `frontend/src/types/index.ts`:

```ts
export interface UploadTask {
  id: number;
  target_dir: string;
  relative_path: string;
  filename: string;
  status: "queued" | "running" | "succeeded" | "failed";
  progress: number;
  size: number;
  saved_path: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface UploadTaskCreateItem {
  filename: string;
  relative_path: string;
  size: number;
}

export interface WorkspaceTask {
  type: "upload" | "conversion";
  id: number;
  name: string;
  path: string;
  status: "queued" | "running" | "succeeded" | "failed";
  progress: number | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}
```

- [ ] **Step 2: Add API client methods**

Modify imports in `frontend/src/api/client.ts` to include `UploadTask`, `UploadTaskCreateItem`, and `WorkspaceTask`.

Add methods:

```ts
  createUploadTasks: (targetDir: string, items: UploadTaskCreateItem[]) =>
    request<UploadTask[]>("/api/upload-tasks", {
      method: "POST",
      body: JSON.stringify({ target_dir: targetDir, items }),
    }),

  uploadTaskFile: (
    taskId: number,
    file: File,
    opts: {
      onProgress?: (percent: number) => void;
    } = {},
  ) =>
    new Promise<UploadTask>((resolve, reject) => {
      const form = new FormData();
      form.append("file", file, file.name);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/upload-tasks/${taskId}/file`);
      xhr.withCredentials = true;
      xhr.upload.onprogress = (evt) => {
        if (evt.lengthComputable && opts.onProgress) {
          opts.onProgress(Math.round((evt.loaded / evt.total) * 100));
        }
      };
      xhr.onload = () => {
        if (xhr.status === 401) {
          redirectToLogin();
          reject(unauthorizedError());
          return;
        }
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(new Error(`HTTP ${xhr.status}: ${xhr.responseText || xhr.statusText}`));
          return;
        }
        resolve(JSON.parse(xhr.responseText) as UploadTask);
      };
      xhr.onerror = () => reject(new Error("上传失败"));
      xhr.send(form);
    }),

  updateUploadTaskProgress: (taskId: number, progress: number) =>
    request<UploadTask>(`/api/upload-tasks/${taskId}/progress`, {
      method: "PATCH",
      body: JSON.stringify({ progress }),
    }),

  abandonUploadTasks: (ids: number[]) =>
    request<UploadTask[]>("/api/upload-tasks/abandon", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),

  workspaceTasks: (limit?: number, offset?: number) => {
    const qs = new URLSearchParams();
    if (limit !== undefined) qs.set("limit", String(limit));
    if (offset !== undefined) qs.set("offset", String(offset));
    const query = qs.toString();
    return request<WorkspaceTask[]>(
      `/api/workspace-tasks${query ? "?" + query : ""}`,
    );
  },
```

- [ ] **Step 3: Change workspace page task state**

In `frontend/src/pages/WorkspacePage.tsx`:

```ts
import type { WorkspaceTask, UploadTask } from "@/types";
```

Replace:

```ts
const [tasks, setTasks] = useState<ConversionTask[]>([]);
const tasksRef = useRef<ConversionTask[]>(tasks);
```

with:

```ts
const [tasks, setTasks] = useState<WorkspaceTask[]>([]);
const uploadQueueRef = useRef<Array<{ task: UploadTask; file: File }>>([]);
const uploadActiveRef = useRef(false);
const pendingUploadTaskIdsRef = useRef<Set<number>>(new Set());
const tasksRef = useRef<WorkspaceTask[]>(tasks);
```

Replace `api.conversionTasks(limit, offset)` inside `loadTasks` with:

```ts
const newTasks = await api.workspaceTasks(limit, offset);
```

- [ ] **Step 4: Replace direct upload with queued upload**

In `WorkspacePage.tsx`, replace the existing `upload` callback with:

```ts
  const syncUploadProgress = useCallback((taskId: number, progress: number) => {
    setTasks((prev) =>
      prev.map((task) =>
        task.type === "upload" && task.id === taskId
          ? { ...task, status: "running", progress }
          : task,
      ),
    );
    void api.updateUploadTaskProgress(taskId, progress).catch(() => undefined);
  }, []);

  const drainUploadQueue = useCallback(async () => {
    if (uploadActiveRef.current) return;
    uploadActiveRef.current = true;
    try {
      while (uploadQueueRef.current.length > 0) {
        const next = uploadQueueRef.current.shift();
        if (!next) continue;
        pendingUploadTaskIdsRef.current.add(next.task.id);
        try {
          await api.uploadTaskFile(next.task.id, next.file, {
            onProgress: (percent) => syncUploadProgress(next.task.id, percent),
          });
        } catch (e) {
          showToast(`上传失败：${formatErrorMessage(e)}`, "error");
        } finally {
          pendingUploadTaskIdsRef.current.delete(next.task.id);
          await loadTree();
          await loadTasks("refresh");
        }
      }
    } finally {
      uploadActiveRef.current = false;
    }
  }, [loadTasks, loadTree, showToast, syncUploadProgress]);

  const upload = useCallback(
    async (targetDir: string, files: File[], relativePaths: string[]) => {
      if (files.length === 0) return;
      try {
        const created = await api.createUploadTasks(
          targetDir,
          files.map((file, index) => ({
            filename: file.name,
            relative_path: relativePaths[index] || file.name,
            size: file.size,
          })),
        );
        created.forEach((task, index) => {
          uploadQueueRef.current.push({ task, file: files[index] });
          pendingUploadTaskIdsRef.current.add(task.id);
        });
        await loadTasks("refresh");
        void drainUploadQueue();
      } catch (e) {
        showToast(`创建上传任务失败：${formatErrorMessage(e)}`, "error");
      }
    },
    [drainUploadQueue, loadTasks, showToast],
  );
```

Remove `uploadProgress` state and the left-side `上传中 {uploadProgress}%` banner, because progress now appears in the right task drawer.

- [ ] **Step 5: Add beforeunload abandon handling**

In `WorkspacePage.tsx`, add:

```ts
  useEffect(() => {
    const hasPendingUploads = pendingUploadTaskIdsRef.current.size > 0;
    if (!hasPendingUploads) return;

    const abandon = () => {
      const ids = Array.from(pendingUploadTaskIdsRef.current);
      if (ids.length === 0) return;
      const body = JSON.stringify({ ids });
      if (navigator.sendBeacon) {
        navigator.sendBeacon(
          "/api/upload-tasks/abandon",
          new Blob([body], { type: "application/json" }),
        );
        return;
      }
      void fetch("/api/upload-tasks/abandon", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        keepalive: true,
      });
    };

    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
      abandon();
    };

    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [tasks]);
```

If implementation reveals that this effect does not re-run when only the ref changes, add a `pendingUploadVersion` state incremented whenever `pendingUploadTaskIdsRef` changes and use it in the dependency array.

- [ ] **Step 6: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/pages/WorkspacePage.tsx
git commit -m "feat:实现个人空间上传队列"
```

---

### Task 5: Frontend Unified Task Drawer

**Files:**
- Create: `frontend/src/components/workspace/WorkspaceTaskDrawer.tsx`
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Optional Delete: `frontend/src/components/workspace/ConversionTaskDrawer.tsx` only if no imports remain

- [ ] **Step 1: Create unified drawer component**

Create `frontend/src/components/workspace/WorkspaceTaskDrawer.tsx`:

```tsx
import React from "react";
import type { WorkspaceTask } from "@/types";
import { I } from "@/icons";

interface Props {
  tasks: WorkspaceTask[];
  collapsed: boolean;
  hasMore: boolean;
  onToggle: () => void;
  onRefresh: () => void;
  onLoadMore: () => void;
}

function taskStatusLabel(task: WorkspaceTask): string {
  if (task.status === "queued") return "等待中";
  if (task.status === "running") return task.type === "upload" ? "上传中" : "转换中";
  if (task.status === "succeeded") return "已完成";
  return "失败";
}

function taskStatusColor(task: WorkspaceTask): string {
  if (task.status === "queued") return "var(--ink-3)";
  if (task.status === "running") return "var(--accent)";
  if (task.status === "succeeded") return "var(--success)";
  return "var(--danger)";
}

export default function WorkspaceTaskDrawer(props: Props) {
  const { tasks, collapsed } = props;

  if (collapsed) {
    return (
      <div style={collapsedStyle}>
        <button onClick={props.onToggle} title="展开任务" style={iconBtnStyle}>
          <I.ChevronLeft size={16} />
        </button>
      </div>
    );
  }

  return (
    <div style={drawerStyle}>
      <div style={headerStyle}>
        <I.Server size={14} />
        <div style={{ flex: 1, fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>
          任务
        </div>
        <button onClick={props.onRefresh} title="刷新" style={iconBtnStyle}>
          <I.Refresh size={13} />
        </button>
        <button onClick={props.onToggle} title="收起" style={iconBtnStyle}>
          <I.ChevronRight size={16} />
        </button>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
        {tasks.length === 0 && (
          <div style={{ padding: 20, color: "var(--ink-3)", fontSize: 12.5, textAlign: "center" }}>
            暂无任务
          </div>
        )}
        {tasks.map((task) => {
          const color = taskStatusColor(task);
          return (
            <div key={`${task.type}-${task.id}`} style={cardStyle}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                <span style={task.type === "upload" ? uploadTagStyle : conversionTagStyle}>
                  {task.type === "upload" ? "上传" : "转换"}
                </span>
                <div
                  style={{
                    flex: 1,
                    fontSize: 12.5,
                    fontWeight: 500,
                    color: "var(--ink)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={task.path}
                >
                  {task.name}
                </div>
              </div>
              <div style={pathStyle}>{task.path}</div>
              {task.type === "upload" && task.status === "running" && (
                <div style={progressTrackStyle}>
                  <div style={{ ...progressBarStyle, width: `${task.progress ?? 0}%` }} />
                </div>
              )}
              <div style={statusRowStyle}>
                <span style={{ fontSize: 11, color, fontWeight: 600 }}>
                  {taskStatusLabel(task)}
                  {task.type === "upload" && task.status === "running" && task.progress !== null
                    ? ` ${task.progress}%`
                    : ""}
                </span>
              </div>
              {task.error_message && (
                <div style={{ fontSize: 11, color: "var(--danger)", marginTop: 4, wordBreak: "break-word" }}>
                  {task.error_message}
                </div>
              )}
            </div>
          );
        })}
        {props.tasks.length > 0 && (
          <div style={{ marginTop: 8, textAlign: "center" }}>
            {props.hasMore ? (
              <button onClick={props.onLoadMore} style={loadMoreStyle}>显示更多</button>
            ) : (
              <span style={{ fontSize: 12, color: "var(--ink-4)" }}>已显示全部</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const collapsedStyle: React.CSSProperties = {
  width: 40,
  borderLeft: "1px solid var(--line)",
  background: "var(--bg-2)",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  paddingTop: 12,
};

const drawerStyle: React.CSSProperties = {
  width: 280,
  borderLeft: "1px solid var(--line)",
  background: "var(--bg-2)",
  display: "flex",
  flexDirection: "column",
};

const headerStyle: React.CSSProperties = {
  height: 48,
  padding: "0 12px 0 16px",
  borderBottom: "1px solid var(--line)",
  display: "flex",
  alignItems: "center",
  gap: 8,
  flexShrink: 0,
};

const cardStyle: React.CSSProperties = {
  padding: "8px 10px",
  borderRadius: 8,
  border: "1px solid var(--line)",
  background: "var(--bg)",
  marginBottom: 6,
};

const pathStyle: React.CSSProperties = {
  fontSize: 11,
  color: "var(--ink-4)",
  marginTop: 2,
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const statusRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  marginTop: 6,
};

const progressTrackStyle: React.CSSProperties = {
  height: 5,
  background: "var(--line)",
  borderRadius: 999,
  overflow: "hidden",
  marginTop: 8,
};

const progressBarStyle: React.CSSProperties = {
  height: "100%",
  background: "var(--accent)",
  borderRadius: 999,
};

const uploadTagStyle: React.CSSProperties = {
  fontSize: 11,
  color: "var(--accent-2)",
  background: "var(--accent-soft)",
  borderRadius: 4,
  padding: "1px 5px",
  flexShrink: 0,
};

const conversionTagStyle: React.CSSProperties = {
  fontSize: 11,
  color: "var(--success)",
  background: "rgba(34, 197, 94, 0.12)",
  borderRadius: 4,
  padding: "1px 5px",
  flexShrink: 0,
};

const iconBtnStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: 28,
  height: 28,
  background: "transparent",
  border: "none",
  color: "var(--ink-3)",
  cursor: "pointer",
  borderRadius: 4,
};

const loadMoreStyle: React.CSSProperties = {
  fontSize: 12.5,
  color: "var(--accent-2)",
  background: "transparent",
  border: "none",
  cursor: "pointer",
  fontFamily: "inherit",
  padding: "4px 8px",
};
```

- [ ] **Step 2: Replace drawer usage**

In `frontend/src/pages/WorkspacePage.tsx`, replace:

```ts
import ConversionTaskDrawer from "@/components/workspace/ConversionTaskDrawer";
```

with:

```ts
import WorkspaceTaskDrawer from "@/components/workspace/WorkspaceTaskDrawer";
```

Replace JSX:

```tsx
<ConversionTaskDrawer
  tasks={tasks}
  collapsed={drawerCollapsed}
  hasMore={hasMore}
  onToggle={() => setDrawerCollapsed((v) => !v)}
  onRefresh={() => loadTasks("refresh")}
  onLoadMore={() => loadTasks("more")}
  onRetry={retry}
/>
```

with:

```tsx
<WorkspaceTaskDrawer
  tasks={tasks}
  collapsed={drawerCollapsed}
  hasMore={hasMore}
  onToggle={() => setDrawerCollapsed((v) => !v)}
  onRefresh={() => loadTasks("refresh")}
  onLoadMore={() => loadTasks("more")}
/>
```

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/workspace/WorkspaceTaskDrawer.tsx frontend/src/pages/WorkspacePage.tsx
git commit -m "feat:统一个人空间任务列表"
```

---

### Task 6: Final Verification and Cleanup

**Files:**
- Review all changed files from Tasks 1-5.

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
cd backend && pytest tests/test_workspace_upload_tasks.py tests/test_workspace_tasks.py tests/test_workspace_office_preview.py tests/test_workspace_preview.py -v
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

Expected: only intentional changes from this feature remain, plus any unrelated pre-existing user changes. Do not stage unrelated files such as `backend/app/integrations/claude/runner.py`, `backend/app/integrations/claude/guard.py.bak`, or files under `design/` unless the user explicitly asks.

- [ ] **Step 4: Commit final fixes if needed**

If verification required small fixes:

```bash
git add <only files touched for this feature>
git commit -m "fix:完善个人空间上传任务"
```

If no fixes are needed, do not create an empty commit.

- [ ] **Step 5: Report**

Summarize:

- Upload task persistence implemented.
- Single-user upload concurrency enforced.
- Frontend upload queue uploads one file at a time.
- Browser refresh warns and abandons unfinished uploads.
- Unified task drawer displays upload and conversion tasks.
- Backend tests and frontend build results.

---

## Self-Review

- Spec coverage: The plan covers persistent upload tasks, single-user upload concurrency, frontend serial queue, progress display, abandon-on-refresh, upload/conversion unified list, auto conversion after upload, no upload retry in v1, and keeping old `/api/uploads`.
- Placeholder scan: The plan contains no `TBD`, `TODO`, or unspecified implementation steps.
- Type consistency: Backend statuses are `queued | running | succeeded | failed`; frontend task types are `upload | conversion`; API and component names are consistent across tasks.
