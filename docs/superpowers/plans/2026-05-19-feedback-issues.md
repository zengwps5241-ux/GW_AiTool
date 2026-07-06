# Feedback Issues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a user feedback issue flow with a topbar feedback panel, persisted image attachments, and an admin-only feedback management page.

**Architecture:** Add focused backend feedback models, schemas, service functions, and routes under `app.modules.feedback` and `app.api.routes.feedback`. Store issue metadata in PostgreSQL and image files under a dedicated `feedback_uploads/` directory. Add frontend API types, a reusable feedback modal from `Topbar`, and an admin-only `FeedbackPage` wired through the existing `App` and `Sidebar` view router.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, local filesystem storage, multipart upload, React + TypeScript, existing UI primitives, pytest, `npm run build`.

---

## File Structure

- Create `backend/app/models/feedback.py`
  - Owns `FeedbackIssue` and `FeedbackAttachment` ORM models.
- Modify `backend/app/models/__init__.py`
  - Exports feedback models so `Base.metadata.create_all` sees them.
- Modify `backend/app/db/migrations.py`
  - Adds compatibility creation for `feedback_issues` and `feedback_attachments` tables and indexes.
- Create `backend/app/schemas/feedback.py`
  - Owns response schemas for create response, list items, paginated list, detail, and attachments.
- Modify `backend/app/schemas/__init__.py`
  - Exports feedback schemas.
- Create `backend/app/modules/feedback/service.py`
  - Owns validation, issue creation, attachment persistence, pagination, detail lookup, and attachment path resolution.
- Create `backend/app/api/routes/feedback.py`
  - Owns `/api/feedback/issues` and `/api/admin/feedback/*` routes.
- Modify `backend/app/api/router.py`
  - Includes feedback routes.
- Create `backend/tests/test_feedback_api.py`
  - Covers submit, image validation, admin list/detail/attachment, and permissions.
- Modify `frontend/src/types/index.ts`
  - Adds feedback types and `"feedback"` view.
- Modify `frontend/src/api/client.ts`
  - Adds feedback submit, admin list/detail, and attachment URL helpers.
- Modify `frontend/src/components/Topbar.tsx`
  - Adds feedback icon button and mounts `FeedbackDialog`.
- Create `frontend/src/components/FeedbackDialog.tsx`
  - Owns user feedback form, paste-image handling, preview, submit, and error UI.
- Modify `frontend/src/components/Sidebar.tsx`
  - Adds admin-only “反馈管理” item.
- Create `frontend/src/pages/FeedbackPage.tsx`
  - Owns admin feedback list, pagination, and detail view.
- Modify `frontend/src/App.tsx`
  - Wires feedback view, breadcrumb, and topbar feedback submit handler.

## Task 1: Backend Feedback Models and Migration

**Files:**
- Create: `backend/app/models/feedback.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/db/migrations.py`
- Test: `backend/tests/test_feedback_api.py`

- [ ] **Step 1: Write failing model/migration smoke test**

Create `backend/tests/test_feedback_api.py`:

```python
from pathlib import Path

import pytest


async def test_feedback_models_are_registered():
    from app.models import Base

    assert "feedback_issues" in Base.metadata.tables
    assert "feedback_attachments" in Base.metadata.tables
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
pytest backend/tests/test_feedback_api.py::test_feedback_models_are_registered -q
```

Expected: FAIL because `feedback_issues` and `feedback_attachments` are not registered.

- [ ] **Step 3: Add ORM models**

Create `backend/app/models/feedback.py`:

```python
"""问题反馈 ORM 模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FeedbackIssue(Base):
    __tablename__ = "feedback_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reporter_username: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )

    attachments: Mapped[list["FeedbackAttachment"]] = relationship(
        back_populates="issue",
        cascade="all, delete-orphan",
        order_by="FeedbackAttachment.id",
    )


class FeedbackAttachment(Base):
    __tablename__ = "feedback_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_issues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )

    issue: Mapped[FeedbackIssue] = relationship(back_populates="attachments")
```

- [ ] **Step 4: Export models**

Modify `backend/app/models/__init__.py`:

```python
from app.db.base import Base
from app.models.agent import Agent
from app.models.conversion_task import ConversionTask
from app.models.feedback import FeedbackAttachment, FeedbackIssue
from app.models.session import ChatSession
from app.models.user import User

__all__ = [
    "Base",
    "Agent",
    "ChatSession",
    "ConversionTask",
    "FeedbackAttachment",
    "FeedbackIssue",
    "User",
]
```

- [ ] **Step 5: Add compatibility migration**

Append this block near the end of `init_db()` in `backend/app/db/migrations.py`, before leaving the `engine.begin()` context:

