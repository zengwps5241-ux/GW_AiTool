"""SSE 流式对话编排。"""

import asyncio
import json
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core import redis as redis_core
from app.core.config import _merged_env, get_settings, user_workspace
from app.db.session import async_session
from app.integrations.claude.guard import FileLockHookContext
from app.integrations.claude.runner import stream_chat
from app.integrations.claude.defense import apply_output_filter, defense_plugin_active
from app.integrations.claude.search_tools import SearchToolContext, search_plugin_active
from app.integrations.claude.tools import DraftToolContext
from app.integrations.openai import generate_chat_completion
from app.models import Agent, ChatSession, Project, User
from app.modules.agents.workdir import get_agent_workdir
from app.modules.projects.access import get_user_project_role
from app.modules.consultant.router import (
    log_routing,
    route_user_prompt,
    router_plugin_active,
)
from app.modules.catalog.commands import scan_agent_commands
from app.modules.sessions.run_state import RunEvent, RunStatus, run_state_store
from app.modules.team_spaces.file_locks import FileLockService, agent_lock_token
from app.modules.usage.service import collect_usage_resources, persist_usage_event
from app.modules.workspace.scope import WorkspaceScope, team_workspace_scope

logger = logging.getLogger(__name__)

WORKFLOW_TO_SKILL: dict[str, str] = {
    "hypothesis_map": "consultant-hypothesis-map",
    "interview_summary": "consultant-interview",
    "stakeholder_card": "consultant-stakeholder",
    "visit_plan": "consultant-visit-plan",
    "current_map_verify": "consultant-verify",
}
SKILL_TO_WORKFLOW: dict[str, str] = {skill: wf for wf, skill in WORKFLOW_TO_SKILL.items()}

WORKFLOW_INITIAL_STAGE: dict[str, str] = {
    "hypothesis_map": "A",
    "interview_summary": "draft",
    "stakeholder_card": "draft",
    "visit_plan": "draft",
    "current_map_verify": "draft",
}

PERSISTENT_WORKFLOWS: set[str] = {
    "hypothesis_map",
    "interview_summary",
    "stakeholder_card",
    "current_map_verify",
}


def _workflow_from_slash_prompt(prompt: str) -> str | None:
    match = re.match(r"^\s*/([^\s]+)", prompt)
    if not match:
        return None
    command = match.group(1)
    return SKILL_TO_WORKFLOW.get(command)

_active_stops: dict[str, asyncio.Event] = {}
_session_locks: dict[str, asyncio.Lock] = {}


def _session_lock_for(session_id: str) -> asyncio.Lock:
    """同一会话的 run start 与元数据回写必须串行，避免旧 run 覆盖新 run。"""
    lock = _session_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_id] = lock
    return lock


def _make_title(prompt: str) -> str:
    snippet = prompt.strip().splitlines()[0] if prompt.strip() else "新会话"
    return snippet[:30]


def _clean_generated_title(title: str) -> str:
    """清理模型可能返回的引号、换行和解释性标点。"""
    cleaned = re.sub(r"\s+", " ", title).strip(" \t\r\n\"'“”‘’")
    return cleaned[:30]


async def _make_semantic_title(prompt: str) -> str:
    """使用大模型根据首条用户消息生成会话标题，失败时返回本地兜底标题。"""
    fallback = _make_title(prompt)
    env = _merged_env()
    api_key = env.get("ANTHROPIC_PROVIDER_DEEPSEEK_AUTH_TOKEN", "").strip()
    if not api_key or not prompt.strip():
        return fallback

    try:
        title = await generate_chat_completion(
            api_key=api_key,
            base_url=env.get("SESSION_TITLE_OPENAI_BASE_URL", "https://api.deepseek.com").strip()
            or "https://api.deepseek.com",
            model=env.get("SESSION_TITLE_OPENAI_MODEL", "deepseek-v4-flash").strip()
            or "deepseek-v4-flash",
            system_prompt=(
                "你是会话标题生成器。请根据用户的第一条消息生成一个简洁、准确的中文会话名称。"
                "只输出标题本身，不要解释，不要加引号，长度控制在6到18个中文字符。"
            ),
            user_prompt=prompt,
            thinking={"type": "enabled"},
            reasoning_effort="high",
            timeout=10.0,
        )
    except Exception:
        logger.exception("Semantic session title generation failed")
        return fallback

    cleaned = _clean_generated_title(title)
    return cleaned or fallback


