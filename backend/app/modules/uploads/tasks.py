"""上传任务持久化服务。"""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import safe_filename
from app.models import UploadTask
from app.modules.conversions.service import (
    create_conversion_task,
    is_convertible_path,
    schedule_conversion_task,
)
from app.modules.uploads.service import _dedupe_path, _safe_relative_parts
from app.modules.uploads.service import _MAX_FILE_SIZE, _open_upload_tmp_file
from app.modules.workspace.paths import resolve_inside_workspace
from app.schemas import UploadTaskAbandonIn, UploadTaskCreateIn, UploadTaskProgressIn

logger = logging.getLogger(__name__)


def _dedupe_reserved_path(target: Path, reserved: set[Path]) -> Path:
    """同时避开磁盘已有文件和本批次已分配路径。"""
    candidate = _dedupe_path(target)
    if candidate not in reserved:
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    parent = candidate.parent
    idx = 1
    while True:
        next_candidate = parent / f"{stem} ({idx}){suffix}"
        if next_candidate not in reserved and not next_candidate.exists():
            return next_candidate
        idx += 1


def _workspace_relative_path(workspace: Path, target: Path) -> str:
    """解析最终路径并确认没有通过符号链接越出 workspace。"""
    try:
        return target.resolve().relative_to(workspace.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="路径越出工作区") from exc


async def create_upload_tasks(
    session: AsyncSession,
    username: str,
    workspace: Path,
    data: UploadTaskCreateIn,
    *,
    workspace_kind: str = "personal",
    team_space_id: int | None = None,
) -> list[UploadTask]:
    """创建排队态上传任务，只计算目标路径，不写入文件内容。"""
    if not data.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未提供任何文件")

    target_dir = data.target_dir.strip()
    base_dir = workspace if not target_dir else resolve_inside_workspace(workspace, target_dir)
    tasks: list[UploadTask] = []
    reserved_paths: set[Path] = set()

    for item in data.items:
        original = safe_filename(item.filename or "file")
        rel_input = item.relative_path or original
        try:
            parts = _safe_relative_parts(rel_input)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        # 保持目录结构,但最终文件名仍按上传文件名清洗，避免客户端传入危险文件名。
        parts[-1] = safe_filename(parts[-1] or original)
        target = _dedupe_reserved_path(base_dir.joinpath(*parts), reserved_paths)
        saved_path = _workspace_relative_path(workspace, target)
        reserved_paths.add(target)

        tasks.append(
            UploadTask(
                username=username,
                workspace_kind=workspace_kind,
                team_space_id=team_space_id,
                target_dir=target_dir,
                relative_path=item.relative_path,
                filename=original,
                status="queued",
                progress=0,
                size=item.size or 0,
                saved_path=saved_path,
            )
        )

    session.add_all(tasks)
    await session.commit()
    for task in tasks:
        await session.refresh(task)
    return tasks


async def _get_user_upload_task(
    session: AsyncSession,
    username: str,
    task_id: int,
    *,
    workspace_kind: str = "personal",
    team_space_id: int | None = None,
) -> UploadTask:
    task = await session.get(UploadTask, task_id)
    if (
        task is None
        or task.username != username
        or task.workspace_kind != workspace_kind
        or task.team_space_id != team_space_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="上传任务不存在")
    return task


async def get_upload_task_target_path(
    session: AsyncSession,
    *,
    username: str,
    task_id: int,
    workspace_kind: str = "personal",
    team_space_id: int | None = None,
) -> str:
    """返回上传任务最终写入路径，供团队空间写入前加锁。"""
    task = await _get_user_upload_task(
        session,
        username,
        task_id,
        workspace_kind=workspace_kind,
        team_space_id=team_space_id,
    )
    if not task.saved_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传任务缺少保存路径")
    return task.saved_path


async def _claim_upload_task(
    session: AsyncSession,
    username: str,
    task_id: int,
    *,
    workspace_kind: str = "personal",
    team_space_id: int | None = None,
) -> UploadTask:
    """领取 queued 上传任务，确保同一用户同时只有一个 running 上传。"""
    try:
        claim_result = await session.execute(
            update(UploadTask)
            .where(
                UploadTask.id == task_id,
                UploadTask.username == username,
                UploadTask.workspace_kind == workspace_kind,
                UploadTask.team_space_id == team_space_id,
                UploadTask.status == "queued",
            )
            .values(
                status="running",
                started_at=datetime.now(UTC),
                finished_at=None,
                error_message=None,
            )
            .returning(UploadTask.id)
        )
        claimed_id = claim_result.scalar_one_or_none()
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已有上传任务正在执行") from exc
    if claimed_id is None:
        task = await session.get(UploadTask, task_id)
        if (
            task is None
            or task.username != username
            or task.workspace_kind != workspace_kind
            or task.team_space_id != team_space_id
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="上传任务不存在")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="上传任务状态不可执行")
    task = await session.get(UploadTask, claimed_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="上传任务不存在")
    return task


