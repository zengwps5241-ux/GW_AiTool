"""Usage analytics 采集与聚合服务。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import case, distinct, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from app.db.session import async_session
from app.models import Department, UsageEvent, UsageResourceEvent, User

logger = logging.getLogger(__name__)

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class CollectedResource:
    resource_type: str
    resource_name: str
    plugin_name: str | None
    source: str
    tool_use_id: str | None
    is_error: bool


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    return 0


def extract_token_counts(
    usage: dict[str, Any] | None,
    model_usage: dict[str, Any] | None = None,
) -> tuple[int, int, int]:
    """从 SDK usage/model_usage 中提取输入、输出和总 token。"""
    if isinstance(usage, dict):
        input_tokens = _int_value(usage.get("input_tokens"))
        output_tokens = _int_value(usage.get("output_tokens"))
        if input_tokens or output_tokens:
            return input_tokens, output_tokens, input_tokens + output_tokens

    input_total = 0
    output_total = 0
    if isinstance(model_usage, dict):
        for value in model_usage.values():
            if not isinstance(value, dict):
                continue
            input_total += _int_value(value.get("input_tokens"))
            output_total += _int_value(value.get("output_tokens"))
    return input_total, output_total, input_total + output_total


def _skill_name_from_input(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if not isinstance(value, dict):
        return None
    for key in ("skill", "name", "command"):
        raw = value.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip().lstrip("/")
    return None


def _resource_from_command(command: str, *, source: str, tool_use_id: str | None, is_error: bool) -> CollectedResource:
    if ":" in command:
        plugin_name = command.split(":", 1)[0]
        return CollectedResource("plugin", command, plugin_name, source, tool_use_id, is_error)
    return CollectedResource("skill", command, None, source, tool_use_id, is_error)


def _prompt_commands(prompt: str) -> list[str]:
    return [match.group(1) for match in re.finditer(r"(?<!\S)/([A-Za-z0-9_.:-]+)", prompt)]


def collect_usage_resources(
    *,
    prompt: str,
    commands: list[dict[str, Any]],
    tool_uses: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
) -> list[CollectedResource]:
    """根据 tool_use/tool_result 与 slash command 收集实际资源使用。"""
    result_errors = {
        str(item.get("tool_use_id")): bool(item.get("is_error", False))
        for item in tool_results
        if item.get("tool_use_id")
    }
    collected: list[CollectedResource] = []
    seen: set[tuple[str, str, str, str | None]] = set()

    def add(resource: CollectedResource) -> None:
        key = (resource.resource_type, resource.resource_name, resource.source, resource.tool_use_id)
        if key in seen:
            return
        seen.add(key)
        collected.append(resource)

    for evt in tool_uses:
        if evt.get("name") != "Skill":
            continue
        command = _skill_name_from_input(evt.get("input"))
        if not command:
            continue
        tool_use_id = str(evt.get("id") or "") or None
        add(_resource_from_command(
            command,
            source="tool_use",
            tool_use_id=tool_use_id,
            is_error=result_errors.get(tool_use_id or "", False),
        ))

    command_map = {str(item.get("name")): item for item in commands}
    for command in _prompt_commands(prompt):
        meta = command_map.get(command)
        if meta is None:
            continue
        source = str(meta.get("source") or "")
        if source == "plugin":
            plugin_name = str(meta.get("plugin") or command.split(":", 1)[0])
            add(CollectedResource("plugin", command, plugin_name, "slash_command", None, False))
        elif source == "skill":
            add(CollectedResource("skill", command, None, "slash_command", None, False))
    return collected


async def persist_usage_event(
    *,
    user,
    session_id: str,
    agent,
    started_at: datetime,
    ended_at: datetime,
    status: str,
    stop_reason: str | None,
    usage: dict[str, Any] | None,
    model_usage: dict[str, Any] | None,
    duration_ms: int | None,
    duration_api_ms: int | None,
    total_cost_usd: float | Decimal | None,
    error_message: str | None,
    resources: list[CollectedResource],
) -> None:
    """保存一轮对话统计；调用方负责捕获异常以保护聊天链路。"""
    input_tokens, output_tokens, total_tokens = extract_token_counts(usage, model_usage)
    cost = Decimal(str(total_cost_usd)) if total_cost_usd is not None else None
    async with async_session() as session:
        event = UsageEvent(
            user_id=user.id,
            username=user.username,
            session_id=session_id,
            agent_id=agent.id if agent else None,
            agent_name=agent.name if agent else None,
            agent_code=agent.code if agent else None,
            started_at=started_at,
            ended_at=ended_at,
            status=status,
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            duration_api_ms=duration_api_ms,
            total_cost_usd=cost,
            sdk_usage_json=usage,
            sdk_model_usage_json=model_usage,
            error_message=error_message[:1000] if error_message else None,
        )
        session.add(event)
        await session.flush()
        for item in resources:
            session.add(UsageResourceEvent(
                usage_event_id=event.id,
                resource_type=item.resource_type,
                resource_name=item.resource_name,
                plugin_name=item.plugin_name,
                source=item.source,
                tool_use_id=item.tool_use_id,
                is_error=item.is_error,
            ))
        await session.commit()


def resolve_usage_window(range_name: str, start: date | None, end: date | None) -> tuple[datetime, datetime, str, str, str]:
    today = datetime.now(SHANGHAI_TZ).date()
    if range_name == "today":
        local_start = datetime.combine(today, time.min, tzinfo=SHANGHAI_TZ)
        local_end = local_start + timedelta(days=1)
        granularity = "hour"
    elif range_name == "7d":
        local_start = datetime.combine(today - timedelta(days=6), time.min, tzinfo=SHANGHAI_TZ)
        local_end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=SHANGHAI_TZ)
        granularity = "day"
    elif range_name == "30d":
        local_start = datetime.combine(today - timedelta(days=29), time.min, tzinfo=SHANGHAI_TZ)
        local_end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=SHANGHAI_TZ)
        granularity = "day"
    elif range_name == "custom" and start and end:
        local_start = datetime.combine(start, time.min, tzinfo=SHANGHAI_TZ)
        local_end = datetime.combine(end + timedelta(days=1), time.min, tzinfo=SHANGHAI_TZ)
        granularity = "hour" if start == end else "day"
    else:
        raise ValueError("无效的时间范围")
    return (
        local_start.astimezone(ZoneInfo("UTC")),
        local_end.astimezone(ZoneInfo("UTC")),
        granularity,
        local_start.date().isoformat(),
        (local_end.date() - timedelta(days=1)).isoformat(),
    )


async def build_usage_summary(
    db: AsyncSession,
    *,
    range_name: str,
    start: date | None,
    end: date | None,
    username_filter: str | None = None,
    department_filter: str | None = None,
) -> dict:
    start_dt, end_dt, granularity, start_label, end_label = resolve_usage_window(range_name, start, end)
    conditions = [UsageEvent.started_at >= start_dt, UsageEvent.started_at < end_dt]
    if username_filter:
        conditions.append(UsageEvent.username == username_filter)

    # 部门过滤需要关联 User 表，且先走 departments 表匹配名称得到ID
    need_user_join = bool(department_filter)
    matched_dept_ids: list[int] = []
    if department_filter:
        dept_result = await db.execute(
            select(Department.id).where(Department.name.ilike(f"%{department_filter}%"))
        )
        matched_dept_ids = [row[0] for row in dept_result.all()]

    def _apply_filters(stmt):
        if need_user_join:
            stmt = stmt.join(User, UsageEvent.user_id == User.id)
        stmt = stmt.where(*conditions)
        if department_filter:
            department_name_condition = User.department.ilike(f"%{department_filter}%")
            if matched_dept_ids:
                stmt = stmt.where(
                    or_(
                        department_name_condition,
                        text(
                            "EXISTS (SELECT 1 FROM jsonb_array_elements_text(users.department_ids::jsonb) AS elem WHERE elem::int = ANY(:dept_ids))"
                        ).bindparams(dept_ids=matched_dept_ids),
                    )
                )
            else:
                stmt = stmt.where(department_name_condition)
        return stmt

    overview_stmt = _apply_filters(
        select(
            func.count(UsageEvent.id),
            func.count(distinct(UsageEvent.user_id)),
            func.count(distinct(UsageEvent.agent_id)),
            func.coalesce(func.sum(UsageEvent.input_tokens), 0),
            func.coalesce(func.sum(UsageEvent.output_tokens), 0),
            func.coalesce(func.sum(UsageEvent.total_tokens), 0),
            func.coalesce(func.sum(case((UsageEvent.status == "error", 1), else_=0)), 0),
            func.coalesce(func.sum(case((UsageEvent.status == "interrupted", 1), else_=0)), 0),
            func.avg(UsageEvent.duration_ms),
        )
    )
    overview_row = (await db.execute(overview_stmt)).one()

    skill_stmt = _apply_filters(
        select(func.count(UsageResourceEvent.id))
        .join(UsageEvent, UsageEvent.id == UsageResourceEvent.usage_event_id)
    ).where(UsageResourceEvent.resource_type == "skill")
    skill_count = (await db.execute(skill_stmt)).scalar_one()

    plugin_stmt = _apply_filters(
        select(func.count(UsageResourceEvent.id))
        .join(UsageEvent, UsageEvent.id == UsageResourceEvent.usage_event_id)
    ).where(UsageResourceEvent.resource_type == "plugin")
    plugin_count = (await db.execute(plugin_stmt)).scalar_one()

    agents_stmt = _apply_filters(
        select(
            UsageEvent.agent_id,
            func.coalesce(UsageEvent.agent_name, "未选择智能体").label("agent_name"),
            func.count(UsageEvent.id).label("call_count"),
            func.count(distinct(UsageEvent.user_id)).label("active_user_count"),
            func.coalesce(func.sum(UsageEvent.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(case((UsageEvent.status == "error", 1), else_=0)), 0).label("error_count"),
        )
        .group_by(UsageEvent.agent_id, UsageEvent.agent_name)
        .order_by(func.count(UsageEvent.id).desc())
        .limit(10)
    )
    agents = (await db.execute(agents_stmt)).mappings().all()

    skills_stmt = _apply_filters(
        select(UsageResourceEvent.resource_name, func.count(UsageResourceEvent.id).label("trigger_count"))
        .join(UsageEvent, UsageEvent.id == UsageResourceEvent.usage_event_id)
        .group_by(UsageResourceEvent.resource_name)
        .order_by(func.count(UsageResourceEvent.id).desc())
        .limit(10)
    ).where(UsageResourceEvent.resource_type == "skill")
    skills = (await db.execute(skills_stmt)).mappings().all()

    plugins_stmt = _apply_filters(
        select(
            func.coalesce(UsageResourceEvent.plugin_name, "").label("plugin_name"),
            UsageResourceEvent.resource_name,
            func.count(UsageResourceEvent.id).label("trigger_count"),
        )
        .join(UsageEvent, UsageEvent.id == UsageResourceEvent.usage_event_id)
        .group_by(UsageResourceEvent.plugin_name, UsageResourceEvent.resource_name)
        .order_by(func.count(UsageResourceEvent.id).desc())
        .limit(10)
    ).where(UsageResourceEvent.resource_type == "plugin")
    plugins = (await db.execute(plugins_stmt)).mappings().all()

    status_stmt = _apply_filters(
        select(UsageEvent.status, func.count(UsageEvent.id).label("count"))
        .group_by(UsageEvent.status)
    )
    status_rows = (await db.execute(status_stmt)).mappings().all()

    # 先转换到北京时间再截桶，保证趋势按本地自然日/小时统计。
    bucket_expr = func.date_trunc(
        "hour" if granularity == "hour" else "day",
        func.timezone("Asia/Shanghai", UsageEvent.started_at),
    )
    series_stmt = _apply_filters(
        select(
            bucket_expr.label("bucket"),
            func.count(UsageEvent.id).label("call_count"),
            func.count(distinct(UsageEvent.user_id)).label("active_user_count"),
            func.coalesce(func.sum(UsageEvent.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(case((UsageEvent.status == "error", 1), else_=0)), 0).label("error_count"),
            func.coalesce(func.sum(UsageEvent.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(UsageEvent.output_tokens), 0).label("output_tokens"),
        )
        .group_by(bucket_expr)
        .order_by(bucket_expr)
    )
    series_rows = (await db.execute(series_stmt)).mappings().all()

    timeseries = [
        {
            "bucket": row["bucket"].replace(tzinfo=SHANGHAI_TZ).isoformat(),
            "call_count": row["call_count"],
            "active_user_count": row["active_user_count"],
            "total_tokens": row["total_tokens"],
            "error_count": row["error_count"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
        }
        for row in series_rows
    ]

    overview = {
        "call_count": overview_row[0],
        "active_user_count": overview_row[1],
        "agent_count": overview_row[2],
        "skill_trigger_count": skill_count,
        "plugin_trigger_count": plugin_count,
        "input_tokens": overview_row[3],
        "output_tokens": overview_row[4],
        "total_tokens": overview_row[5],
        "error_count": overview_row[6],
        "interrupted_count": overview_row[7],
        "avg_duration_ms": float(overview_row[8]) if overview_row[8] is not None else None,
    }
    return {
        "range": range_name,
        "start": start_label,
        "end": end_label,
        "granularity": granularity,
        "overview": overview,
        "timeseries": timeseries,
        "agents": [dict(row) for row in agents],
        "skills": [dict(row) for row in skills],
        "plugins": [dict(row) for row in plugins],
        "tokens": {
            "input_tokens": overview["input_tokens"],
            "output_tokens": overview["output_tokens"],
            "total_tokens": overview["total_tokens"],
            "timeseries": timeseries,
        },
        "status_breakdown": [dict(row) for row in status_rows],
    }
