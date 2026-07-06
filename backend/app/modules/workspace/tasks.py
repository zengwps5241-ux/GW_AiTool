"""个人空间通用任务聚合服务。"""

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConversionTask, UploadTask
from app.schemas import WorkspaceTaskOut

_TYPE_ORDER = {"upload": 0, "conversion": 1}


def _upload_task_out(task: UploadTask) -> WorkspaceTaskOut:
    """将上传任务映射为统一任务结构。"""
    return WorkspaceTaskOut(
        type="upload",
        task_key=f"upload:{task.id}",
        id=task.id,
        workspace_kind=task.workspace_kind,
        team_space_id=task.team_space_id,
        name=task.filename,
        path=task.saved_path or task.relative_path,
        status=task.status,
        progress=task.progress,
        error_message=task.error_message,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )


def _conversion_task_out(task: ConversionTask) -> WorkspaceTaskOut:
    """将转换任务映射为统一任务结构。"""
    return WorkspaceTaskOut(
        type="conversion",
        task_key=f"conversion:{task.id}",
        id=task.id,
        workspace_kind=task.workspace_kind,
        team_space_id=task.team_space_id,
        name=task.source_name,
        path=task.source_path,
        status=task.status,
        progress=None,
        error_message=task.error_message,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )


async def list_workspace_tasks(
    session: AsyncSession,
    username: str,
    limit: int = 10,
    offset: int = 0,
    *,
    workspace_kind: str = "personal",
    team_space_id: int | None = None,
) -> list[WorkspaceTaskOut]:
    """合并上传和转换任务，按创建时间倒序分页返回。"""
    fetch_size = limit + offset
    upload_result = await session.execute(
        select(UploadTask)
        .where(
            UploadTask.username == username,
            UploadTask.workspace_kind == workspace_kind,
            UploadTask.team_space_id == team_space_id,
        )
        .order_by(desc(UploadTask.created_at), desc(UploadTask.id))
        .limit(fetch_size)
    )
    conversion_result = await session.execute(
        select(ConversionTask)
        .where(
            ConversionTask.username == username,
            ConversionTask.workspace_kind == workspace_kind,
            ConversionTask.team_space_id == team_space_id,
        )
        .order_by(desc(ConversionTask.created_at), desc(ConversionTask.id))
        .limit(fetch_size)
    )

    tasks = [_upload_task_out(task) for task in upload_result.scalars().all()]
    tasks.extend(_conversion_task_out(task) for task in conversion_result.scalars().all())
    tasks.sort(key=lambda task: (task.created_at, task.id, _TYPE_ORDER[task.type]), reverse=True)
    return tasks[offset : offset + limit]