def _run_event_from_stream_event(evt: dict) -> RunEvent:
    """将 Claude SSE 事件转换为可恢复运行态事件。"""
    content = evt.get("content")
    if content is None:
        content = evt.get("text")
    message = evt.get("message")
    return RunEvent(
        type=str(evt.get("type", "message")),
        content=content if isinstance(content, str) else None,
        message=message if isinstance(message, str) else None,
        payload=evt,
    )


def _chat_event_from_run_event(event: RunEvent) -> dict:
    """将缓存中的 RunEvent 转成前端 ChatEvent 兼容结构。"""
    if event.payload:
        return dict(event.payload)

    data: dict = {"type": event.type}
    if event.content is not None:
        data["text"] = event.content
        data["content"] = event.content
    if event.message is not None:
        data["message"] = event.message
    return data


def _running_snapshot_to_dict(snapshot) -> dict:
    events = [
        {"seq": event.seq, "event": _chat_event_from_run_event(event)}
        for event in snapshot.events
    ]
    return {
        "running": snapshot.status == RunStatus.RUNNING,
        "run_id": snapshot.run_id,
        "status": str(snapshot.status),
        "events": events,
        "latest_seq": snapshot.latest_seq,
        "error_message": snapshot.error_message,
    }


def get_running_session_state(session_id: str) -> dict:
    """查询会话最近一轮运行态，供前端刷新后恢复。"""
    snapshot = run_state_store.snapshot(session_id, after_seq=0)
    if snapshot is None:
        return {
            "running": False,
            "status": str(RunStatus.COMPLETED),
            "events": [],
            "latest_seq": 0,
        }
    return _running_snapshot_to_dict(snapshot)


def stream_running_session(session_id: str, after_seq: int) -> StreamingResponse:
    """从指定 seq 后恢复输出缓存事件，并在运行中继续等待新增事件。"""

    async def event_source():
        current_seq = max(after_seq, 0)
        current_run_id: str | None = None

        while True:
            snapshot = run_state_store.snapshot(session_id, after_seq=current_seq)
            if snapshot is None:
                return
            if current_run_id is not None and snapshot.run_id != current_run_id:
                current_seq = 0
                snapshot = run_state_store.snapshot(session_id, after_seq=current_seq)
                if snapshot is None:
                    return
            if current_seq > snapshot.latest_seq:
                # 客户端可能带着上一轮 run 的 seq 重连；当前 run 的 seq 会重新从 1 开始。
                current_seq = 0
                snapshot = run_state_store.snapshot(session_id, after_seq=current_seq)
                if snapshot is None:
                    return
            current_run_id = snapshot.run_id

            for event in snapshot.events:
                current_seq = max(current_seq, event.seq)
                payload = {"seq": event.seq, "event": _chat_event_from_run_event(event)}
                yield f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

            if snapshot.status != RunStatus.RUNNING:
                return

            await run_state_store.wait_for_change(
                session_id,
                after_seq=current_seq,
                timeout=15,
            )

    return StreamingResponse(event_source(), media_type="text/event-stream")


async def _scope_for_session(db, user: User, cs: ChatSession) -> WorkspaceScope:
    if getattr(cs, "workspace_kind", "personal") == "team":
        return await team_workspace_scope(db, user, getattr(cs, "team_space_id", None))
    return WorkspaceScope(
        kind="personal",
        key=user.username,
        root=user_workspace(user.username),
        display_name="个人空间",
        can_read=True,
        can_write=True,
    )


async def _build_draft_context(
    db,
    *,
    project_id: int | None,
    user: User,
    source_session_id: str,
    publish: Callable[[dict[str, Any]], Awaitable[None]],
) -> DraftToolContext | None:
    """会话绑定项目且当前用户仍是项目成员时，构造草稿工具上下文（M3.4.2）。

    - 未绑定项目 → None（不挂载草稿工具）
    - 用户已退出项目（role 为 None）→ None（防御：避免向无权项目写草稿）
    - 否则返回注入了 project_id/user_id/source_session_id/publish 的 DraftToolContext

    入参显式传 project_id/source_session_id（不依赖 cs 对象），便于后台 runner
    在请求会话关闭后安全调用，也便于单测。
    """
    if project_id is None:
        return None
    role = await get_user_project_role(db, project_id, user)
    if role is None:
        logger.warning(
            "用户 %s 在项目 %s 已无权限，会话 %s 不挂载草稿工具",
            user.id, project_id, source_session_id,
        )
        return None
    return DraftToolContext(
        project_id=project_id,
        user_id=user.id,
        source_session_id=source_session_id,
        publish=publish,
    )