```python
        # 问题反馈表迁移
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='feedback_issues'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE feedback_issues ("
                "id SERIAL PRIMARY KEY, "
                "title VARCHAR(200) NOT NULL, "
                "description TEXT NOT NULL DEFAULT '', "
                "reporter_username VARCHAR NOT NULL, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_feedback_issues_created "
                "ON feedback_issues (created_at DESC)"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_feedback_issues_reporter "
                "ON feedback_issues (reporter_username)"
            ))

        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='feedback_attachments'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE feedback_attachments ("
                "id SERIAL PRIMARY KEY, "
                "issue_id INTEGER NOT NULL REFERENCES feedback_issues(id) ON DELETE CASCADE, "
                "filename VARCHAR(255) NOT NULL, "
                "content_type VARCHAR(100) NOT NULL, "
                "file_path VARCHAR(500) NOT NULL, "
                "size INTEGER NOT NULL, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_feedback_attachments_issue "
                "ON feedback_attachments (issue_id)"
            ))
```

- [ ] **Step 6: Run the model smoke test**

Run:

```bash
pytest backend/tests/test_feedback_api.py::test_feedback_models_are_registered -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/feedback.py backend/app/models/__init__.py backend/app/db/migrations.py backend/tests/test_feedback_api.py
git commit -m "feat: 添加反馈数据模型"
```

## Task 2: Backend Feedback Service and Submit API

**Files:**
- Create: `backend/app/schemas/feedback.py`
- Modify: `backend/app/schemas/__init__.py`
- Create: `backend/app/modules/feedback/service.py`
- Create: `backend/app/modules/feedback/__init__.py`
- Create: `backend/app/api/routes/feedback.py`
- Modify: `backend/app/api/router.py`
- Test: `backend/tests/test_feedback_api.py`

- [ ] **Step 1: Write failing submit tests**

Append to `backend/tests/test_feedback_api.py`:

```python
async def test_create_feedback_issue_with_image(logged_in_client, tmp_path, monkeypatch):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads")

    res = await logged_in_client.post(
        "/api/feedback/issues",
        data={"title": "按钮无响应", "description": "点击后没有任何反馈"},
        files={"images": ("screen.png", b"\x89PNG\r\n", "image/png")},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "按钮无响应"
    assert body["description"] == "点击后没有任何反馈"
    assert body["reporter_username"] == "alice"
    assert body["attachment_count"] == 1
    assert list((tmp_path / "feedback_uploads" / str(body["id"])).iterdir())


async def test_create_feedback_rejects_non_image(logged_in_client, tmp_path, monkeypatch):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads")

    res = await logged_in_client.post(
        "/api/feedback/issues",
        data={"title": "错误附件", "description": ""},
        files={"images": ("note.txt", b"hello", "text/plain")},
    )

    assert res.status_code == 400
    assert "图片" in res.text
```

- [ ] **Step 2: Run submit tests and verify they fail**

Run:

```bash
pytest backend/tests/test_feedback_api.py::test_create_feedback_issue_with_image backend/tests/test_feedback_api.py::test_create_feedback_rejects_non_image -q
```

Expected: FAIL because routes and service do not exist.

- [ ] **Step 3: Add schemas**

Create `backend/app/schemas/feedback.py`:

```python
"""问题反馈 API schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FeedbackIssueCreatedOut(BaseModel):
    id: int
    title: str
    description: str
    reporter_username: str
    created_at: datetime
    attachment_count: int


class FeedbackAttachmentOut(BaseModel):
    id: int
    filename: str
    content_type: str
    size: int
    url: str


class FeedbackIssueListItemOut(BaseModel):
    id: int
    title: str
    reporter_username: str
    created_at: datetime


class FeedbackIssueListOut(BaseModel):
    items: list[FeedbackIssueListItemOut]
    total: int
    page: int
    page_size: int


class FeedbackIssueDetailOut(BaseModel):
    id: int
    title: str
    description: str
    reporter_username: str
    created_at: datetime
    attachments: list[FeedbackAttachmentOut]
```

Modify `backend/app/schemas/__init__.py` by adding:

```python
from app.schemas.feedback import (
    FeedbackAttachmentOut,
    FeedbackIssueCreatedOut,
    FeedbackIssueDetailOut,
    FeedbackIssueListItemOut,
    FeedbackIssueListOut,
)
```

and include those names in `__all__`.

- [ ] **Step 4: Add feedback service**

Create `backend/app/modules/feedback/__init__.py`:

```python
"""问题反馈模块。"""
```

Create `backend/app/modules/feedback/service.py`:

