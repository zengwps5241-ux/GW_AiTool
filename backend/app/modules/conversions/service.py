"""Office/PDF 转 Markdown 任务服务。"""

import asyncio
import logging
import shutil
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis as redis_core
from app.core.config import get_settings, user_workspace
from app.db.session import async_session
from app.integrations.mineru import convert_document_to_markdown
from app.models.conversion_task import ConversionTask
from app.modules.team_spaces.file_locks import FileLockService
from app.modules.team_spaces.service import team_workspace
from app.modules.conversions.office_pdf import needs_pdf_intermediate, temporary_pdf_for_doc
from app.modules.workspace.markdown_index import (
    add_markdown_mapping,
    ensure_markdown_root,
    find_markdown_mappings_under,
    remove_markdown_mappings,
)
from app.modules.workspace.paths import resolve_inside_workspace

logger = logging.getLogger(__name__)

CONVERTIBLE_SUFFIXES = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
_dispatcher_queue: asyncio.Queue[int] | None = None
_dispatcher_workers: list[asyncio.Task] = []
_scheduled_task_ids: set[int] = set()


def is_convertible_path(path: str | Path) -> bool:
    """判断文件是否需要走 MinerU 转换。"""
    return Path(path).suffix.lower() in CONVERTIBLE_SUFFIXES


async def convert_source_to_markdown(
    source: Path,
    output_root: Path,
    *,
    api_url: str,
    timeout_seconds: float,
    max_concurrent_requests: int,
):
    """按源文件类型调用 MinerU；旧版 .doc 先转临时 PDF。"""
    if needs_pdf_intermediate(source):
        async with temporary_pdf_for_doc(source) as pdf_source:
            return await convert_document_to_markdown(
                source_path=pdf_source,
                output_root=output_root,
                api_url=api_url,
                timeout_seconds=timeout_seconds,
                max_concurrent_requests=max_concurrent_requests,
            )
    return await convert_document_to_markdown(
        source_path=source,
        output_root=output_root,
        api_url=api_url,
        timeout_seconds=timeout_seconds,
        max_concurrent_requests=max_concurrent_requests,
    )


