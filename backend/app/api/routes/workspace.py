"""工作空间路由（薄层 HTTP 适配器）。"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings, user_workspace
from app.api.deps import current_user
from app.db.session import get_db
from app.models import User
from app.modules.workspace.office_preview import (
    build_internal_file_url,
    build_kkfileview_online_preview_url,
    create_file_token,
    fetch_kkfileview_response,
    is_office_document,
    kkfileview_preview_type_for_size,
    rewrite_kkfileview_html,
    stream_kkfileview_path,
    verify_file_token,
)
from app.modules.workspace.paths import resolve_inside_workspace
from app.modules.workspace.preview import guess_mime, inline_headers
from app.modules.workspace.service import (
    delete_workspace_item,
    download_workspace_markdown,
    download_workspace_item,
    get_workspace_tree,
    preview_workspace_item,
    preview_workspace_markdown_item,
)
from app.modules.workspace.text_ops import (
    create_workspace_item,
    move_workspace_item,
    rename_workspace_item,
    save_content_file,
)
from app.schemas import (
    WorkspaceCreateIn,
    WorkspaceMoveIn,
    WorkspaceNode,
    WorkspaceRenameIn,
    WorkspaceTextOut,
    WorkspaceTextSaveIn,
)

router = APIRouter(prefix="/api/workspace")
kkfileview_router = APIRouter(prefix="/kkfileview")


@router.get("/tree", response_model=list[WorkspaceNode])
async def workspace_tree(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkspaceNode]:
    from app.modules.conversions.service import list_user_tasks

    tasks = await list_user_tasks(db, user.username)
    conversion_meta = {
        t.source_path: {
            "conversion_status": t.status,
            "conversion_task_id": t.id,
            "conversion_error": t.error_message,
            "markdown_path": t.markdown_path,
        }
        for t in tasks
    }
    return get_workspace_tree(user_workspace(user.username), conversion_meta)


@router.delete("/file", status_code=204)
def delete_workspace_item_route(
    path: str = Query(..., description="相对于工作区的文件或目录路径"),
    user: User = Depends(current_user),
) -> None:
    delete_workspace_item(user_workspace(user.username), path)


@router.get("/download")
def download_workspace_item_route(
    path: str = Query(..., description="相对于工作区的文件或目录路径"),
    user: User = Depends(current_user),
):
    return download_workspace_item(user_workspace(user.username), path)


@router.get("/download-markdown")
def download_workspace_markdown_route(
    path: str = Query(..., description="相对于工作区的 Office/PDF 源文件路径"),
    user: User = Depends(current_user),
):
    return download_workspace_markdown(user_workspace(user.username), path)


@router.get("/preview")
def preview_workspace_item_route(
    path: str = Query(..., description="相对于工作区的文件路径"),
    user: User = Depends(current_user),
):
    return preview_workspace_item(user_workspace(user.username), path)


@router.get("/markdown-preview")
def preview_workspace_markdown_route(
    path: str = Query(..., description="相对于工作区的文件路径"),
    user: User = Depends(current_user),
):
    return preview_workspace_markdown_item(user_workspace(user.username), path)


@router.get("/office-preview")
async def office_preview_route(
    path: str = Query(..., description="相对于工作区的 Office/PDF 文件路径"),
    user: User = Depends(current_user),
):
    settings = get_settings()
    if not settings.app_internal_base_url or not settings.kkfileview_base_url:
        raise HTTPException(status_code=503, detail="Office 预览服务未配置")
    workspace = user_workspace(user.username)
    target = resolve_inside_workspace(workspace, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not is_office_document(target):
        raise HTTPException(status_code=400, detail="仅 Office/PDF 文件支持 kkFileView 预览")

    rel_path = target.relative_to(workspace.resolve()).as_posix()
    token = create_file_token(user.username, rel_path, secret=settings.app_secret)
    source_url = build_internal_file_url(settings.app_internal_base_url, token, target.name)
    office_preview_type = kkfileview_preview_type_for_size(target.stat().st_size)
    kk_url = build_kkfileview_online_preview_url(
        settings.kkfileview_base_url,
        source_url,
        office_preview_type=office_preview_type,
    )
    response = await fetch_kkfileview_response(kk_url)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Office 预览服务不可用")
    content_type = response.headers.get("content-type", "text/html")
    body = response.text if "text/html" in content_type else response.content
    if isinstance(body, str):
        body = rewrite_kkfileview_html(
            body,
            "/api/workspace/kkfileview",
            settings.kkfileview_base_url,
        )
    return Response(content=body, media_type=content_type)


@router.get("/office-preview/proxy/{rel_path:path}")
async def office_preview_proxy_route(rel_path: str, request: Request):
    settings = get_settings()
    if not settings.kkfileview_base_url:
        raise HTTPException(status_code=503, detail="Office 预览服务未配置")
    return await stream_kkfileview_path(settings.kkfileview_base_url, rel_path, request.url.query, request.headers)


@router.get("/kkfileview/{rel_path:path}")
async def workspace_kkfileview_proxy_route(rel_path: str, request: Request):
    """代理 kkFileView 相对资源，处理 office-preview HTML 中的 xlsx/js 等路径。"""
    settings = get_settings()
    if not settings.kkfileview_base_url:
        raise HTTPException(status_code=503, detail="Office 预览服务未配置")
    return await stream_kkfileview_path(settings.kkfileview_base_url, rel_path, request.url.query, request.headers)


@kkfileview_router.get("/{rel_path:path}")
async def kkfileview_context_proxy_route(rel_path: str, request: Request):
    """代理 kkFileView 上下文路径资源，避免浏览器直接访问内网地址。"""
    settings = get_settings()
    if not settings.kkfileview_base_url:
        raise HTTPException(status_code=503, detail="Office 预览服务未配置")
    return await stream_kkfileview_path(settings.kkfileview_base_url, rel_path, request.url.query, request.headers)


@router.get("/internal-preview-file")
def internal_preview_file_route(token: str = Query(...)):
    settings = get_settings()
    data = verify_file_token(token, secret=settings.app_secret)
    workspace = user_workspace(str(data["username"]))
    target = resolve_inside_workspace(workspace, str(data["path"]))
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not is_office_document(target):
        raise HTTPException(status_code=400, detail="仅 Office/PDF 文件支持")
    headers = inline_headers(guess_mime(target))
    headers["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(target.name, safe='')}"
    return FileResponse(path=target, media_type=guess_mime(target), headers=headers)


@router.put("/content", response_model=WorkspaceTextOut)
def save_workspace_content_route(data: WorkspaceTextSaveIn, user: User = Depends(current_user)):
    return save_content_file(user_workspace(user.username), data.path, data.content)


@router.post("/file")
def create_workspace_item_route(data: WorkspaceCreateIn, user: User = Depends(current_user)):
    return create_workspace_item(user_workspace(user.username), data.path, data.kind, data.content)


@router.patch("/file/rename")
async def rename_workspace_item_route(
    data: WorkspaceRenameIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.modules.conversions.service import update_conversion_task_source_path

    result = rename_workspace_item(
        user_workspace(user.username), data.path, data.new_name
    )
    await update_conversion_task_source_path(
        db, user.username, data.path, result["path"]
    )
    return result


@router.patch("/file/move")
async def move_workspace_item_route(
    data: WorkspaceMoveIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.modules.conversions.service import update_conversion_task_source_path

    result = move_workspace_item(
        user_workspace(user.username), data.path, data.target_dir
    )
    await update_conversion_task_source_path(
        db, user.username, data.path, result["path"]
    )
    return result
