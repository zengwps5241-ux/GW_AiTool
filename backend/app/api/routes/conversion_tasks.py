"""转换任务路由。"""

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core.config import user_workspace
from app.db.session import get_db
from app.models import User
from app.modules.conversions.service import (
    create_conversion_task,
    list_user_tasks,
    schedule_conversion_task,
)
from app.schemas import ConversionRetryIn, ConversionTaskOut

router = APIRouter(prefix="/api/conversion-tasks")


@router.get("", response_model=list[ConversionTaskOut])
async def conversion_tasks(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ConversionTaskOut]:
    return await list_user_tasks(session, user.username, limit=limit, offset=offset)


@router.post("/retry", response_model=ConversionTaskOut)
async def retry_conversion_task(
    data: ConversionRetryIn,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> ConversionTaskOut:
    task = await create_conversion_task(
        session,
        username=user.username,
        workspace=user_workspace(user.username),
        source_path=data.source_path,
    )
    schedule_conversion_task(background_tasks, task.id)
    return task