```python
"""问题反馈业务逻辑。"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.utils import safe_filename
from app.models.feedback import FeedbackAttachment, FeedbackIssue

FEEDBACK_UPLOAD_ROOT = Path("feedback_uploads")
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_TOTAL_IMAGE_SIZE = 30 * 1024 * 1024


def _validate_title(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="标题不能为空")
    if len(cleaned) > 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="标题不能超过200字")
    return cleaned


def _validate_image(file: UploadFile) -> str:
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只允许上传图片附件")
    return content_type


async def _save_image(file: UploadFile, issue_dir: Path) -> tuple[str, str, int]:
    content_type = _validate_image(file)
    filename = safe_filename(file.filename or "image")
    if not filename:
        filename = "image"
    target = issue_dir / filename
    index = 1
    while target.exists():
        target = issue_dir / f"{Path(filename).stem}-{index}{Path(filename).suffix}"
        index += 1

    size = 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_IMAGE_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="单张图片不能超过10MB",
                    )
                out.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    return filename, content_type, size


async def create_feedback_issue(
    session: AsyncSession,
    *,
    title: str,
    description: str,
    reporter_username: str,
    images: list[UploadFile],
) -> FeedbackIssue:
    cleaned_title = _validate_title(title)
    issue = FeedbackIssue(
        title=cleaned_title,
        description=description or "",
        reporter_username=reporter_username,
    )
    session.add(issue)
    await session.flush()

    issue_dir = FEEDBACK_UPLOAD_ROOT / str(issue.id)
    issue_dir.mkdir(parents=True, exist_ok=True)
    total_size = 0
    try:
        for image in images:
            filename, content_type, size = await _save_image(image, issue_dir)
            total_size += size
            if total_size > MAX_TOTAL_IMAGE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="图片总大小不能超过30MB",
                )
            relative_path = (Path(str(issue.id)) / filename).as_posix()
            session.add(FeedbackAttachment(
                issue_id=issue.id,
                filename=filename,
                content_type=content_type,
                file_path=relative_path,
                size=size,
            ))
        await session.commit()
    except Exception:
        await session.rollback()
        shutil.rmtree(issue_dir, ignore_errors=True)
        raise

    result = await session.execute(
        select(FeedbackIssue)
        .options(selectinload(FeedbackIssue.attachments))
        .where(FeedbackIssue.id == issue.id)
    )
    return result.scalar_one()


async def list_feedback_issues(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
) -> tuple[list[FeedbackIssue], int]:
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), 100)
    total = (await session.execute(select(func.count()).select_from(FeedbackIssue))).scalar_one()
    result = await session.execute(
        select(FeedbackIssue)
        .order_by(desc(FeedbackIssue.created_at), desc(FeedbackIssue.id))
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
    )
    return list(result.scalars().all()), total


async def get_feedback_issue(session: AsyncSession, issue_id: int) -> FeedbackIssue:
    result = await session.execute(
        select(FeedbackIssue)
        .options(selectinload(FeedbackIssue.attachments))
        .where(FeedbackIssue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    return issue


async def get_feedback_attachment(session: AsyncSession, attachment_id: int) -> tuple[FeedbackAttachment, Path]:
    attachment = await session.get(FeedbackAttachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")
    path = (FEEDBACK_UPLOAD_ROOT / attachment.file_path).resolve()
    root = FEEDBACK_UPLOAD_ROOT.resolve()
    if not path.is_relative_to(root) or not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件文件不存在")
    return attachment, path
```

- [ ] **Step 5: Add routes**

Create `backend/app/api/routes/feedback.py`:

```python
"""问题反馈 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, require_admin
from app.db.session import get_db
from app.models import User
from app.modules.feedback.service import (
    create_feedback_issue,
    get_feedback_attachment,
    get_feedback_issue,
    list_feedback_issues,
)
from app.schemas.feedback import (
    FeedbackAttachmentOut,
    FeedbackIssueCreatedOut,
    FeedbackIssueDetailOut,
    FeedbackIssueListItemOut,
    FeedbackIssueListOut,
)

router = APIRouter()


def _attachment_out(attachment) -> FeedbackAttachmentOut:
    return FeedbackAttachmentOut(
        id=attachment.id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size=attachment.size,
        url=f"/api/admin/feedback/attachments/{attachment.id}",
    )


@router.post("/feedback/issues", response_model=FeedbackIssueCreatedOut)
async def create_feedback_issue_route(
    title: str = Form(...),
    description: str = Form(""),
    images: list[UploadFile] = File(default=[]),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedbackIssueCreatedOut:
    issue = await create_feedback_issue(
        db,
        title=title,
        description=description,
        reporter_username=user.username,
        images=images,
    )
    return FeedbackIssueCreatedOut(
        id=issue.id,
        title=issue.title,
        description=issue.description,
        reporter_username=issue.reporter_username,
        created_at=issue.created_at,
        attachment_count=len(issue.attachments),
    )


@router.get("/admin/feedback/issues", response_model=FeedbackIssueListOut)
async def list_feedback_issues_route(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> FeedbackIssueListOut:
    items, total = await list_feedback_issues(db, page=page, page_size=page_size)
    return FeedbackIssueListOut(
        items=[
            FeedbackIssueListItemOut(
                id=item.id,
                title=item.title,
                reporter_username=item.reporter_username,
                created_at=item.created_at,
            )
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/admin/feedback/issues/{issue_id}", response_model=FeedbackIssueDetailOut)
async def get_feedback_issue_route(
    issue_id: int,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> FeedbackIssueDetailOut:
    issue = await get_feedback_issue(db, issue_id)
    return FeedbackIssueDetailOut(
        id=issue.id,
        title=issue.title,
        description=issue.description,
        reporter_username=issue.reporter_username,
        created_at=issue.created_at,
        attachments=[_attachment_out(attachment) for attachment in issue.attachments],
    )


@router.get("/admin/feedback/attachments/{attachment_id}")
async def get_feedback_attachment_route(
    attachment_id: int,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    attachment, path = await get_feedback_attachment(db, attachment_id)
    return FileResponse(path, media_type=attachment.content_type, filename=attachment.filename)
```

Modify `backend/app/api/router.py`:

```python
from app.api.routes import agents, auth, conversion_tasks, feedback, sessions, uploads, workspace, admin_skills, admin_plugins
router.include_router(feedback.router)
```

- [ ] **Step 6: Run submit tests**

Run:

```bash
pytest backend/tests/test_feedback_api.py::test_create_feedback_issue_with_image backend/tests/test_feedback_api.py::test_create_feedback_rejects_non_image -q
```

Expected: PASS if local `gokagent_test` database exists. If it errors with database connection or missing database, record the exact DB error and run:

```bash
python -m py_compile backend/app/modules/feedback/service.py backend/app/api/routes/feedback.py backend/app/schemas/feedback.py
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/feedback.py backend/app/schemas/__init__.py backend/app/modules/feedback backend/app/api/routes/feedback.py backend/app/api/router.py backend/tests/test_feedback_api.py
git commit -m "feat: 支持提交问题反馈"
```

## Task 3: Backend Admin Feedback APIs

**Files:**
- Modify: `backend/tests/test_feedback_api.py`
- Modify: `backend/app/api/routes/feedback.py`
- Modify: `backend/app/modules/feedback/service.py`

- [ ] **Step 1: Write failing admin API tests**

Append to `backend/tests/test_feedback_api.py`:

```python
async def test_admin_can_list_and_view_feedback(admin_client, tmp_path, monkeypatch):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads")

    create = await admin_client.post(
        "/api/feedback/issues",
        data={"title": "列表问题", "description": "详情描述"},
        files={"images": ("screen.png", b"\x89PNG\r\n", "image/png")},
    )
    issue_id = create.json()["id"]

    listing = await admin_client.get("/api/admin/feedback/issues?page=1&page_size=20")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] >= 1
    assert body["items"][0]["title"] == "列表问题"
    assert body["items"][0]["reporter_username"] == "admin"

    detail = await admin_client.get(f"/api/admin/feedback/issues/{issue_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["description"] == "详情描述"
    assert len(detail_body["attachments"]) == 1
    assert detail_body["attachments"][0]["url"].startswith("/api/admin/feedback/attachments/")


async def test_admin_can_fetch_feedback_attachment(admin_client, tmp_path, monkeypatch):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads")

    create = await admin_client.post(
        "/api/feedback/issues",
        data={"title": "截图", "description": ""},
        files={"images": ("screen.png", b"\x89PNG\r\n", "image/png")},
    )
    issue_id = create.json()["id"]
    detail = await admin_client.get(f"/api/admin/feedback/issues/{issue_id}")
    attachment_url = detail.json()["attachments"][0]["url"]

    image = await admin_client.get(attachment_url)

    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")
    assert image.content == b"\x89PNG\r\n"


async def test_non_admin_cannot_manage_feedback(logged_in_client):
    listing = await logged_in_client.get("/api/admin/feedback/issues")
    assert listing.status_code == 403
```

- [ ] **Step 2: Run admin tests**

Run:

