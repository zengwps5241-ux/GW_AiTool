"""团队空间 API。"""

from urllib.parse import quote, urlencode
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, require_admin
from app.core import redis as redis_core
from app.core.config import get_settings
from app.db.session import get_db
from app.models import TeamSpace, TeamSpaceMember, User
from app.modules.conversions.service import (
    create_conversion_task,
    list_user_tasks as list_conversion_tasks,
    schedule_conversion_task,
    update_conversion_task_source_path,
)
from app.modules.team_spaces import service
from app.modules.team_spaces.file_locks import FileLockService
from app.modules.uploads.tasks import create_upload_tasks, get_upload_task_target_path, save_upload_task_file
from app.modules.workspace.office_preview import (
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
from app.modules.workspace.scope import require_workspace_write, team_workspace_scope
from app.modules.workspace.service import (
    delete_workspace_item,
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
    resolve_content_write_path,
)
from app.modules.workspace.tasks import list_workspace_tasks
from app.schemas import (
    ConversionRetryIn,
    ConversionTaskOut,
    UploadTaskCreateIn,
    UploadTaskOut,
    WorkspaceCreateIn,
    WorkspaceFileLockIn,
    WorkspaceFileLockOut,
    WorkspaceFileUnlockIn,
    WorkspaceFileUnlockOut,
    WorkspaceMoveIn,
    WorkspaceNode,
    WorkspaceRenameIn,
    WorkspaceTaskOut,
    WorkspaceTextOut,
    WorkspaceTextSaveIn,
)
from app.schemas.team_spaces import (
    MethodologyCategory,
    MethodologyItemCreate,
    MethodologyItemOut,
    MethodologyItemUpdate,
    PublicAssetsOut,
    TeamSpaceCreateIn,
    TeamSpaceLockIn,
    TeamSpaceMemberAddIn,
    TeamSpaceMemberOut,
    TeamSpaceMemberSearchOut,
    TeamSpaceMemberUpdateIn,
    TeamSpaceOut,
    TeamSpaceTransferOwnerIn,
    UserSearchOut,
)

router = APIRouter(prefix="/api/team-spaces")


def _team_preview_token_subject(space_id: int) -> str:
    return f"team:{space_id}"


def _team_internal_file_url(base_url: str, token: str, filename: str) -> str:
    root = base_url.rstrip("/")
    query = urlencode({"token": token, "fullfilename": filename})
    return f"{root}/api/team-spaces/workspace/internal-preview-file?{query}"


def _file_lock_service() -> FileLockService:
    settings = get_settings()
    return FileLockService(
        redis_core.get_redis_client(),
        ttl_seconds=settings.team_space_file_lock_ttl_seconds,
        cleanup_grace_seconds=settings.team_space_file_lock_cleanup_grace_seconds,
    )


async def _acquire_temporary_user_file_lock(
    *,
    space_id: int,
    path: str,
    user: User,
    operation: str,
) -> str:
    lock_token = f"user-op:{operation}:{uuid4()}"
    result = await _file_lock_service().try_lock_file(
        space_id=space_id,
        path=path,
        holder_type="user",
        holder_user_id=user.id,
        session_id="api",
        lock_token=lock_token,
    )
    if not result.ok:
        raise HTTPException(status_code=409, detail={"code": "FILE_LOCKED", "path": path})
    return lock_token


async def _release_temporary_user_file_lock(*, space_id: int, path: str, lock_token: str) -> None:
    await _file_lock_service().release_file_lock(space_id=space_id, path=path, lock_token=lock_token)


async def _space_out(db: AsyncSession, space, member, *, member_count: int | None = None) -> TeamSpaceOut:
    can_write, readonly_reason = service.can_write(space, member)
    return TeamSpaceOut.model_validate({
        "id": space.id,
        "name": space.name,
        "description": space.description,
        "owner_user_id": space.owner_user_id,
        "owner_name": "",
        "member_count": member_count if member_count is not None else await service.member_count(db, space.id),
        "locked_by_user_id": space.lock_holder_user_id,
        "locked_by_name": None,
        "lock_acquired_at": space.lock_acquired_at,
        "lock_note": space.lock_note,
        "member_role": member.role,
        "can_write": can_write,
        "is_owner": space.owner_user_id == member.user_id,
        "readonly_reason": readonly_reason,
        "created_at": space.created_at,
        "updated_at": space.updated_at,
    })


def _member_out(space: TeamSpace, member: TeamSpaceMember, member_user: User) -> TeamSpaceMemberOut:
    return TeamSpaceMemberOut.model_validate({
        "id": member.id,
        "user_id": member.user_id,
        "username": member_user.username,
        "display_name": member_user.display_name,
        "role": member.role,
        "is_owner": space.owner_user_id == member.user_id,
        "added_by_user_id": member.added_by_user_id,
        "created_at": member.created_at,
        "updated_at": member.updated_at,
    })


@router.get("", response_model=list[TeamSpaceOut])
async def list_team_spaces(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TeamSpaceOut]:
    rows = (
        await db.execute(
            select(TeamSpace, TeamSpaceMember)
            .join(TeamSpaceMember, TeamSpaceMember.space_id == TeamSpace.id)
            .where(TeamSpaceMember.user_id == user.id)
            .order_by(TeamSpace.updated_at.desc(), TeamSpace.id.desc())
        )
    ).all()
    return [await _space_out(db, space, member) for space, member in rows]


@router.post("", response_model=TeamSpaceOut)
async def create_team_space(
    payload: TeamSpaceCreateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    space = await service.create_space(db, user, payload.name, payload.description)
    _space, member = await service.require_member(db, user, space.id)
    return await _space_out(db, space, member, member_count=1)


# ─── 对象公开机制（M5.5.3，§2.6 / §5.x / §6.3）────────────────────
# 这两个端点放在 /{space_id} 之前，避免路径字面量 public-assets / shared-with-me
# 被 /{space_id}:int 误匹配（int 转换失败本就会跳过，前置仅为稳妥）。
# 公开资产对所有登录用户可见（无需团队空间成员身份），仅 current_user 鉴权。


@router.get("/public-assets", response_model=PublicAssetsOut)
async def list_public_assets(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PublicAssetsOut:
    """团队空间公开资产区：跨项目聚合 is_public=1 的 reviewed 对象（§6.3）。

    对象类型=角色卡 / 业务地图片段 / 拜访记录（含 is_public 字段的三类）。
    """
    return PublicAssetsOut.model_validate(
        (await service.list_public_assets(db)),
    )


@router.get("/shared-with-me", response_model=PublicAssetsOut)
async def list_shared_with_me(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PublicAssetsOut:
    """共享给我的对象：跨项目聚合 shared_with ∋ 当前用户 的 reviewed 对象（§5.x）。"""
    return PublicAssetsOut.model_validate(
        (await service.list_shared_with_me(db, user.id)),
    )


@router.get("/users/search", response_model=list[UserSearchOut])
async def search_users(
    keyword: str = Query(min_length=1, max_length=80),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserSearchOut]:
    """按姓名/用户名搜索 active 用户（「共享给」picker 数据源）。"""
    users = await service.search_users(db, keyword)
    return [
        UserSearchOut(user_id=u.id, username=u.username, display_name=u.display_name)
        for u in users
    ]


# ─── 方法论库（§2.6 / §6.3，admin 维护，用户只读）──────────────────
# 全局端点（非团队空间作用域），置于 /{space_id}:int 之前，避免字面量
# methodology-library 被 int 转换器之外的路径误匹配（同 public-assets 前置）。
# 所有登录用户只读；写操作 require_admin（§3.2 管理种子数据）。

@router.get("/methodology-library", response_model=list[MethodologyItemOut])
async def list_methodology_library(
    category: MethodologyCategory | None = Query(None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MethodologyItemOut]:
    """方法论库列表（按 类别→排序→id），可按类别过滤。"""
    return await service.list_methodology(db, category=category)


@router.get("/methodology-library/{item_id}", response_model=MethodologyItemOut)
async def get_methodology_library_item(
    item_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> MethodologyItemOut:
    item = await service.get_methodology(db, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="条目不存在")
    return item


@router.post(
    "/methodology-library",
    response_model=MethodologyItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_methodology_library_item(
    payload: MethodologyItemCreate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> MethodologyItemOut:
    """新增方法论库条目（仅 admin/super）。"""
    return await service.create_methodology(db, payload, user)


@router.put("/methodology-library/{item_id}", response_model=MethodologyItemOut)
async def update_methodology_library_item(
    item_id: int,
    payload: MethodologyItemUpdate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> MethodologyItemOut:
    """更新方法论库条目（仅 admin/super）。"""
    item = await service.update_methodology(db, item_id, payload)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="条目不存在")
    return item


@router.delete(
    "/methodology-library/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_methodology_library_item(
    item_id: int,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """删除方法论库条目（仅 admin/super）。"""
    ok = await service.delete_methodology(db, item_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="条目不存在")


@router.get("/{space_id}", response_model=TeamSpaceOut)
async def get_team_space(
    space_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamSpaceOut:
    space, member = await service.require_member(db, user, space_id)
    return await _space_out(db, space, member)


@router.get("/{space_id}/members", response_model=list[TeamSpaceMemberOut])
async def list_team_space_members(
    space_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TeamSpaceMemberOut]:
    space, _member = await service.require_member(db, user, space_id)
    rows = (
        await db.execute(
            select(TeamSpaceMember, User)
            .join(User, User.id == TeamSpaceMember.user_id)
            .where(TeamSpaceMember.space_id == space_id)
            .order_by(TeamSpaceMember.created_at.asc(), TeamSpaceMember.id.asc())
        )
    ).all()
    return [_member_out(space, member, member_user) for member, member_user in rows]


@router.get("/{space_id}/members/search", response_model=list[TeamSpaceMemberSearchOut])
async def search_team_space_member_candidates(
    space_id: int,
    keyword: str = Query(min_length=1, max_length=80),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TeamSpaceMemberSearchOut]:
    candidates = await service.search_member_candidates(db, user, space_id, keyword)
    return [
        TeamSpaceMemberSearchOut(
            user_id=candidate.id,
            username=candidate.username,
            display_name=candidate.display_name,
            is_member=is_member,
        )
        for candidate, is_member in candidates
    ]


@router.post("/{space_id}/members")
async def add_team_space_member(
    space_id: int,
    payload: TeamSpaceMemberAddIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    member = await service.add_member(db, user, space_id, payload.user_id, payload.role)
    return {"id": member.id, "user_id": member.user_id, "role": member.role}


@router.patch("/{space_id}/members/{member_id}", response_model=TeamSpaceMemberOut)
async def update_team_space_member(
    space_id: int,
    member_id: int,
    payload: TeamSpaceMemberUpdateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamSpaceMemberOut:
    member = await service.update_member_role(db, user, space_id, member_id, payload.role)
    space, _owner_member = await service.require_member(db, user, space_id)
    member_user = await db.get(User, member.user_id)
    if member_user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _member_out(space, member, member_user)


@router.delete("/{space_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_space_member(
    space_id: int,
    member_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.remove_member(db, user, space_id, member_id)


@router.post("/{space_id}/owner", response_model=TeamSpaceOut)
async def transfer_team_space_owner(
    space_id: int,
    payload: TeamSpaceTransferOwnerIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamSpaceOut:
    space = await service.transfer_owner(db, user, space_id, payload.user_id)
    _space, member = await service.require_member(db, user, space_id)
    return await _space_out(db, space, member)


@router.post("/{space_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_team_space(
    space_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.leave_space(db, user, space_id)


@router.post("/{space_id}/lock", response_model=TeamSpaceOut)
async def lock_team_space(
    space_id: int,
    payload: TeamSpaceLockIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    space = await service.lock_space(db, user, space_id, payload.note)
    _space, member = await service.require_member(db, user, space_id)
    return await _space_out(db, space, member)


@router.delete("/{space_id}/lock", response_model=TeamSpaceOut)
async def unlock_team_space(
    space_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    space = await service.unlock_space(db, user, space_id)
    _space, member = await service.require_member(db, user, space_id)
    return await _space_out(db, space, member)


@router.get("/{space_id}/workspace/tree", response_model=list[WorkspaceNode])
async def team_workspace_tree(
    space_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkspaceNode]:
    scope = await team_workspace_scope(db, user, space_id)
    tasks = await list_conversion_tasks(
        db,
        user.username,
        workspace_kind="team",
        team_space_id=space_id,
    )
    conversion_meta = {
        task.source_path: {
            "conversion_status": task.status,
            "conversion_task_id": task.id,
            "conversion_error": task.error_message,
            "markdown_path": task.markdown_path,
        }
        for task in tasks
    }
    return get_workspace_tree(scope.root, conversion_meta)


@router.post("/{space_id}/workspace/file")
async def team_create_workspace_item(
    space_id: int,
    payload: WorkspaceCreateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    if payload.kind == "file":
        lock_token = await _acquire_temporary_user_file_lock(
            space_id=space_id,
            path=payload.path,
            user=user,
            operation="create",
        )
        try:
            return create_workspace_item(scope.root, payload.path, payload.kind, payload.content)
        finally:
            await _release_temporary_user_file_lock(space_id=space_id, path=payload.path, lock_token=lock_token)
    return create_workspace_item(scope.root, payload.path, payload.kind, payload.content)


@router.post("/{space_id}/workspace/locks", response_model=WorkspaceFileLockOut)
async def team_lock_workspace_file(
    space_id: int,
    payload: WorkspaceFileLockIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    write_path = resolve_content_write_path(scope.root, payload.path)
    lock_token = str(uuid4())
    result = await _file_lock_service().try_lock_file(
        space_id=space_id,
        path=write_path,
        holder_type="user",
        holder_user_id=user.id,
        session_id="ui",
        lock_token=lock_token,
    )
    if not result.ok:
        raise HTTPException(status_code=409, detail={"code": "FILE_LOCKED", "path": payload.path})
    return WorkspaceFileLockOut(
        ok=True,
        path=write_path,
        lock_token=lock_token,
        expires_at_ms=result.expires_at_ms or 0,
    )


@router.delete("/{space_id}/workspace/locks", response_model=WorkspaceFileUnlockOut)
async def team_unlock_workspace_file(
    space_id: int,
    payload: WorkspaceFileUnlockIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    write_path = resolve_content_write_path(scope.root, payload.path)
    released = await _file_lock_service().release_file_lock(
        space_id=space_id,
        path=write_path,
        lock_token=payload.lock_token,
    )
    return WorkspaceFileUnlockOut(released=released)


@router.put("/{space_id}/workspace/content", response_model=WorkspaceTextOut)
async def team_save_workspace_content(
    space_id: int,
    payload: WorkspaceTextSaveIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    write_path = resolve_content_write_path(scope.root, payload.path)
    if not payload.lock_token:
        raise HTTPException(status_code=409, detail={"code": "FILE_LOCK_EXPIRED", "path": payload.path})
    valid = await _file_lock_service().validate_file_lock(
        space_id=space_id,
        path=write_path,
        lock_token=payload.lock_token,
    )
    if not valid:
        raise HTTPException(status_code=409, detail={"code": "FILE_LOCK_EXPIRED", "path": payload.path})
    return save_content_file(scope.root, payload.path, payload.content)


@router.get("/{space_id}/workspace/preview")
async def team_preview_workspace_item(
    space_id: int,
    path: str = Query(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await team_workspace_scope(db, user, space_id)
    return preview_workspace_item(scope.root, path)


@router.get("/{space_id}/workspace/markdown-preview")
async def team_preview_workspace_markdown_item(
    space_id: int,
    path: str = Query(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await team_workspace_scope(db, user, space_id)
    return preview_workspace_markdown_item(scope.root, path)


@router.get("/{space_id}/workspace/office-preview")
async def team_office_preview(
    space_id: int,
    path: str = Query(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    if not settings.app_internal_base_url or not settings.kkfileview_base_url:
        raise HTTPException(status_code=503, detail="Office 预览服务未配置")
    scope = await team_workspace_scope(db, user, space_id)
    target = resolve_inside_workspace(scope.root, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not is_office_document(target):
        raise HTTPException(status_code=400, detail="仅 Office/PDF 文件支持 kkFileView 预览")

    rel_path = target.relative_to(scope.root.resolve()).as_posix()
    token = create_file_token(_team_preview_token_subject(space_id), rel_path, secret=settings.app_secret)
    source_url = _team_internal_file_url(settings.app_internal_base_url, token, target.name)
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
            f"/api/team-spaces/{space_id}/workspace/kkfileview",
            settings.kkfileview_base_url,
        )
    return Response(content=body, media_type=content_type)


@router.get("/{space_id}/workspace/kkfileview/{rel_path:path}")
async def team_workspace_kkfileview_proxy(space_id: int, rel_path: str, request: Request):
    settings = get_settings()
    if not settings.kkfileview_base_url:
        raise HTTPException(status_code=503, detail="Office 预览服务未配置")
    return await stream_kkfileview_path(settings.kkfileview_base_url, rel_path, request.url.query, request.headers)


@router.get("/workspace/internal-preview-file")
def team_internal_preview_file(token: str = Query(...)):
    settings = get_settings()
    data = verify_file_token(token, secret=settings.app_secret)
    subject = str(data["username"])
    if not subject.startswith("team:"):
        raise HTTPException(status_code=403, detail="签名无效")
    try:
        space_id = int(subject.removeprefix("team:"))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="签名无效") from exc
    root = service.team_workspace(space_id)
    target = resolve_inside_workspace(root, str(data["path"]))
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not is_office_document(target):
        raise HTTPException(status_code=400, detail="仅 Office/PDF 文件支持")
    headers = inline_headers(guess_mime(target))
    headers["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(target.name, safe='')}"
    return FileResponse(path=target, media_type=guess_mime(target), headers=headers)


@router.patch("/{space_id}/workspace/file/rename")
async def team_rename_workspace_item(
    space_id: int,
    payload: WorkspaceRenameIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    lock_token = await _acquire_temporary_user_file_lock(
        space_id=space_id,
        path=payload.path,
        user=user,
        operation="rename",
    )
    try:
        result = rename_workspace_item(scope.root, payload.path, payload.new_name)
        await update_conversion_task_source_path(
            db,
            user.username,
            payload.path,
            result["path"],
            workspace_kind="team",
            team_space_id=space_id,
        )
        return result
    finally:
        await _release_temporary_user_file_lock(space_id=space_id, path=payload.path, lock_token=lock_token)


@router.patch("/{space_id}/workspace/file/move")
async def team_move_workspace_item(
    space_id: int,
    payload: WorkspaceMoveIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    lock_token = await _acquire_temporary_user_file_lock(
        space_id=space_id,
        path=payload.path,
        user=user,
        operation="move",
    )
    try:
        result = move_workspace_item(scope.root, payload.path, payload.target_dir)
        await update_conversion_task_source_path(
            db,
            user.username,
            payload.path,
            result["path"],
            workspace_kind="team",
            team_space_id=space_id,
        )
        return result
    finally:
        await _release_temporary_user_file_lock(space_id=space_id, path=payload.path, lock_token=lock_token)


@router.delete("/{space_id}/workspace/file", status_code=204)
async def team_delete_workspace_item(
    space_id: int,
    path: str = Query(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    lock_token = await _acquire_temporary_user_file_lock(
        space_id=space_id,
        path=path,
        user=user,
        operation="delete",
    )
    try:
        delete_workspace_item(scope.root, path)
    finally:
        await _release_temporary_user_file_lock(space_id=space_id, path=path, lock_token=lock_token)


@router.get("/{space_id}/workspace/download")
async def team_download_workspace_item(
    space_id: int,
    path: str = Query(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await team_workspace_scope(db, user, space_id)
    return download_workspace_item(scope.root, path)


@router.post("/{space_id}/upload-tasks", response_model=list[UploadTaskOut])
async def create_team_upload_tasks(
    space_id: int,
    payload: UploadTaskCreateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UploadTaskOut]:
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    return await create_upload_tasks(
        db,
        user.username,
        scope.root,
        payload,
        workspace_kind="team",
        team_space_id=space_id,
    )


@router.post("/{space_id}/upload-tasks/{task_id}/file", response_model=UploadTaskOut)
async def upload_team_task_file(
    space_id: int,
    task_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> UploadTaskOut:
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    target_path = await get_upload_task_target_path(
        db,
        username=user.username,
        task_id=task_id,
        workspace_kind="team",
        team_space_id=space_id,
    )
    lock_token = await _acquire_temporary_user_file_lock(
        space_id=space_id,
        path=target_path,
        user=user,
        operation="upload",
    )
    try:
        return await save_upload_task_file(
            db,
            username=user.username,
            workspace=scope.root,
            task_id=task_id,
            file=file,
            background_tasks=background_tasks,
            workspace_kind="team",
            team_space_id=space_id,
        )
    finally:
        await _release_temporary_user_file_lock(space_id=space_id, path=target_path, lock_token=lock_token)


@router.get("/{space_id}/conversion-tasks", response_model=list[ConversionTaskOut])
async def list_team_conversion_tasks(
    space_id: int,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConversionTaskOut]:
    await team_workspace_scope(db, user, space_id)
    return await list_conversion_tasks(
        db,
        user.username,
        limit=limit,
        offset=offset,
        workspace_kind="team",
        team_space_id=space_id,
    )


@router.post("/{space_id}/conversion-tasks/retry", response_model=ConversionTaskOut)
async def retry_team_conversion_task(
    space_id: int,
    payload: ConversionRetryIn,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversionTaskOut:
    scope = await team_workspace_scope(db, user, space_id)
    require_workspace_write(scope)
    task = await create_conversion_task(
        db,
        username=user.username,
        workspace=scope.root,
        source_path=payload.source_path,
        workspace_kind="team",
        team_space_id=space_id,
    )
    schedule_conversion_task(background_tasks, task.id)
    return task


@router.get("/{space_id}/workspace-tasks", response_model=list[WorkspaceTaskOut])
async def list_team_workspace_tasks(
    space_id: int,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkspaceTaskOut]:
    await team_workspace_scope(db, user, space_id)
    return await list_workspace_tasks(
        db,
        user.username,
        limit=limit,
        offset=offset,
        workspace_kind="team",
        team_space_id=space_id,
    )
