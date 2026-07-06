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
