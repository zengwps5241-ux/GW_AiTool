"""问题反馈 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, require_admin
from app.db.session import get_db
from app.models import User
from app.modules.feedback.service import (
    create_feedback_issue,
    delete_feedback_issue,
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

router = APIRouter(prefix="/api")


def _attachment_out(attachment) -> FeedbackAttachmentOut:
    return FeedbackAttachmentOut(
        id=attachment.id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size=attachment.size,
        url=f"/api/admin/feedback/attachments/{attachment.id}",
    )


async def _display_names_by_username(
    db: AsyncSession, usernames: set[str]
) -> dict[str, str]:
    if not usernames:
        return {}
    result = await db.execute(select(User).where(User.username.in_(usernames)))
    users = result.scalars().all()
    return {
        user.username: (user.display_name or user.username)
        for user in users
    }


async def _display_name_for_username(db: AsyncSession, username: str) -> str:
    names = await _display_names_by_username(db, {username})
    return names.get(username, username)


@router.post("/feedback/issues", response_model=FeedbackIssueCreatedOut)
async def create_feedback_issue_route(
    title: str = Form(...),
    description: str = Form(""),
    images: list[UploadFile] | None = File(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedbackIssueCreatedOut:
    issue = await create_feedback_issue(
        db,
        title=title,
        description=description,
        reporter_username=user.username,
        images=images or [],
    )
    return FeedbackIssueCreatedOut(
        id=issue.id,
        title=issue.title,
        description=issue.description,
        reporter_username=user.display_name or user.username,
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
    display_names = await _display_names_by_username(
        db, {item.reporter_username for item in items}
    )
    return FeedbackIssueListOut(
        items=[
            FeedbackIssueListItemOut(
                id=item.id,
                title=item.title,
                reporter_username=display_names.get(
                    item.reporter_username, item.reporter_username
                ),
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
    reporter_name = await _display_name_for_username(db, issue.reporter_username)
    return FeedbackIssueDetailOut(
        id=issue.id,
        title=issue.title,
        description=issue.description,
        reporter_username=reporter_name,
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
    return FileResponse(
        path,
        media_type=attachment.content_type,
        filename=attachment.filename,
        content_disposition_type="inline",
    )


@router.delete("/admin/feedback/issues/{issue_id}", status_code=204)
async def delete_feedback_issue_route(
    issue_id: int,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    await delete_feedback_issue(db, issue_id)
