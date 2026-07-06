"""上传任务路由。"""

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core.config import user_workspace
from app.db.session import get_db
from app.models import User
from app.modules.uploads.tasks import (
    abandon_upload_tasks,
    create_upload_tasks,
    save_upload_task_file,
    update_upload_task_progress,
)
from app.schemas import UploadTaskAbandonIn, UploadTaskCreateIn, UploadTaskOut, UploadTaskProgressIn

router = APIRouter(prefix="/api/upload-tasks")


@router.post("", response_model=list[UploadTaskOut])
async def create_tasks(
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


@router.post("/abandon", response_model=list[UploadTaskOut])
async def abandon_tasks(
    data: UploadTaskAbandonIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[UploadTaskOut]:
    return await abandon_upload_tasks(
        session,
        username=user.username,
        data=data,
    )


@router.post("/{task_id}/file", response_model=UploadTaskOut)
async def upload_task_file(
    task_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> UploadTaskOut:
    return await save_upload_task_file(
        session,
        username=user.username,
        workspace=user_workspace(user.username),
        task_id=task_id,
        file=file,
        background_tasks=background_tasks,
    )


@router.patch("/{task_id}/progress", response_model=UploadTaskOut)
async def patch_task_progress(
    task_id: int,
    data: UploadTaskProgressIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> UploadTaskOut:
    return await update_upload_task_progress(
        session,
        username=user.username,
        task_id=task_id,
        data=data,
    )