```bash
pytest backend/tests/test_feedback_api.py::test_admin_can_list_and_view_feedback backend/tests/test_feedback_api.py::test_admin_can_fetch_feedback_attachment backend/tests/test_feedback_api.py::test_non_admin_cannot_manage_feedback -q
```

Expected: PASS if local test DB exists. If DB is unavailable, record the exact DB error and continue with py_compile verification.

- [ ] **Step 3: Commit**

If tests required small fixes, commit them:

```bash
git add backend/app/api/routes/feedback.py backend/app/modules/feedback/service.py backend/tests/test_feedback_api.py
git commit -m "feat: 支持管理员查看反馈"
```

If no source changes were needed beyond tests:

```bash
git add backend/tests/test_feedback_api.py
git commit -m "test: 覆盖反馈管理接口"
```

## Task 4: Frontend Feedback API Types and Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add frontend feedback types**

Modify `frontend/src/types/index.ts`:

```ts
export type ViewName = "new" | "chat" | "workspace" | "agents" | "skills" | "feedback";

export interface FeedbackIssueCreated {
  id: number;
  title: string;
  description: string;
  reporter_username: string;
  created_at: string;
  attachment_count: number;
}

export interface FeedbackAttachment {
  id: number;
  filename: string;
  content_type: string;
  size: number;
  url: string;
}

export interface FeedbackIssueListItem {
  id: number;
  title: string;
  reporter_username: string;
  created_at: string;
}

export interface FeedbackIssueList {
  items: FeedbackIssueListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface FeedbackIssueDetail {
  id: number;
  title: string;
  description: string;
  reporter_username: string;
  created_at: string;
  attachments: FeedbackAttachment[];
}
```

- [ ] **Step 2: Add API client methods**

Modify imports in `frontend/src/api/client.ts` to include the new types:

```ts
  FeedbackIssueCreated,
  FeedbackIssueDetail,
  FeedbackIssueList,
```

Add these methods inside `api`:

```ts
  createFeedbackIssue: async (data: {
    title: string;
    description: string;
    images: File[];
  }) => {
    const form = new FormData();
    form.append("title", data.title);
    form.append("description", data.description);
    data.images.forEach((image) => form.append("images", image, image.name));
    const res = await fetch("/api/feedback/issues", {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    handleUnauthorizedResponse(res);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
    }
    return res.json() as Promise<FeedbackIssueCreated>;
  },

  adminFeedbackIssues: (page: number, pageSize: number) =>
    request<FeedbackIssueList>(
      `/api/admin/feedback/issues?page=${page}&page_size=${pageSize}`,
    ),

  adminFeedbackIssue: (id: number) =>
    request<FeedbackIssueDetail>(`/api/admin/feedback/issues/${id}`),

  adminFeedbackAttachmentUrl: (id: number) =>
    `/api/admin/feedback/attachments/${id}`,
```

- [ ] **Step 3: Run frontend build and verify expected failures**

Run:

```bash
cd frontend && npm run build
```

Expected: It may fail because no UI references the new `"feedback"` view yet or because imports need exact ordering. Fix TypeScript import ordering if needed, but do not build UI in this task.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts
git commit -m "feat: 添加反馈前端接口"
```

## Task 5: Feedback Dialog in Topbar

**Files:**
- Create: `frontend/src/components/FeedbackDialog.tsx`
- Modify: `frontend/src/components/Topbar.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create feedback dialog component**

Create `frontend/src/components/FeedbackDialog.tsx`:

