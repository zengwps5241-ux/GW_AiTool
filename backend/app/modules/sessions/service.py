"""会话元数据 CRUD 业务逻辑。"""

import uuid

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, ChatSession, Project, TeamSpaceMember, User


async def get_owned_session(db: AsyncSession, session_id: str, user: User) -> ChatSession | None:
    return (
        await db.execute(
            select(ChatSession).where(
                ChatSession.id == session_id, ChatSession.user_id == user.id
            )
        )
    ).scalar_one_or_none()


async def get_accessible_session(db: AsyncSession, session_id: str, user: User) -> ChatSession | None:
    cs = await db.get(ChatSession, session_id)
    if cs is None:
        return None
    if cs.workspace_kind == "personal":
        return cs if cs.user_id == user.id else None
    if cs.team_space_id is None:
        return None
    member = (
        await db.execute(
            select(TeamSpaceMember).where(
                TeamSpaceMember.space_id == cs.team_space_id,
                TeamSpaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        return None
    return cs if cs.user_id == user.id or cs.is_shared else None


async def list_sessions(
    db: AsyncSession,
    user: User,
    workspace_kind: str = "personal",
    team_space_id: int | None = None,
    agent_id: int | None = None,
    limit: int = 10,
    offset: int = 0,
    mine_only: bool = False,
):
    stmt = select(ChatSession, Agent.name.label("agent_name")).outerjoin(Agent, ChatSession.agent_id == Agent.id)
    if mine_only:
        stmt = stmt.where(ChatSession.user_id == user.id)
        if workspace_kind in ("personal", "team"):
            stmt = stmt.where(ChatSession.workspace_kind == workspace_kind)
        if team_space_id is not None:
            stmt = stmt.where(ChatSession.team_space_id == team_space_id)
    elif workspace_kind == "all":
        stmt = stmt.outerjoin(
            TeamSpaceMember,
            (TeamSpaceMember.space_id == ChatSession.team_space_id)
            & (TeamSpaceMember.user_id == user.id),
        ).where(
            or_(
                ChatSession.user_id == user.id,
                (
                    (ChatSession.workspace_kind == "team")
                    & (TeamSpaceMember.user_id == user.id)
                    & (ChatSession.is_shared.is_(True))
                ),
            )
        )
    elif workspace_kind == "team":
        stmt = stmt.join(TeamSpaceMember, TeamSpaceMember.space_id == ChatSession.team_space_id).where(
            ChatSession.workspace_kind == "team",
            TeamSpaceMember.user_id == user.id,
            or_(ChatSession.user_id == user.id, ChatSession.is_shared.is_(True)),
        )
        if team_space_id is not None:
            stmt = stmt.where(ChatSession.team_space_id == team_space_id)
    else:
        stmt = stmt.where(ChatSession.user_id == user.id, ChatSession.workspace_kind == "personal")
    if agent_id is not None:
        stmt = stmt.where(ChatSession.agent_id == agent_id)
    return (
        await db.execute(
            stmt.order_by(desc(ChatSession.updated_at), desc(ChatSession.created_at), ChatSession.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()


async def create_session(
    db: AsyncSession,
    user: User,
    title: str | None,
    agent_id: int | None,
    workspace_kind: str = "personal",
    team_space_id: int | None = None,
    is_shared: bool = False,
    project_id: int | None = None,
) -> ChatSession:
    # M3.4.2：绑定项目时，若未显式指定 agent，自动加载项目 Agent（§5.2）。
    if project_id is not None and agent_id is None:
        project = await db.get(Project, project_id)
        if project is not None and project.agent_id is not None:
            agent_id = project.agent_id
    cs = ChatSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        agent_id=agent_id,
        title=title or "新会话",
        workspace_kind=workspace_kind,
        team_space_id=team_space_id,
        is_shared=is_shared if workspace_kind == "team" else False,
        project_id=project_id,
    )
    db.add(cs)
    await db.commit()
    await db.refresh(cs)
    return cs


async def rename_session(db: AsyncSession, cs: ChatSession, title: str) -> ChatSession:
    cs.title = title
    await db.commit()
    await db.refresh(cs)
    return cs


async def delete_session(db: AsyncSession, cs: ChatSession) -> None:
    await db.delete(cs)
    await db.commit()