async def _build_draft_brief(db, project_id: int) -> str | None:
    """读取项目当前待采纳草稿，生成供 AI「基于原文+指令重新生成」的上下文摘要（§7.2）。

    M3.4.3 Chat 调整循环：项目存在 active 业务地图草稿或 draft 态角色卡/拜访记录时，
    把它们概要注入 system prompt，使 AI 在用户用自然语言提出修改时，能基于当前草稿原文
    重新调用草稿工具覆盖更新（而非凭空新建重复草稿）。无任何待采纳草稿时返回 None。
    """
    from app.models import StakeholderCard, VisitRecord
    from app.modules.business_map import service as bm_svc

    lines: list[str] = []
    # 业务地图：active 草稿（整图草稿单元）
    draft = await bm_svc.get_active_draft(db, project_id)
    if draft is not None:
        specs = bm_svc._extract_object_specs(draft.draft_data)
        ready_for_adoption = bm_svc.is_draft_ready_for_adoption(draft.draft_data)
        by_level: dict[str, list[str]] = {}
        for spec in specs:
            by_level.setdefault(str(spec.get("level", "?")), []).append(
                str(spec.get("name", "?"))
            )
        if by_level:
            level_desc = " / ".join(
                f"{lv}：{'、'.join(ns[:8])}{'…' if len(ns) > 8 else ''}"
                for lv, ns in sorted(by_level.items())
            )
        else:
            level_desc = "（空）"
        rev = getattr(draft, "revision", 1) or 1
        label = "业务地图草稿" if ready_for_adoption else "假设地图构建中草稿"
        lines.append(f"- {label}（第 {rev} 版，{len(specs)} 个节点）：{level_desc}")
    # 角色卡：draft 态
    cards = (
        await db.execute(
            select(StakeholderCard).where(
                StakeholderCard.project_id == project_id,
                StakeholderCard.review_status == "draft",
            )
        )
    ).scalars().all()
    if cards:
        desc = " / ".join(f"{c.name}（{c.role_type or '未分类'}）" for c in cards[:10])
        lines.append(f"- 角色卡草稿（{len(cards)} 张草稿态）：{desc}")
    # 拜访记录：draft 态
    visits = (
        await db.execute(
            select(VisitRecord).where(
                VisitRecord.project_id == project_id,
                VisitRecord.review_status == "draft",
            )
        )
    ).scalars().all()
    if visits:
        desc = " / ".join(
            (
                f"{v.visit_date.isoformat() if v.visit_date else '未定'} {v.visit_type or ''}"
            ).strip()
            for v in visits[:10]
        )
        lines.append(f"- 拜访记录草稿（{len(visits)} 条草稿态）：{desc}")
    if not lines:
        return None
    return (
        "【当前草稿状态】用户可能基于以下草稿用自然语言提出修改。"
        "若用户要求调整，应基于原文+用户指令重新调用对应草稿工具更新"
        "（假设地图构建中草稿按阶段保存；已完成业务地图草稿可整图覆盖；"
        "角色卡/拜访记录需带 update_draft_id 更新对应草稿，避免新建重复草稿），"
        "更新后主动询问用户下一步：\n" + "\n".join(lines)
    )


