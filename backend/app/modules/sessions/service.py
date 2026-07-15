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
    project_id: int | None = None,
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
    # M7.1：项目过滤（决策 #72/#77）——传 project_id 则仅返回该项目会话（自动排除
    # project_id 为 null 的自由对话会话）；不传则全量（含 null 自由对话会话）。
    # 与上述 workspace_kind/mine_only 过滤 AND 叠加，个人/团队/全部三分支通用。
    # 会话可见性仍由现有闭环兜底（personal 仅本人 / TeamSpaceMember 成员），不额外查项目权限。
    if project_id is not None:
        stmt = stmt.where(ChatSession.project_id == project_id)
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
    # 审计埋点（决策 #64）
    from app.modules.audit.service import log_audit

    await log_audit(
        db, user.id, "create", "session", cs.id,
        detail={"after": {"title": cs.title, "project_id": cs.project_id,
                          "workspace_kind": cs.workspace_kind}},
    )
    return cs


async def rename_session(db: AsyncSession, cs: ChatSession, title: str) -> ChatSession:
    cs.title = title
    await db.commit()
    await db.refresh(cs)
    return cs


async def delete_session(db: AsyncSession, cs: ChatSession) -> None:
    # 审计快照：删除前（commit 后 cs 对象 expired，先捕获 id/title）
    session_id = cs.id
    actor_id = cs.user_id
    before = {"title": cs.title, "project_id": cs.project_id}
    await db.delete(cs)
    await db.commit()
    # 审计埋点（决策 #64）
    from app.modules.audit.service import log_audit

    await log_audit(
        db, actor_id, "delete", "session", session_id,
        detail={"before": before},
    )


async def save_knowledge_fragment(
    db: AsyncSession,
    cs: ChatSession,
    user: User,
    content: str,
    title: str | None = None,
) -> dict:
    """将一段对话内容标记为「有价值的知识片段」，落盘到用户个人空间。

    规格依据：§2.6 line157 — 对话「标记为有价值」→ 个人空间对应项目目录下的
    Markdown 知识片段；§6.2 资产矩阵 line1126 存放于 ``个人空间/项目名/知识片段/``。

    路径规则：``{项目名}/知识片段/{时间戳}_{标题}.md``；会话未绑项目时落到根
    ``知识片段/``。文件名经 ``safe_filename`` 净化（防路径穿越 / Windows 非法符），
    同秒冲突自动追加序号。返回相对个人空间根的路径，供前端提示用户。
    """
    from datetime import datetime

    from app.core.config import user_workspace
    from app.core.utils import safe_filename
    from app.modules.workspace.paths import resolve_inside_workspace

    # 1. 解析项目名（决定落盘子目录；未绑项目则落根 知识片段/）
    project_name: str | None = None
    if getattr(cs, "project_id", None) is not None:
        project = await db.get(Project, cs.project_id)
        project_name = project.name if project else None

    dir_parts = ["知识片段"]
    if project_name:
        pn = safe_filename(project_name)
        if pn and pn != "file":
            dir_parts.insert(0, pn)
    dir_rel = "/".join(dir_parts)

    # 2. 文件名标题：显式 > 内容首行 > 兜底
    raw_title = (title or "").strip()
    if not raw_title:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped:
                raw_title = stripped
                break
    stem = safe_filename(raw_title or "知识片段") or "知识片段"
    stem = stem[:40]  # 限长，避免标题过长致整路径超限

    # 3. 唯一化文件名（同秒冲突追加 _2/_3）
    workspace = user_workspace(user.username)
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")
    suffix = 0
    while True:
        name = f"{ts}_{stem}.md" if suffix == 0 else f"{ts}_{stem}_{suffix}.md"
        rel = f"{dir_rel}/{name}"
        target = resolve_inside_workspace(workspace, rel)
        if not target.exists():
            break
        suffix += 1

    # 4. 组装 Markdown：HTML 注释记来源（复盘用，渲染不可见）+ 正文
    meta = (
        "<!-- 知识片段来源："
        f"会话「{cs.title or ''}」"
        + (f" · 项目「{project_name}」" if project_name else "")
        + f" · 标记时间 {now.strftime('%Y-%m-%d %H:%M:%S')} -->\n\n"
    )
    body = meta + content.strip() + "\n"

    # 5. 落盘（建父目录 + utf-8）
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")

    return {
        "path": target.relative_to(workspace.resolve()).as_posix(),
        "filename": target.name,
        "project_name": project_name,
    }
