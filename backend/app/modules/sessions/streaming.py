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

from app.core import redis as redis_core
from app.core.config import _merged_env, get_settings, user_workspace
from app.db.session import async_session
from app.integrations.claude.guard import FileLockHookContext
from app.integrations.claude.runner import stream_chat
from app.integrations.claude.tools import DraftToolContext
from app.integrations.openai import generate_chat_completion
from app.models import Agent, ChatSession, User
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


async def stream_session_chat(
    cs: ChatSession,
    user: User,
    prompt: str,
    agent: Agent | None = None,
    model: str | None = None,
    thinking_level: str = "low",
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
            # M3.3.1 consultant-router：项目 Agent 绑定路由 Plugin 时，对用户输入
            # 做意图路由（斜杠/chip 直达 / LLM 分类 / 关键词兜底 / chat 兜底），
            # 落 IntentRoutingLog，并把路由到 Skill 的提示改写为 /<skill> <原提示>
            # （复用 M3.4.1 斜杠命令机制）。失败只记日志，不阻断对话。
            routed_prompt = prompt
            if router_plugin_active(agent):
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
            # M3.4.2：项目级会话挂载草稿工具（绑定项目且当前用户仍为成员）。
            # 草稿工具经 DraftToolContext 闭包把 project/user/session 注入 handler，
            # AI 调用 save_xxx_draft → 校验落库 → publish_draft_event 推送「待采纳」。
            if project_id is not None:
                async with async_session() as s:
                    draft_context = await _build_draft_context(
                        s,
                        project_id=project_id,
                        user=user,
                        source_session_id=session_id,
                        publish=publish_draft_event,
                    )
                if draft_context is not None:
                    stream_kwargs["draft_context"] = draft_context
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
