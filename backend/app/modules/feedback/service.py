"""问题反馈业务逻辑。"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.utils import safe_filename
from app.models.feedback import FeedbackAttachment, FeedbackIssue

# 默认从环境变量 FEEDBACK_UPLOADS_DIR 读取；保留该变量便于测试按需覆盖。
FEEDBACK_UPLOAD_ROOT: Path | None = None
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_TOTAL_IMAGE_SIZE = 30 * 1024 * 1024
MAX_FILENAME_LENGTH = 200
MAX_FILENAME_BYTES = 240


def _feedback_upload_root() -> Path:
    return FEEDBACK_UPLOAD_ROOT or get_settings().feedback_uploads_dir


def _filename_is_within_limit(filename: str) -> bool:
    return (
        len(filename) <= MAX_FILENAME_LENGTH
        and len(filename.encode("utf-8")) <= MAX_FILENAME_BYTES
    )


def _ensure_filename_within_limit(filename: str) -> None:
    if not _filename_is_within_limit(filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图片文件名过长")


def _validate_title(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="标题不能为空")
    if len(cleaned) > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="标题不能超过200字"
        )
    return cleaned


def _validate_image(file: UploadFile) -> str:
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只允许上传图片附件")
    return content_type


def _clean_image_filename(file: UploadFile) -> str:
    raw_filename = file.filename or "image"
    filename = safe_filename(raw_filename)
    if not filename:
        filename = "image"
    _ensure_filename_within_limit(filename)
    return filename


def _dedupe_filename(stem: str, suffix: str, duplicate_suffix: str) -> str:
    trimmed_stem = stem
    while trimmed_stem:
        filename = f"{trimmed_stem}{duplicate_suffix}{suffix}"
        if _filename_is_within_limit(filename):
            return filename
        trimmed_stem = trimmed_stem[:-1]
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图片文件名过长")


def _unique_image_target(issue_dir: Path, filename: str) -> Path:
    target = issue_dir / filename
    if not target.exists():
        return target

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    index = 1
    while True:
        duplicate_suffix = f"-{index}"
        target = issue_dir / _dedupe_filename(stem, suffix, duplicate_suffix)
        if not target.exists():
            return target
        index += 1


async def _save_image(file: UploadFile, issue_dir: Path) -> tuple[str, str, int]:
    content_type = _validate_image(file)
    filename = _clean_image_filename(file)
    target = _unique_image_target(issue_dir, filename)

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

    return target.name, content_type, size


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

    issue_id = issue.id
    issue_dir = _feedback_upload_root() / str(issue_id)
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
            relative_path = (Path(str(issue_id)) / filename).as_posix()
            session.add(
                FeedbackAttachment(
                    issue_id=issue_id,
                    filename=filename,
                    content_type=content_type,
                    file_path=relative_path,
                    size=size,
                )
            )
        await session.commit()
    except Exception:
        await session.rollback()
        # 文件写入和数据库提交必须一起成功，失败时清理本次反馈目录。
        shutil.rmtree(issue_dir, ignore_errors=True)
        raise

    result = await session.execute(
        select(FeedbackIssue)
        .options(selectinload(FeedbackIssue.attachments))
        .where(FeedbackIssue.id == issue_id)
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
    total = (
        await session.execute(select(func.count()).select_from(FeedbackIssue))
    ).scalar_one()
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


async def delete_feedback_issue(session: AsyncSession, issue_id: int) -> None:
    issue = await get_feedback_issue(session, issue_id)
    issue_dir = _feedback_upload_root() / str(issue.id)
    await session.delete(issue)
    await session.commit()
    # 数据库删除成功后再清理文件目录；文件清理失败不应恢复已删除的反馈记录。
    shutil.rmtree(issue_dir, ignore_errors=True)


async def get_feedback_attachment(
    session: AsyncSession, attachment_id: int
) -> tuple[FeedbackAttachment, Path]:
    attachment = await session.get(FeedbackAttachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")
    upload_root = _feedback_upload_root()
    path = (upload_root / attachment.file_path).resolve()
    root = upload_root.resolve()
    if not path.is_relative_to(root) or not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件文件不存在")
    return attachment, path