async def save_upload_task_file(
    session: AsyncSession,
    *,
    username: str,
    workspace: Path,
    task_id: int,
    file: UploadFile,
    background_tasks=None,
    workspace_kind: str = "personal",
    team_space_id: int | None = None,
) -> UploadTask:
    """执行单个上传任务：先写临时文件，完整成功后原子替换到目标路径。"""
    try:
        task = await _claim_upload_task(
            session,
            username,
            task_id,
            workspace_kind=workspace_kind,
            team_space_id=team_space_id,
        )
        if not task.saved_path:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传任务缺少保存路径")

        target = resolve_inside_workspace(workspace, task.saved_path)
        tmp_target: Path | None = None
        total = 0
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            tmp_target, out = _open_upload_tmp_file(target)
            with out:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_FILE_SIZE:
                        raise ValueError(f"文件 {task.filename} 超过 {_MAX_FILE_SIZE // (1024 * 1024)} MB 上限")
                    out.write(chunk)
        except Exception as exc:
            if tmp_target is not None:
                tmp_target.unlink(missing_ok=True)
            task.status = "failed"
            task.error_message = str(exc)
            task.finished_at = datetime.now(UTC)
            await session.commit()
            status_code = (
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                if total > _MAX_FILE_SIZE
                else status.HTTP_400_BAD_REQUEST
            )
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

        finished_at = datetime.now(UTC)
        complete_result = await session.execute(
            update(UploadTask)
            .where(
                UploadTask.id == task.id,
                UploadTask.username == username,
                UploadTask.workspace_kind == workspace_kind,
                UploadTask.team_space_id == team_space_id,
                UploadTask.status == "running",
            )
            .values(
                status="succeeded",
                progress=100,
                size=total,
                error_message=None,
                finished_at=finished_at,
            )
            .returning(UploadTask.id)
        )
        if complete_result.scalar_one_or_none() is None:
            # 上传期间可能被 abandon 标记失败，此时只清理临时文件，不能触碰目标路径。
            await session.rollback()
            tmp_target.unlink(missing_ok=True)
            await session.refresh(task)
            return task
        if target.exists():
            await session.execute(
                update(UploadTask)
                .where(UploadTask.id == task.id)
                .values(
                    status="failed",
                    error_message="目标文件已存在，请重新上传",
                    finished_at=finished_at,
                )
            )
            await session.commit()
            tmp_target.unlink(missing_ok=True)
            await session.refresh(task)
            return task
        try:
            # 使用无覆盖发布，避免检查后目标文件被其他流程创建时被替换。
            os.link(tmp_target, target)
            tmp_target.unlink(missing_ok=True)
        except FileExistsError:
            await session.execute(
                update(UploadTask)
                .where(UploadTask.id == task.id)
                .values(
                    status="failed",
                    error_message="目标文件已存在，请重新上传",
                    finished_at=finished_at,
                )
            )
            await session.commit()
            tmp_target.unlink(missing_ok=True)
            await session.refresh(task)
            return task
        await session.commit()
        await session.refresh(task)

        if is_convertible_path(target):
            try:
                conversion = await create_conversion_task(
                    session,
                    username=username,
                    workspace=workspace,
                    source_path=task.saved_path,
                    workspace_kind=task.workspace_kind,
                    team_space_id=task.team_space_id,
                )
            except HTTPException as exc:
                if exc.status_code != status.HTTP_409_CONFLICT:
                    await session.rollback()
                    logger.exception("Create conversion task failed after upload succeeded")
                    await session.refresh(task)
            except Exception:
                await session.rollback()
                logger.exception("Create conversion task failed after upload succeeded")
                await session.refresh(task)
            else:
                schedule_conversion_task(background_tasks, conversion.id)
        return task
    finally:
        await file.close()


async def update_upload_task_progress(
    session: AsyncSession,
    *,
    username: str,
    task_id: int,
    data: UploadTaskProgressIn,
    workspace_kind: str = "personal",
    team_space_id: int | None = None,
) -> UploadTask:
    task = await _get_user_upload_task(
        session,
        username,
        task_id,
        workspace_kind=workspace_kind,
        team_space_id=team_space_id,
    )
    if task.status != "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只能更新执行中的上传任务进度")
    task.progress = data.progress
    await session.commit()
    await session.refresh(task)
    return task


async def abandon_upload_tasks(
    session: AsyncSession,
    *,
    username: str,
    data: UploadTaskAbandonIn,
    workspace_kind: str = "personal",
    team_space_id: int | None = None,
) -> list[UploadTask]:
    """页面刷新或客户端上传异常时，将当前用户未完成的上传任务标记为失败。"""
    result = await session.execute(
        select(UploadTask).where(
            UploadTask.username == username,
            UploadTask.workspace_kind == workspace_kind,
            UploadTask.team_space_id == team_space_id,
            UploadTask.id.in_(data.ids),
        )
    )
    tasks = list(result.scalars().all())
    now = datetime.now(UTC)
    error_message = data.error_message or "页面刷新导致上传中断，请重新上传"
    for task in tasks:
        if task.status in {"queued", "running"}:
            task.status = "failed"
            task.error_message = error_message
            task.finished_at = now
    await session.commit()
    for task in tasks:
        await session.refresh(task)
    return tasks