async def stream_session_chat(
    cs: ChatSession,
    user: User,
    prompt: str,
    agent: Agent | None = None,
    model: str | None = None,
    thinking_level: str = "low",
    workflow_type: str | None = None,
) -> StreamingResponse:
    prior_session_id = cs.claude_session_id
    is_first_message = prior_session_id is None
    if getattr(cs, "workspace_kind", "personal") == "team":
        async with async_session() as s:
            fresh = await s.get(ChatSession, cs.id)
            scope = await _scope_for_session(s, user, fresh or cs)
    else:
        scope = await _scope_for_session(None, user, cs)
    ws = scope.root
    session_id = cs.id
    # M3.4.2：项目绑定在 runner 前捕获为局部量（runner 在请求会话关闭后仍可能运行，
    # 且后台 runner 不直接访问 cs 对象，与 session_id/prior_session_id 同处理）。
    project_id = getattr(cs, "project_id", None)
    requested_workflow_type = (workflow_type or "").strip() or _workflow_from_slash_prompt(prompt)
    if requested_workflow_type is not None and requested_workflow_type not in WORKFLOW_TO_SKILL:
        raise ValueError(f"不支持的工作流类型: {requested_workflow_type}")
    active_workflow_type = (
        getattr(cs, "workflow_type", None)
        if getattr(cs, "workflow_status", None) == "active"
        else None
    )
    if requested_workflow_type is not None:
        if project_id is None:
            raise ValueError("业务工作流必须绑定项目")
        if active_workflow_type is not None and active_workflow_type != requested_workflow_type:
            raise ValueError("当前会话已有未完成工作流，不能启动新的工作流")
    workflow_to_start = (
        requested_workflow_type
        if active_workflow_type is None and requested_workflow_type in PERSISTENT_WORKFLOWS
        else None
    )
    effective_workflow_type = requested_workflow_type or active_workflow_type
    if effective_workflow_type is not None and project_id is None:
        raise ValueError("业务工作流必须绑定项目")
    run_id = str(uuid.uuid4())
    async with _session_lock_for(session_id):
        run_state_store.start(session_id, run_id)
        run_state_store.append_event(
            session_id,
            RunEvent(type="user_text", payload={"type": "user_text", "text": prompt}),
            run_id=run_id,
        )

    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    stop_event = asyncio.Event()
    _active_stops[session_id] = stop_event

    started_at = datetime.now(timezone.utc)
    tool_uses: list[dict] = []
    tool_results: list[dict] = []
    finalized = False
    sse_active = True

    async def publish_to_sse(evt: dict) -> None:
        """当前 SSE 仍连接时才推送；断开后 runner 只继续写运行态。"""
        if sse_active:
            await queue.put(evt)

    async def on_message(evt: dict) -> None:
        # M3.3.3 防线2：对 LLM 文本产出做确定性指纹过滤（never_visible）。
        # 仅过滤 assistant_text；思维链（assistant_thinking）不过滤（§8.2）。
        if (
            defense_plugin_active(agent)
            and evt.get("type") == "assistant_text"
            and evt.get("text")
        ):
            evt = {**evt, "text": apply_output_filter(evt["text"])}
        if evt.get("type") == "tool_use":
            tool_uses.append(evt)
        elif evt.get("type") == "tool_result":
            tool_results.append(evt)
        run_state_store.append_event(
            session_id,
            _run_event_from_stream_event(evt),
            run_id=run_id,
        )
        await publish_to_sse(evt)

    async def publish_draft_event(evt: dict) -> None:
        """草稿「待采纳」事件：与 tool_use/tool_result 同走 run_state + SSE（M3.4.2）。

        run_state 入栈保证客户端断开重连（/running/stream）仍可回放草稿卡片。
        """
        run_state_store.append_event(
            session_id,
            _run_event_from_stream_event(evt),
            run_id=run_id,
        )
        await publish_to_sse(evt)

    def finish_run_state(summary, error_message: str | None = None) -> None:
        if summary is None:
            status = RunStatus.FAILED
        elif summary.interrupted:
            status = RunStatus.INTERRUPTED
        elif summary.is_error:
            status = RunStatus.FAILED
        else:
            status = RunStatus.COMPLETED
        run_state_store.finish(
            session_id,
            status,
            error_message=error_message or (summary.error_message if summary else None),
            run_id=run_id,
        )

    async def finalize_usage(summary, error_message: str | None = None) -> None:
        """收尾会话状态并记录 usage，避免客户端断开造成漏统计。"""
        nonlocal finalized
        if finalized:
            return
        finalized = True

        new_sid = summary.session_id if summary else prior_session_id
        # 旧 run 可能晚于新 run 完成；校验和提交必须与新 run start 共用会话锁。
        async with _session_lock_for(session_id):
            if run_state_store.is_current_run(session_id, run_id):
                async with async_session() as s:
                    fresh = await s.get(ChatSession, session_id)
                    if fresh is not None:
                        if new_sid:
                            fresh.claude_session_id = new_sid
                        if is_first_message:
                            fresh.title = await _make_semantic_title(prompt)
                        if workflow_to_start is not None:
                            fresh.workflow_type = workflow_to_start
                            fresh.workflow_status = "active"
                            fresh.workflow_stage = WORKFLOW_INITIAL_STAGE.get(workflow_to_start)
                        fresh.updated_at = datetime.now(timezone.utc)
                        await s.commit()

        status_value = (
            "error" if error_message else
            "interrupted" if summary and summary.interrupted else
            "error" if summary and summary.is_error else
            "success"
        )

        commands = []
        if agent is not None:
            commands = scan_agent_commands(get_agent_workdir(agent.code))
        resources = collect_usage_resources(
            prompt=prompt,
            commands=commands,
            tool_uses=tool_uses,
            tool_results=tool_results,
        )

        # 持久化 usage 失败只记录日志，不影响聊天链路。
        try:
            await persist_usage_event(
                user=user,
                session_id=session_id,
                agent=agent,
                started_at=started_at,
                ended_at=datetime.now(timezone.utc),
                status=status_value,
                stop_reason=summary.stop_reason if summary else None,
                usage=summary.usage if summary else None,
                model_usage=summary.model_usage if summary else None,
                duration_ms=summary.duration_ms if summary else None,
                duration_api_ms=summary.duration_api_ms if summary else None,
                total_cost_usd=summary.total_cost_usd if summary else None,
                error_message=error_message or (summary.error_message if summary else None),
                resources=resources,
            )
        except Exception:
            logger.exception("Usage analytics persistence failed")

    async def runner() -> None:
        try:
            await on_message({"type": "assistant_thinking", "text": "正在准备业务工作流..."})
            # M3.3.1 consultant-router：项目 Agent 绑定路由 Plugin 时，对用户输入
            # 做意图路由（斜杠/chip 直达 / LLM 分类 / 关键词兜底 / chat 兜底），
            # 落 IntentRoutingLog，并把路由到 Skill 的提示改写为 /<skill> <原提示>
            # （复用 M3.4.1 斜杠命令机制）。失败只记日志，不阻断对话。
            routed_prompt = prompt
            if effective_workflow_type is not None:
                skill = WORKFLOW_TO_SKILL[effective_workflow_type]
                skill_prompt = (
                    prompt
                    if _workflow_from_slash_prompt(prompt) == effective_workflow_type
                    else f"/{skill} {prompt}"
                )
                workflow_action = "进入" if workflow_to_start is not None else "继续"
                if effective_workflow_type == "visit_plan":
                    workflow_rule = (
                        f"【工作流规则】用户已{workflow_action}拜访方案生成工作流。"
                        "这是文档归档类工作流，不调用业务草稿工具，也不会触发业务入库采纳卡片。"
                        "本轮生成完整拜访方案；如用户要求归档，使用 Write 保存到个人空间对应项目目录。"
                    )
                else:
                    workflow_rule = (
                        f"【工作流规则】用户已{workflow_action}该业务工作流。"
                        "中间阶段只通过自然语言确认、提问或修改推进；不要在中间阶段要求用户点击采纳按钮。"
                        "只有完整最终候选完成后，才调用对应候选/草稿保存工具，触发最终采纳卡片。"
                    )
                routed_prompt = f"{skill_prompt}\n\n{workflow_rule}"
            elif router_plugin_active(agent):
                try:
                    decision = await route_user_prompt(agent=agent, prompt=prompt)
                    async with async_session() as s:
                        await log_routing(
                            s,
                            session_id=session_id,
                            project_id=project_id,
                            user_id=user.id,
                            prompt=prompt,
                            decision=decision,
                        )
                    routed_prompt = decision.final_prompt
                except Exception:
                    logger.warning("意图路由失败，按原始提示继续", exc_info=True)
            stream_kwargs = {
                "prompt": routed_prompt,
                "claude_session_id": prior_session_id,
                "user_workspace": ws,
                "agent": agent,
                "on_message": on_message,
                "stop_event": stop_event,
            }
            if not scope.can_write:
                stream_kwargs["can_write"] = False
                stream_kwargs["readonly_reason"] = scope.readonly_reason
            if scope.kind == "team":
                stream_kwargs["file_lock_context"] = FileLockHookContext(
                    space_id=int(scope.key),
                    user_id=user.id,
                    session_id=str(session_id),
                )
            # 未显式选择时沿用 runner 的默认模型和默认思考级别。
            if model is not None:
                stream_kwargs["model"] = model
            if thinking_level != "low":
                stream_kwargs["thinking_level"] = thinking_level
            # M3.4.2/M3.4.3：项目级会话挂载草稿工具（绑定项目且当前用户仍为成员），
            # 并把当前待采纳草稿摘要注入 system prompt（§7.2 Chat 调整循环——使 AI
            # 基于原文+指令重新生成并覆盖更新草稿，而非新建重复草稿）。
            if project_id is not None and effective_workflow_type in PERSISTENT_WORKFLOWS:
                draft_brief: str | None = None
                async with async_session() as s:
                    draft_context = await _build_draft_context(
                        s,
                        project_id=project_id,
                        user=user,
                        source_session_id=session_id,
                        publish=publish_draft_event,
                    )
                    if draft_context is not None:
                        draft_brief = await _build_draft_brief(s, project_id)
                if draft_context is not None:
                    stream_kwargs["draft_context"] = draft_context
                    if draft_brief:
                        stream_kwargs["draft_brief"] = draft_brief
            # M3.3.2 consultant-search：项目 Agent 绑定搜索 Plugin 时挂载 3 个搜索工具
            # （search_web/search_company_registry/fetch_webpage），结果归档个人空间。
            # workspace_root 来自会话工作区；project/user/session 经闭包注入 handler。
            # M5.5.8：解析 project_name 传入 SearchToolContext，归档按项目名归类（§6.2）。
            if search_plugin_active(agent):
                _project_name: str | None = None
                if project_id is not None:
                    async with async_session() as _s:
                        _proj = await _s.get(Project, project_id)
                        _project_name = _proj.name if _proj else None
                stream_kwargs["search_context"] = SearchToolContext(
                    workspace_root=ws,
                    project_id=project_id,
                    user_id=user.id,
                    source_session_id=session_id,
                    project_name=_project_name,
                )
            await on_message({"type": "assistant_thinking", "text": "正在连接模型服务..."})

            summary = await stream_chat(**stream_kwargs)
            await finalize_usage(summary)
            finish_run_state(summary, summary.error_message)
            await publish_to_sse({"__internal": "done", "summary": summary})
        except Exception as exc:
            logger.exception("Claude stream failed")
            error_message = str(exc)
            error_event = {"type": "error", "message": error_message}
            run_state_store.append_event(
                session_id,
                _run_event_from_stream_event(error_event),
                run_id=run_id,
            )
            await publish_to_sse(error_event)
            await finalize_usage(None, error_message)
            finish_run_state(None, error_message)
            await publish_to_sse({"__internal": "done", "summary": None, "error_message": error_message})
        finally:
            if scope.kind == "team":
                settings = get_settings()
                file_lock_service = FileLockService(
                    redis_core.get_redis_client(),
                    ttl_seconds=settings.team_space_file_lock_ttl_seconds,
                    cleanup_grace_seconds=settings.team_space_file_lock_cleanup_grace_seconds,
                )
                await file_lock_service.release_owner_locks(agent_lock_token(str(session_id)))
            if _active_stops.get(session_id) is stop_event:
                _active_stops.pop(session_id, None)

    def _consume_runner_result(task: asyncio.Task) -> None:
        """后台 runner 脱离 SSE 后仍需取出异常，避免未读取异常告警。"""
        if task.cancelled():
            logger.warning("Claude runner task cancelled")
            return
        exc = task.exception()
        if exc is not None:
            logger.exception("Claude runner task failed", exc_info=exc)

    runner_task = asyncio.create_task(runner())
    runner_task.add_done_callback(_consume_runner_result)

    async def event_source():
        nonlocal sse_active
        try:
            while True:
                evt = await queue.get()
                if evt is None:
                    break
                if evt.get("__internal") == "done":
                    break
                yield f"event: message\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n"
        finally:
            # SSE 连接断开只代表订阅结束，不能取消或等待后台 agent runner。
            sse_active = False

    return StreamingResponse(event_source(), media_type="text/event-stream")


async def stop_session(session_id: str) -> dict:
    ev = _active_stops.get(session_id)
    if ev is not None:
        ev.set()
        return {"stopped": True}
    return {"stopped": False, "message": "当前没有正在执行的对话"}
