"""会话路由（薄层 HTTP 适配器）。"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.deps import current_user
from app.integrations.claude.runner import load_history, remove_session
from app.models import Agent, ChatSession, Project, User
from app.modules.projects.access import get_user_project_role
from app.modules.sessions.service import (
    create_session as create_session_svc,
    delete_session as delete_session_svc,
    get_accessible_session as get_accessible_session_svc,
    list_sessions as list_sessions_svc,
    rename_session as rename_session_svc,
)
from app.modules.sessions.streaming import (
    get_running_session_state,
    stop_session,
    stream_running_session,
    stream_session_chat,
)
from app.modules.workspace.scope import WorkspaceScope, personal_workspace_scope, team_workspace_scope
from app.schemas import ChatRequest, CreateSessionRequest, RenameSessionRequest, SessionOut

router = APIRouter(prefix="/api/sessions")

# 兼容旧测试和调用点的 monkeypatch 名称；实际语义已扩展为可访问会话。
get_owned_session_svc = get_accessible_session_svc


async def _scope_for_session(db: AsyncSession, user: User, cs: ChatSession) -> WorkspaceScope:
    if getattr(cs, "workspace_kind", "personal") == "team":
        team_space_id = getattr(cs, "team_space_id", None)
        if team_space_id is None:
            raise HTTPException(status_code=400, detail="团队会话缺少团队空间")
        return await team_workspace_scope(db, user, team_space_id)
    return await personal_workspace_scope(user)


async def _ensure_can_manage_session(db: AsyncSession, user: User, cs: ChatSession) -> WorkspaceScope:
    scope = await _scope_for_session(db, user, cs)
    if getattr(cs, "workspace_kind", "personal") == "team" and cs.user_id != user.id and not scope.is_owner:
        raise HTTPException(status_code=403, detail="只有会话创建者或空间所有者可以操作会话")
    return scope


async def _session_out(
    db: AsyncSession,
    user: User,
    cs: ChatSession,
    agent_name: str | None = None,
) -> SessionOut:
    scope = await _scope_for_session(db, user, cs)
    creator = user if cs.user_id == user.id else await db.get(User, cs.user_id)
    # M3.4.2：解析项目名（项目级会话才显示）
    project_name: str | None = None
    project_id = getattr(cs, "project_id", None)
    if project_id is not None:
        project = await db.get(Project, project_id)
        project_name = project.name if project else None
    return SessionOut.model_validate(
        {
            "id": cs.id,
            "title": cs.title,
            "agent_id": cs.agent_id,
            "agent_name": agent_name,
            "workspace_kind": getattr(cs, "workspace_kind", "personal"),
            "team_space_id": getattr(cs, "team_space_id", None),
            "created_by_user_id": cs.user_id,
            "created_by_name": (creator.display_name or creator.username) if creator else None,
            "team_space_name": scope.display_name if scope.kind == "team" else None,
            "is_shared": getattr(cs, "is_shared", False),
            "workspace_member_role": scope.member_role,
            "workspace_can_write": scope.can_write,
            "workspace_readonly_reason": scope.readonly_reason,
            "project_id": project_id,
            "project_name": project_name,
            "created_at": cs.created_at,
            "updated_at": cs.updated_at,
        }
    )


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    workspace_kind: str = Query("personal"),
    team_space_id: int | None = Query(None),
    agent_id: int | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    mine_only: bool = Query(False),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionOut]:
    rows = await list_sessions_svc(
        db,
        user,
        workspace_kind,
        team_space_id,
        agent_id=agent_id,
        limit=limit,
        offset=offset,
        mine_only=mine_only,
    )
    result = []
    for row in rows:
        cs = row[0]
        result.append(await _session_out(db, user, cs, row.agent_name))
    return result


@router.post("", response_model=SessionOut)
async def create_session(
    payload: CreateSessionRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    if payload.workspace_kind == "team":
        if payload.team_space_id is None:
            raise HTTPException(status_code=400, detail="团队空间会话必须指定团队空间")
        await team_workspace_scope(db, user, payload.team_space_id)
    # M3.4.2：项目级会话需校验项目成员资格（§3.5 项目内透明、项目外隔离）
    if payload.project_id is not None:
        project = await db.get(Project, payload.project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        if await get_user_project_role(db, payload.project_id, user) is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目")
    cs = await create_session_svc(
        db,
        user,
        payload.title,
        payload.agent_id,
        payload.workspace_kind,
        payload.team_space_id,
        payload.is_shared,
        payload.project_id,
    )
    agent_name = None
    if cs.agent_id:
        agent = await db.get(Agent, cs.agent_id)
        agent_name = agent.name if agent else None
    return await _session_out(db, user, cs, agent_name)


@router.patch("/{session_id}", response_model=SessionOut)
async def rename_session(
    session_id: str,
    payload: RenameSessionRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    cs = await get_owned_session_svc(db, session_id, user)
    if cs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    await _ensure_can_manage_session(db, user, cs)
    cs = await rename_session_svc(db, cs, payload.title)
    agent_name = None
    if cs.agent_id:
        agent = await db.get(Agent, cs.agent_id)
        agent_name = agent.name if agent else None
    return await _session_out(db, user, cs, agent_name)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    cs = await get_owned_session_svc(db, session_id, user)
    if cs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    scope = await _ensure_can_manage_session(db, user, cs)
    agent = None
    if cs.agent_id:
        agent = await db.get(Agent, cs.agent_id)
    await remove_session(
        cs.claude_session_id,
        scope.root,
        agent=agent,
    )
    await delete_session_svc(db, cs)


@router.get("/{session_id}/messages")
async def list_messages(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    cs = await get_owned_session_svc(db, session_id, user)
    if cs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    if not cs.claude_session_id:
        return []
    scope = await _scope_for_session(db, user, cs)
    agent = None
    if cs.agent_id:
        agent = await db.get(Agent, cs.agent_id)
    return await load_history(
        cs.claude_session_id,
        scope.root,
        agent=agent,
    )


@router.get("/{session_id}/running")
async def get_running_session(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cs = await get_owned_session_svc(db, session_id, user)
    if cs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return get_running_session_state(session_id)


@router.get("/{session_id}/running/stream")
async def stream_running_session_events(
    session_id: str,
    after_seq: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    cs = await get_owned_session_svc(db, session_id, user)
    if cs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return stream_running_session(session_id, after_seq)


@router.post("/{session_id}/chat")
async def chat(
    session_id: str,
    payload: ChatRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    cs = await get_owned_session_svc(db, session_id, user)
    if cs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    agent = None
    if cs.agent_id:
        agent = await db.get(Agent, cs.agent_id)
    return await stream_session_chat(
        cs,
        user,
        payload.prompt,
        agent=agent,
        model=payload.model,
        thinking_level=payload.thinking_level,
    )


@router.post("/{session_id}/stop")
async def stop_chat(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cs = await get_owned_session_svc(db, session_id, user)
    if cs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return await stop_session(session_id)