```tsx
import { useEffect, useMemo, useState, type ClipboardEvent } from "react";
import { api } from "@/api/client";
import { I } from "@/icons";
import { Btn, Input, useToast } from "@/components/ui";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface ImageDraft {
  id: string;
  file: File;
  url: string;
}

export default function FeedbackDialog({ open, onClose }: Props) {
  const { showToast } = useToast();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [images, setImages] = useState<ImageDraft[]>([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    return () => {
      images.forEach((image) => URL.revokeObjectURL(image.url));
    };
  }, [images, open]);

  const canSubmit = title.trim() !== "" && !submitting;

  const imageFiles = useMemo(() => images.map((image) => image.file), [images]);

  const addImages = (files: File[]) => {
    const imageFiles = files.filter((file) => file.type.startsWith("image/"));
    if (imageFiles.length !== files.length) {
      showToast("仅支持粘贴图片", "error");
    }
    setImages((prev) => [
      ...prev,
      ...imageFiles.map((file) => ({
        id: `${file.name}-${file.size}-${crypto.randomUUID()}`,
        file,
        url: URL.createObjectURL(file),
      })),
    ]);
  };

  const onPaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(event.clipboardData.items)
      .filter((item) => item.kind === "file")
      .map((item) => item.getAsFile())
      .filter((file): file is File => file !== null);
    if (files.length === 0) return;
    event.preventDefault();
    addImages(files);
  };

  const removeImage = (id: string) => {
    setImages((prev) => {
      const target = prev.find((image) => image.id === id);
      if (target) URL.revokeObjectURL(target.url);
      return prev.filter((image) => image.id !== id);
    });
  };

  const resetAndClose = () => {
    images.forEach((image) => URL.revokeObjectURL(image.url));
    setTitle("");
    setDescription("");
    setImages([]);
    setSubmitting(false);
    onClose();
  };

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      await api.createFeedbackIssue({
        title: title.trim(),
        description,
        images: imageFiles,
      });
      showToast("反馈已提交", "success");
      resetAndClose();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "反馈提交失败", "error");
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(0,0,0,.28)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) resetAndClose();
      }}
    >
      <div
        style={{
          width: "min(560px, 100%)",
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: 12,
          boxShadow: "var(--shadow-md)",
          padding: 18,
          display: "flex",
          flexDirection: "column",
          gap: 14,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <I.MessageSquare size={18} />
          <div style={{ fontSize: 16, fontWeight: 600, color: "var(--ink)", flex: 1 }}>
            问题反馈
          </div>
          <button
            type="button"
            onClick={resetAndClose}
            style={{
              border: "none",
              background: "transparent",
              color: "var(--ink-3)",
              cursor: "pointer",
              display: "flex",
              padding: 4,
            }}
          >
            <I.X size={18} />
          </button>
        </div>
        <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ fontSize: 13, color: "var(--ink-2)" }}>标题</span>
          <Input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ fontSize: 13, color: "var(--ink-2)" }}>详细描述</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            onPaste={onPaste}
            placeholder="描述你遇到的问题，可直接粘贴截图"
            rows={7}
            style={{
              width: "100%",
              resize: "vertical",
              border: "1px solid var(--line)",
              borderRadius: 8,
              background: "var(--bg)",
              color: "var(--ink)",
              padding: "10px 12px",
              fontFamily: "inherit",
              fontSize: 14,
              lineHeight: 1.5,
              outline: "none",
            }}
          />
        </label>
        {images.length > 0 && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {images.map((image) => (
              <div key={image.id} style={{ position: "relative" }}>
                <img
                  src={image.url}
                  alt={image.file.name}
                  style={{
                    width: 88,
                    height: 66,
                    objectFit: "cover",
                    border: "1px solid var(--line)",
                    borderRadius: 8,
                  }}
                />
                <button
                  type="button"
                  onClick={() => removeImage(image.id)}
                  title="移除图片"
                  style={{
                    position: "absolute",
                    top: -6,
                    right: -6,
                    width: 20,
                    height: 20,
                    borderRadius: 999,
                    border: "1px solid var(--line)",
                    background: "var(--surface)",
                    color: "var(--ink-2)",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <I.X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Btn variant="ghost" onClick={resetAndClose} disabled={submitting}>
            取消
          </Btn>
          <Btn onClick={submit} disabled={!canSubmit}>
            {submitting ? "提交中…" : "提交反馈"}
          </Btn>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Wire dialog into Topbar**

Modify the imports and component opening in `frontend/src/components/Topbar.tsx`:

```tsx
// 顶部栏:面包屑 + 反馈入口 + 主题切换
import { Fragment, useState } from "react";
import FeedbackDialog from "@/components/FeedbackDialog";
import type { ThemeMode } from "@/types";
import { I } from "@/icons";

interface Props {
  breadcrumb: string[];
  theme: ThemeMode;
  onToggleTheme: () => void;
}

