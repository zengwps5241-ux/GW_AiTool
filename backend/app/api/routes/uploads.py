"""文件上传路由（薄层 HTTP 适配器）。"""

import json

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile

from app.core.config import user_workspace
from app.api.deps import current_user
from app.db.session import get_db
from app.models import User
from app.modules.conversions.service import schedule_conversion_task
from app.modules.uploads.service import save_uploaded_files
from app.schemas import UploadBatchOut

router = APIRouter(prefix="/api/uploads")


@router.post("", response_model=UploadBatchOut)
async def upload_files(
    files: list[UploadFile] = File(...),
    target_dir: str = Form(""),
    relative_paths: str = Form("[]"),
    background_tasks: BackgroundTasks = None,
    session=Depends(get_db),
    user: User = Depends(current_user),
) -> UploadBatchOut:
    workspace = user_workspace(user.username)
    try:
        rels = json.loads(relative_paths)
    except json.JSONDecodeError:
        rels = []
    if not isinstance(rels, list) or not all(isinstance(x, str) for x in rels):
        rels = []
    result = await save_uploaded_files(
        files,
        workspace,
        target_dir=target_dir,
        relative_paths=rels,
        username=user.username,
        session=session,
    )
    for item in result["items"]:
        task_id = item.get("conversion_task_id")
        if task_id and background_tasks:
            schedule_conversion_task(background_tasks, task_id)
    return UploadBatchOut(**result)