async def list_user_tasks(
    session: AsyncSession,
    username: str,
    limit: int | None = None,
    offset: int | None = None,
    *,
    workspace_kind: str = "personal",
    team_space_id: int | None = None,
) -> list[ConversionTask]:
    stmt = (
        select(ConversionTask)
        .where(
            ConversionTask.username == username,
            ConversionTask.workspace_kind == workspace_kind,
            ConversionTask.team_space_id == team_space_id,
        )
        .order_by(desc(ConversionTask.created_at), desc(ConversionTask.id))
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    if offset is not None:
        stmt = stmt.offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_conversion_task(
    session: AsyncSession,
    *,
    username: str,
    workspace: Path,
    source_path: str,
    workspace_kind: str = "personal",
    team_space_id: int | None = None,
) -> ConversionTask:
    source = resolve_inside_workspace(workspace, source_path)
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源文件不存在")
    if not is_convertible_path(source):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该文件类型不支持转换")

    source_rel_path = source.relative_to(workspace.resolve()).as_posix()
    existing = await session.execute(
        select(ConversionTask.id).where(
            ConversionTask.username == username,
            ConversionTask.workspace_kind == workspace_kind,
            ConversionTask.team_space_id == team_space_id,
            ConversionTask.source_path == source_rel_path,
            ConversionTask.status.in_(("queued", "running")),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="已存在转换任务",
        )

    task = ConversionTask(
        username=username,
        workspace_kind=workspace_kind,
        team_space_id=team_space_id,
        source_path=source_rel_path,
        source_name=source.name,
        status="queued",
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def run_conversion_task(task_id: int) -> None:
    """执行单个转换任务，并把状态写回数据库。"""
    async with async_session() as session:
        claim = await session.execute(
            update(ConversionTask)
            .where(
                ConversionTask.id == task_id,
                ConversionTask.status.in_(("queued", "failed")),
            )
            .values(
                status="running",
                started_at=datetime.now(UTC),
                finished_at=None,
                error_message=None,
            )
            .returning(ConversionTask.id)
        )
        if claim.scalar_one_or_none() is None:
            return
        await session.commit()

    async with async_session() as session:
        task = await session.get(ConversionTask, task_id)
        if task is None:
            return
        workspace_kind = getattr(task, "workspace_kind", "personal")
        team_space_id = getattr(task, "team_space_id", None)
        workspace = (
            team_workspace(team_space_id)
            if workspace_kind == "team" and team_space_id is not None
            else user_workspace(task.username)
        )
        source = resolve_inside_workspace(workspace, task.source_path)
        settings = get_settings()
        lock_token: str | None = None
        lock_service: FileLockService | None = None
        if workspace_kind == "team" and team_space_id is not None:
            lock_token = f"conversion:{task.id}"
            lock_service = FileLockService(
                redis_core.get_redis_client(),
                ttl_seconds=settings.team_space_file_lock_ttl_seconds,
                cleanup_grace_seconds=settings.team_space_file_lock_cleanup_grace_seconds,
            )
            result = await lock_service.try_lock_file(
                space_id=team_space_id,
                path=task.source_path,
                holder_type="agent_session",
                holder_user_id=0,
                session_id=f"conversion:{task.id}",
                lock_token=lock_token,
            )
            if not result.ok:
                task.status = "failed"
                task.error_message = "文件正在被其他用户或会话编辑"
                task.finished_at = datetime.now(UTC)
                await session.commit()
                return
        try:
            markdown_root = ensure_markdown_root(workspace)
            final_output_root = markdown_root / Path(task.source_path).stem
            old_mappings = find_markdown_mappings_under(workspace, task.source_path)
            # 已转换文件重新转换时，先写临时目录；确认成功后再按索引删除旧目录并发布新结果。
            output_root = (
                markdown_root / f".{final_output_root.name}.{task.id}.reconvert"
                if old_mappings
                else final_output_root
            )
            result = await convert_source_to_markdown(
                source,
                output_root,
                api_url=settings.mineru_api_url,
                timeout_seconds=settings.mineru_timeout_seconds,
                max_concurrent_requests=settings.mineru_max_concurrent_requests,
            )
            markdown_rel_path = result.markdown_rel_path
            extract_rel_path = output_root.relative_to(markdown_root.parent).as_posix()
            if old_mappings:
                markdown_rel_path, extract_rel_path = _replace_old_markdown_output(
                    workspace,
                    old_mappings,
                    output_root,
                    final_output_root,
                    result.markdown_path,
                )
            add_markdown_mapping(
                workspace,
                source_path=task.source_path,
                source_name=task.source_name,
                markdown_path=markdown_rel_path,
                extract_dir=extract_rel_path,
            )
            task.status = "succeeded"
            task.markdown_path = markdown_rel_path
            task.error_message = None
        except Exception as exc:
            logger.exception("Conversion task failed")
            task.status = "failed"
            task.error_message = str(exc)
        finally:
            if lock_token and lock_service is not None and team_space_id is not None:
                with suppress(Exception):
                    await lock_service.release_file_lock(
                        space_id=team_space_id,
                        path=task.source_path,
                        lock_token=lock_token,
                    )
            task.finished_at = datetime.now(UTC)
            await session.commit()


def _replace_old_markdown_output(
    workspace: Path,
    old_mappings,
    temp_output_root: Path,
    final_output_root: Path,
    temp_markdown_path: Path,
) -> tuple[str, str]:
    """转换成功后，用临时结果替换索引指向的旧 Markdown 目录。"""
    markdown_rel_to_extract = temp_markdown_path.resolve().relative_to(
        temp_output_root.resolve()
    )
    remove_markdown_mappings(workspace, list(old_mappings))
    if final_output_root.exists():
        shutil.rmtree(final_output_root)
    final_output_root.parent.mkdir(parents=True, exist_ok=True)
    temp_output_root.rename(final_output_root)
    final_markdown_path = final_output_root / markdown_rel_to_extract
    return (
        final_markdown_path.relative_to(workspace.resolve()).as_posix(),
        final_output_root.relative_to(workspace.resolve()).as_posix(),
    )


async def update_conversion_task_source_path(
    session: AsyncSession,
    username: str,
    old_source_path: str,
    new_source_path: str,
    *,
    workspace_kind: str = "personal",
    team_space_id: int | None = None,
) -> None:
    """当源文件被重命名或移动时，同步更新对应 ConversionTask 的 source_path。"""
    from sqlalchemy import select

    result = await session.execute(
        select(ConversionTask).where(
            ConversionTask.username == username,
            ConversionTask.workspace_kind == workspace_kind,
            ConversionTask.team_space_id == team_space_id,
            ConversionTask.source_path == old_source_path,
        )
    )
    task = result.scalar_one_or_none()
    if task is not None:
        task.source_path = new_source_path
        await session.commit()


async def start_conversion_task_dispatcher(worker_count: int | None = None) -> None:
    """启动进程内转换队列消费者；任务来源仍以数据库为准。"""
    global _dispatcher_queue
    if _dispatcher_workers:
        return

    settings = get_settings()
    count = max(1, worker_count or settings.mineru_max_concurrent_requests)
    _dispatcher_queue = asyncio.Queue()
    for idx in range(count):
        worker = asyncio.create_task(_conversion_worker(idx), name=f"conversion-worker-{idx}")
        _dispatcher_workers.append(worker)


async def stop_conversion_task_dispatcher() -> None:
    """停止转换队列消费者，主要用于应用关闭和测试清理。"""
    global _dispatcher_queue
    for worker in _dispatcher_workers:
        worker.cancel()
    if _dispatcher_workers:
        await asyncio.gather(*_dispatcher_workers, return_exceptions=True)
    _dispatcher_workers.clear()
    _scheduled_task_ids.clear()
    _dispatcher_queue = None


async def _conversion_worker(worker_index: int) -> None:
    """持续消费转换任务 ID；worker_index 仅用于任务命名和调试定位。"""
    del worker_index
    assert _dispatcher_queue is not None
    while True:
        task_id = await _dispatcher_queue.get()
        try:
            await run_conversion_task(task_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Conversion worker failed")
        finally:
            _scheduled_task_ids.discard(task_id)
            _dispatcher_queue.task_done()


async def enqueue_conversion_task(task_id: int) -> None:
    """把任务 ID 放入进程内队列；重复入队会被当前进程去重。"""
    if _dispatcher_queue is None:
        await start_conversion_task_dispatcher()
    assert _dispatcher_queue is not None
    if task_id in _scheduled_task_ids:
        return
    _scheduled_task_ids.add(task_id)
    await _dispatcher_queue.put(task_id)


async def enqueue_pending_conversion_tasks() -> None:
    """服务启动时恢复数据库中尚未完成的转换任务。"""
    async with async_session() as session:
        result = await session.execute(
            select(ConversionTask.id)
            .where(ConversionTask.status == "queued")
            .order_by(ConversionTask.created_at, ConversionTask.id)
        )
        task_ids = list(result.scalars().all())

    for task_id in task_ids:
        await enqueue_conversion_task(task_id)


def schedule_conversion_task(background_tasks, task_id: int) -> None:
    """在 FastAPI BackgroundTasks 中把转换任务入队。"""
    if background_tasks is None:
        with suppress(RuntimeError):
            asyncio.create_task(enqueue_conversion_task(task_id))
        return
    background_tasks.add_task(enqueue_conversion_task, task_id)