export default function Topbar({ breadcrumb, theme, onToggleTheme }: Props) {
  const [feedbackOpen, setFeedbackOpen] = useState(false);
```

Inside the existing right-side button group, insert this feedback button immediately before the existing theme toggle button:

```tsx
        <button
          onClick={() => setFeedbackOpen(true)}
          className="focus-ring"
          title="问题反馈"
          style={{
            background: "transparent",
            border: "1px solid var(--line)",
            color: "var(--ink-2)",
            cursor: "pointer",
            padding: 0,
            width: 32,
            height: 32,
            borderRadius: 8,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <I.MessageSquare size={15} />
        </button>
```

Insert the dialog mount as the last child inside the existing `<header>` element, after the right-side button group:

```tsx
      <FeedbackDialog open={feedbackOpen} onClose={() => setFeedbackOpen(false)} />
```

Keep the existing breadcrumb mapping and theme button unchanged. The only additions are the `useState` import, `FeedbackDialog` import, `feedbackOpen` state, feedback icon button, and dialog mount.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. If `I.MessageSquare` is not available, inspect `frontend/src/icons/index.tsx` and use the closest existing icon such as `I.MessageCircle`, `I.CircleAlert`, or add a lucide import consistent with that file.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/FeedbackDialog.tsx frontend/src/components/Topbar.tsx
git commit -m "feat: 添加问题反馈入口"
```

## Task 6: Admin Feedback Management Page

**Files:**
- Create: `frontend/src/pages/FeedbackPage.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create admin page**

Create `frontend/src/pages/FeedbackPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { I } from "@/icons";
import { Btn, Spinner, useToast } from "@/components/ui";
import type { FeedbackIssueDetail, FeedbackIssueListItem } from "@/types";

const PAGE_SIZE = 20;

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

export default function FeedbackPage() {
  const { showToast } = useToast();
  const [items, setItems] = useState<FeedbackIssueListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<FeedbackIssueDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadList = async (nextPage = page) => {
    setLoading(true);
    try {
      const result = await api.adminFeedbackIssues(nextPage, PAGE_SIZE);
      setItems(result.items);
      setTotal(result.total);
      setPage(result.page);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "加载反馈列表失败", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadList(1);
  }, []);

  const openDetail = async (id: number) => {
    setDetailLoading(true);
    try {
      setDetail(await api.adminFeedbackIssue(id));
    } catch (err) {
      showToast(err instanceof Error ? err.message : "加载反馈详情失败", "error");
    } finally {
      setDetailLoading(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div style={{ flex: 1, minWidth: 0, padding: 24, overflow: "auto" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {detail && (
            <button
              type="button"
              onClick={() => setDetail(null)}
              style={{
                border: "1px solid var(--line)",
                background: "var(--surface)",
                borderRadius: 8,
                width: 32,
                height: 32,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <I.ChevronLeft size={16} />
            </button>
          )}
          <h1 style={{ margin: 0, fontSize: 20, color: "var(--ink)" }}>
            {detail ? "反馈详情" : "反馈管理"}
          </h1>
        </div>

        {!detail && (
          <section
            style={{
              background: "var(--surface)",
              border: "1px solid var(--line)",
              borderRadius: 10,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 160px 190px",
                gap: 12,
                padding: "10px 14px",
                borderBottom: "1px solid var(--line)",
                fontSize: 12,
                color: "var(--ink-3)",
                fontWeight: 600,
              }}
            >
              <span>标题</span>
              <span>提出人</span>
              <span>提出时间</span>
            </div>
            {loading ? (
              <div style={{ padding: 32, display: "flex", justifyContent: "center" }}>
                <Spinner />
              </div>
            ) : items.length === 0 ? (
              <div style={{ padding: 32, color: "var(--ink-3)", textAlign: "center" }}>
                暂无反馈
              </div>
            ) : (
              items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => openDetail(item.id)}
                  style={{
                    width: "100%",
                    display: "grid",
                    gridTemplateColumns: "1fr 160px 190px",
                    gap: 12,
                    padding: "12px 14px",
                    border: "none",
                    borderBottom: "1px solid var(--line)",
                    background: "transparent",
                    textAlign: "left",
                    cursor: "pointer",
                    fontFamily: "inherit",
                    color: "var(--ink)",
                    alignItems: "center",
                  }}
                >
                  <span style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {item.title}
                  </span>
                  <span style={{ color: "var(--ink-2)" }}>{item.reporter_username}</span>
                  <span style={{ color: "var(--ink-3)" }}>{formatDate(item.created_at)}</span>
                </button>
              ))
            )}
          </section>
        )}

        {!detail && (
          <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 13, color: "var(--ink-3)" }}>
              第 {page} / {totalPages} 页，共 {total} 条
            </span>
            <Btn variant="ghost" disabled={page <= 1 || loading} onClick={() => loadList(page - 1)}>
              上一页
            </Btn>
            <Btn variant="ghost" disabled={page >= totalPages || loading} onClick={() => loadList(page + 1)}>
              下一页
            </Btn>
          </div>
        )}

        {detailLoading && (
          <div style={{ padding: 32, display: "flex", justifyContent: "center" }}>
            <Spinner />
          </div>
        )}

        {detail && !detailLoading && (
          <section
            style={{
              background: "var(--surface)",
              border: "1px solid var(--line)",
              borderRadius: 10,
              padding: 18,
              display: "flex",
              flexDirection: "column",
              gap: 14,
            }}
          >
            <div>
              <div style={{ fontSize: 22, fontWeight: 700, color: "var(--ink)" }}>{detail.title}</div>
              <div style={{ marginTop: 6, fontSize: 13, color: "var(--ink-3)" }}>
                {detail.reporter_username} · {formatDate(detail.created_at)}
              </div>
            </div>
            <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.7, color: "var(--ink-2)" }}>
              {detail.description || "未填写详细描述"}
            </div>
            {detail.attachments.length > 0 && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 12 }}>
                {detail.attachments.map((attachment) => (
                  <a key={attachment.id} href={attachment.url} target="_blank" rel="noreferrer">
                    <img
                      src={attachment.url}
                      alt={attachment.filename}
                      style={{
                        width: "100%",
                        maxHeight: 260,
                        objectFit: "contain",
                        border: "1px solid var(--line)",
                        borderRadius: 8,
                        background: "var(--bg)",
                      }}
                    />
                  </a>
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add admin sidebar nav**

Modify `frontend/src/components/Sidebar.tsx`:

```tsx
  if (user.role === "admin") {
    items.push({ id: "skills", label: "技能管理", icon: I.Puzzle, group: "管理" });
    items.push({ id: "feedback", label: "反馈管理", icon: I.MessageSquare, group: "管理" });
  }
```

If `I.MessageSquare` does not exist, use the same icon selected in Task 5.

- [ ] **Step 3: Wire App view and breadcrumb**

Modify `frontend/src/App.tsx`:

```tsx
import FeedbackPage from "@/pages/FeedbackPage";
```

Update breadcrumb:

```tsx
  const breadcrumb =
    view === "workspace"
      ? ["工作空间", "文件管理"]
      : view === "agents"
      ? ["管理", "智能体"]
      : view === "skills"
      ? ["管理", "技能管理"]
      : view === "feedback"
      ? ["管理", "反馈管理"]
      : view === "chat"
      ? ["对话工作台", "进行中"]
      : ["对话工作台", "新建对话"];
```

Update render branch:

```tsx
          {view === "workspace" ? (
            <WorkspacePage />
          ) : view === "agents" ? (
            <AgentsPage />
          ) : view === "skills" ? (
            <SkillsPage />
          ) : view === "feedback" ? (
            <FeedbackPage />
          ) : (
            <ChatWorkspace
              initialMode={view === "new" ? "empty" : "chat"}
              onModeChange={(m) => setView(m === "empty" ? "new" : "chat")}
              me={auth.me}
            />
          )}
```

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/FeedbackPage.tsx frontend/src/components/Sidebar.tsx frontend/src/App.tsx frontend/src/types/index.ts
git commit -m "feat: 添加反馈管理页面"
```

## Task 7: Final Verification

**Files:**
- No source edits expected.

- [ ] **Step 1: Run backend focused checks**

Run:

```bash
pytest backend/tests/test_feedback_api.py -q
```

Expected: PASS when local PostgreSQL test database `gokagent_test` exists and is reachable.

If the command fails with a local database setup error such as missing `gokagent_test`, also run:

```bash
python -m py_compile \
  backend/app/models/feedback.py \
  backend/app/schemas/feedback.py \
  backend/app/modules/feedback/service.py \
  backend/app/api/routes/feedback.py
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Check generated files and status**

Run:

```bash
git status --short
```

Expected: no uncommitted task files. If `backend/logs/` appears from test logging, remove it with:

```bash
rm -r backend/logs
```

Then re-run:

```bash
git status --short
```

- [ ] **Step 4: Commit final verification fixes if any**

If final verification required small source fixes:

```bash
git add backend/app frontend/src backend/tests/test_feedback_api.py
git commit -m "fix: 完善问题反馈功能"
```

If no changes were needed, do not create an empty commit.

## Self-Review

Spec coverage:

- Topbar feedback icon: Task 5.
- Feedback panel title/description: Task 5.
- Paste image support and preview/delete: Task 5.
- Persisted backend issue and attachments: Tasks 1 and 2.
- Admin sidebar entry: Task 6.
- Admin paginated list: Tasks 3 and 6.
- Admin detail view: Tasks 3 and 6.
- Attachment image viewing: Tasks 2, 3, and 6.
- Permission split between logged-in users and admins: Tasks 2 and 3.

Placeholder scan:

- The plan contains no unresolved placeholder markers.
- Every task has concrete files, code, commands, and expected outcomes.

Type consistency:

- Backend model names are `FeedbackIssue` and `FeedbackAttachment`.
- Backend schema names match route response models.
- Frontend types match backend JSON field names: `reporter_username`, `created_at`, `attachment_count`, `page_size`.
- Frontend `ViewName` includes `"feedback"` and the same value is used in `Sidebar` and `App`.
