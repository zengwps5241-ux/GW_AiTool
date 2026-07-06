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
async def workspace_tasks(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> list[WorkspaceTaskOut]:
    return await list_workspace_tasks(session, user.username, limit=limit, offset=offset)
