"""AI 结构化草稿工具注册框架（M3.1）。

机制
----
用 ``claude_agent_sdk.create_sdk_mcp_server`` 把 3 个草稿工具注册为**进程内 MCP 工具**，
Claude 在对话中调用 ``mcp__<server>__<tool>`` 时，SDK 路由到本模块的 handler：

1. 按 JSON Schema 校验入参（M3.1.2）
2. 落库为草稿（M3.1.3）：
   - save_business_map_draft → ``BusinessMapDraft``（整图草稿单元，§7.1.7）
   - save_stakeholder_card_draft → ``StakeholderCard``（review_status=draft）
   - save_visit_record_draft → ``VisitRecord``（review_status=draft）
3. 通过 ``publish`` 回调向 SSE 推送「待采纳」事件（前端 M3.1.4 消费）
4. 返回工具结果文本给 Claude（告知已存草稿待用户采纳）

工具钩子位于 ``integrations/claude/``（与 ``guard.py`` 同包）。``guard.py`` 的 PreToolUse
安全钩子（Bash 黑名单 / 文件锁 / 只读）保持不变；草稿工具的拦截/校验/落库在 handler 内完成，
SDK 对草稿工具的权限仍由 ``tool_approval.auto_approve_tool`` 放行、安全边界由自身逻辑保证。

会话级上下文（project_id / user_id / source_session_id）由调用方（``runner.stream_chat``）
通过 ``DraftToolContext`` 闭包注入；会话↔项目绑定见 M3.4.2。
"""

from __future__ import annotations

import jsonschema
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

# ─── M3.1.2：三个草稿工具的输入 JSON Schema ──────────────────────
#
# 单一真源：既作为 Claude 工具定义（inputSchema），又作为 handler 入参校验依据。
# 草稿内容为自由 JSONB，此处只约束「结构化输出的骨架字段」，载荷内部（payload/
# objective_layer 等）不展开约束（与既有 schema 层风格一致，由 Skill/前端约定）。

SAVE_BUSINESS_MAP_DRAFT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "pre_analysis": {
            "type": "object",
            "description": "可选。假设地图草稿的项目前置分析；采纳业务地图草稿时会同步写入 pre_analyses。",
            "properties": {
                "industry_value_chain": {"type": "string"},
                "customer_position": {"type": "string"},
                "industry_trends": {"type": "string"},
                "strategic_positioning": {"type": "string"},
                "digitalization_drivers": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "objects": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["L1", "L2", "L3", "L4"]},
                    "name": {"type": "string", "minLength": 1},
                    "temp_id": {
                        "type": "string",
                        "description": "候选阶段临时节点 ID，如 L2-1。采纳时由后端映射为真实数据库 id。",
                    },
                    "parent_temp_id": {
                        "type": "string",
                        "description": "候选阶段父节点临时 ID，如 L1-1/L2-1/L3-1。采纳时由后端转换为 parent_id。",
                    },
                    "map_type": {"type": "string", "enum": ["hypothesis", "current"]},
                    "parent_id": {"type": "integer"},
                    "verification_status": {"type": "string"},
                    "linked_hypothesis_id": {"type": "integer"},
                    "payload": {"type": "object"},
                    "generated_by_ai": {"type": "boolean"},
                },
                "required": ["level", "name"],
                "additionalProperties": True,
            },
        }
    },
    "required": ["objects"],
    "additionalProperties": True,
}

SAVE_HYPOTHESIS_MAP_STAGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "stage": {
            "type": "string",
            "enum": ["pre_analysis", "L1", "L2", "L3", "L4"],
            "description": "当前已获用户确认并需要固化的假设地图阶段。",
        },
        "pre_analysis": SAVE_BUSINESS_MAP_DRAFT_SCHEMA["properties"]["pre_analysis"],
        "objects": SAVE_BUSINESS_MAP_DRAFT_SCHEMA["properties"]["objects"],
    },
    "required": ["stage"],
    "additionalProperties": True,
}

FINALIZE_HYPOTHESIS_MAP_DRAFT_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

SAVE_STAKEHOLDER_CARD_DRAFT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "position": {"type": "string"},
        "department": {"type": "string"},
        "reports_to": {"type": "string"},
        "contact_info": {"type": "string"},
        "role_type": {"type": "string"},
        "decision_power": {"type": "string"},
        "objective_layer": {"type": "object"},
        "subjective_layer": {"type": "object"},
        "behaviors": {"type": "array"},
        "update_draft_id": {
            "type": "integer",
            "description": "可选。增量更新指定草稿卡 id（§7.2 Chat 调整循环）。"
            "不传则新建草稿；传入则覆盖更新该草稿卡（保持草稿态，保留上一版供 diff）。",
        },
    },
    "required": ["name"],
    "additionalProperties": True,
}

SAVE_VISIT_RECORD_DRAFT_SCHEMA: dict = {
    "type": "object",
    "minProperties": 1,  # 至少一个字段（一句话记录可只给 summary）
    "properties": {
        "visit_date": {"type": "string", "format": "date"},
        "visit_type": {"type": "string"},
        "participants_our": {"type": "array"},
        "participants_client": {"type": "array"},
        "location": {"type": "string"},
        "duration": {"type": "string"},
        "summary": {"type": "string"},
        "next_steps": {"type": "string"},
        "key_takeaways": {"type": "array"},
        "related_card_ids": {"type": "array"},
        "update_draft_id": {
            "type": "integer",
            "description": "可选。增量更新指定草稿记录 id（§7.2 Chat 调整循环）。"
            "不传则新建草稿；传入则覆盖更新该草稿记录（保持草稿态，保留上一版供 diff）。",
        },
    },
    "additionalProperties": True,
}


def validate_tool_input(schema: dict, data: object) -> str | None:
    """按 JSON Schema 校验工具入参，返回首条错误信息（无错返回 None）。

    返回的人类可读信息会同时回写给 Claude（is_error=True），便于模型自我修正。
    """
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if not errors:
        return None
    first = errors[0]
    loc = ".".join(str(p) for p in first.path) or "<root>"
    return f"{loc}: {first.message}"


# ─── 工具结果 / 待采纳事件 构造 ─────────────────────────────────


@dataclass
class DraftToolContext:
    """单轮对话的草稿工具上下文（由 runner 注入，handler 闭包读取）。

    - project_id / user_id / source_session_id：落库归属与审计
    - publish：草稿落库后向 SSE 推送「待采纳」事件的回调
    """

    project_id: int
    user_id: int
    source_session_id: str | None
    publish: Callable[[dict[str, Any]], Awaitable[None]]


def _ok_result(text: str) -> dict:
    """构造 MCP 工具成功结果（文本回写给 Claude）。"""
    return {"content": [{"type": "text", "text": text}], "is_error": False}


def _error_result(text: str) -> dict:
    """构造 MCP 工具错误结果（is_error=True，Claude 可据以自我修正）。"""
    return {"content": [{"type": "text", "text": text}], "is_error": True}


def _draft_pending_event(
    entity_type: str,
    entity_label: str,
    draft_id: int,
    project_id: int,
    preview: dict[str, Any],
    *,
    previous: dict[str, Any] | None = None,
    revision: int | None = None,
    is_update: bool = False,
) -> dict[str, Any]:
    """构造 SSE「待采纳」事件（前端 M3.1.4 渲染为采纳/驳回卡片）。

    M3.4.3 Chat 调整循环：增量更新（is_update=True）时携带 previous（上一版内容快照）
    与 revision（修订号），供前端 diff 对比本次改动（§7.2）。首次生成不带 previous。
    """
    evt: dict[str, Any] = {
        "type": "draft_pending",
        "entity_type": entity_type,
        "entity_label": entity_label,
        "draft_id": draft_id,
        "project_id": project_id,
        "preview": preview,
        "is_update": is_update,
    }
    if previous is not None:
        evt["previous"] = previous
    if revision is not None:
        evt["revision"] = revision
    return evt


# ─── M3.4.3：草稿更新时的「上一版」字段快照（供前端 diff） ──────
#
# stakeholder/visit 草稿为实体行（review_status=draft），增量更新时直接覆盖字段，
# 故在覆盖前抓取关键字段快照作为 previous（不持久化到实体表，只在事件里携带供对比）。

_CARD_SNAPSHOT_FIELDS = (
    "name", "position", "department", "reports_to", "contact_info", "role_type",
    "decision_power", "objective_layer", "subjective_layer", "behaviors",
)
_VISIT_SNAPSHOT_FIELDS = (
    "visit_type", "summary", "participants_our", "participants_client",
    "location", "duration", "key_takeaways", "next_steps",
)


def _snapshot_card(card) -> dict[str, Any]:
    """抓取角色卡草稿关键字段快照（用于 diff）。"""
    return {f: getattr(card, f, None) for f in _CARD_SNAPSHOT_FIELDS}


def _snapshot_visit(visit) -> dict[str, Any]:
    """抓取拜访记录草稿关键字段快照（用于 diff），visit_date 转 ISO 字符串。"""
    snap = {f: getattr(visit, f, None) for f in _VISIT_SNAPSHOT_FIELDS}
    vd = getattr(visit, "visit_date", None)
    snap["visit_date"] = vd.isoformat() if vd is not None else None
    return snap


def _normalise_hypothesis_object(obj: dict[str, Any]) -> dict[str, Any]:
    """阶段保存时补齐假设地图节点默认字段，避免每个 Skill 都重复写样板。"""
    out = dict(obj)
    out.setdefault("map_type", "hypothesis")
    out.setdefault("verification_status", "未验证")
    out.setdefault("generated_by_ai", True)
    return out


def _merge_hypothesis_stage_data(
    current: dict[str, Any] | None, args: dict[str, Any]
) -> dict[str, Any]:
    """把已确认阶段合并到业务地图草稿 JSON。

    这里把 BusinessMapDraft.draft_data 当作假设地图工作流的轻量中间状态。
    每个阶段只替换同阶段内容，最终入库直接读取累计 JSON，避免最后让模型
    从长对话上下文重建整张地图。
    """
    stage = str(args.get("stage"))
    current_is_ready = isinstance(current, dict) and current.get("ready_for_adoption") is not False
    # 从 Step 1 开始的新工作流不应混入上一个已经完成但尚未处理的业务地图草稿。
    data: dict[str, Any] = {} if stage == "pre_analysis" and current_is_ready else (
        dict(current) if isinstance(current, dict) else {}
    )
    data.setdefault("candidate_type", "hypothesis_map")
    data.setdefault("map_type", "hypothesis")
    data["workflow_status"] = "building"
    data["ready_for_adoption"] = False
    stages = data.get("confirmed_stages")
    confirmed = [str(s) for s in stages] if isinstance(stages, list) else []

    if stage == "pre_analysis":
        pre_analysis = args.get("pre_analysis")
        if not isinstance(pre_analysis, dict):
            raise ValueError("pre_analysis 阶段必须提供 pre_analysis 对象")
        data["pre_analysis"] = pre_analysis
    else:
        incoming = args.get("objects")
        if not isinstance(incoming, list) or not incoming:
            raise ValueError(f"{stage} 阶段必须提供 objects 数组")
        objects = data.get("objects")
        existing = [o for o in objects if isinstance(o, dict)] if isinstance(objects, list) else []
        normalised = [
            _normalise_hypothesis_object(o)
            for o in incoming
            if isinstance(o, dict) and o.get("level") == stage and o.get("name")
        ]
        if not normalised:
            raise ValueError(f"{stage} 阶段没有可保存的有效节点")
        data["objects"] = [o for o in existing if o.get("level") != stage] + normalised

    if stage not in confirmed:
        confirmed.append(stage)
    data["confirmed_stages"] = confirmed
    return data


_PRE_ANALYSIS_FIELDS = (
    "industry_value_chain",
    "customer_position",
    "industry_trends",
    "strategic_positioning",
    "digitalization_drivers",
)


def _validate_hypothesis_map_ready(data: dict[str, Any] | None) -> str | None:
    """最终提交前校验累计 JSON 是否达到可采纳的最低结构要求。"""
    if not isinstance(data, dict):
        return "尚未保存任何假设地图阶段内容"
    if data.get("candidate_type") != "hypothesis_map":
        return "当前 active 草稿不是假设地图分阶段草稿"
    pre = data.get("pre_analysis")
    if not isinstance(pre, dict):
        return "缺少前置分析阶段"
    missing_pre = [k for k in _PRE_ANALYSIS_FIELDS if not pre.get(k)]
    if missing_pre:
        return "前置分析字段缺失：" + "、".join(missing_pre)
    objects = data.get("objects")
    specs = [o for o in objects if isinstance(o, dict)] if isinstance(objects, list) else []
    if not specs:
        return "缺少 L1-L4 节点"
    by_level: dict[str, list[dict[str, Any]]] = {lv: [] for lv in ("L1", "L2", "L3", "L4")}
    temp_ids: set[str] = set()
    for idx, spec in enumerate(specs):
        level = spec.get("level")
        if level in by_level:
            by_level[level].append(spec)
        temp_id = spec.get("temp_id") or spec.get("tempId") or f"__auto_{idx}"
        if temp_id in temp_ids:
            return f"节点临时 ID 重复：{temp_id}"
        temp_ids.add(str(temp_id))
    missing_levels = [lv for lv, nodes in by_level.items() if not nodes]
    if missing_levels:
        return "缺少层级节点：" + "、".join(missing_levels)
    for spec in specs:
        level = spec.get("level")
        if level in ("L2", "L3", "L4"):
            parent = spec.get("parent_temp_id") or spec.get("parentTempId")
            if not parent:
                return f"{level} 节点「{spec.get('name', '未命名')}」缺少 parent_temp_id"
            if str(parent) not in temp_ids:
                return f"{level} 节点「{spec.get('name', '未命名')}」的 parent_temp_id={parent} 找不到父节点"
    return None


def _business_map_preview(args: dict[str, Any]) -> dict[str, Any]:
    objects = args.get("objects", []) if isinstance(args, dict) else []
    pre_analysis = args.get("pre_analysis") if isinstance(args, dict) else None
    return {
        "object_count": len(objects) if isinstance(objects, list) else 0,
        "pre_analysis": pre_analysis if isinstance(pre_analysis, dict) else None,
        "objects": [
            {
                "temp_id": o.get("temp_id"),
                "parent_temp_id": o.get("parent_temp_id"),
                "level": o.get("level"),
                "name": o.get("name"),
                "map_type": o.get("map_type"),
                "parent_id": o.get("parent_id"),
                "payload": o.get("payload"),
            }
            for o in (objects if isinstance(objects, list) else [])
            if isinstance(o, dict)
        ],
    }


# ─── M3.1.3：草稿工具 handler（校验→落库→推送→回写 Claude） ─────


async def handle_save_business_map_draft(
    ctx: DraftToolContext, args: dict
) -> dict:
    """保存业务地图草稿（整图草稿单元，§7.1.7）→ BusinessMapDraft。"""
    err = validate_tool_input(SAVE_BUSINESS_MAP_DRAFT_SCHEMA, args)
    if err:
        return _error_result(f"save_business_map_draft 入参校验失败：{err}")

    from app.db.session import async_session
    from app.models import User
    from app.modules.business_map import service as business_map_service
    from app.schemas.business_map import BusinessMapDraftUpdate

    objects = args.get("objects", []) if isinstance(args, dict) else []
    pre_analysis = args.get("pre_analysis") if isinstance(args, dict) else None
    draft_data = dict(args)
    draft_data["ready_for_adoption"] = True
    draft_data.setdefault("workflow_status", "ready")
    async with async_session() as db:
        user = await db.get(User, ctx.user_id)
        if user is None:
            return _error_result("当前用户不存在，无法保存草稿")
        draft = await business_map_service.upsert_draft(
            db,
            ctx.project_id,
            BusinessMapDraftUpdate(
                draft_data=draft_data,
                source_session_id=ctx.source_session_id,
            ),
            user,
        )

    # M3.4.3：revision>1 即增量更新，携带上一版供前端 diff（§7.2 Chat 调整循环）
    is_update = (draft.revision or 1) > 1
    await ctx.publish(
        _draft_pending_event(
            "business_map_draft",
            "业务地图草稿",
            draft.id,
            ctx.project_id,
            preview=_business_map_preview(draft_data),
            previous=draft.previous_data if is_update else None,
            revision=draft.revision,
            is_update=is_update,
        )
    )
    verb = "已更新业务地图草稿" if is_update else "已保存业务地图草稿"
    pre_analysis_hint = "，包含前置分析" if isinstance(pre_analysis, dict) else ""
    return _ok_result(
        f"{verb}（第 {draft.revision} 版，{len(objects)} 个节点{pre_analysis_hint}，草稿ID #{draft.id}）。"
        "草稿已进入「待采纳」区，等待用户采纳后才写入正式地图。"
        "若用户要求调整，请基于用户指令重新调用本工具覆盖更新草稿（上一版已自动存档供对比）。"
    )


async def handle_save_hypothesis_map_stage(ctx: DraftToolContext, args: dict) -> dict:
    """保存假设地图已确认阶段 → 累计到 BusinessMapDraft.draft_data，不推送待采纳卡片。"""
    err = validate_tool_input(SAVE_HYPOTHESIS_MAP_STAGE_SCHEMA, args)
    if err:
        return _error_result(f"save_hypothesis_map_stage 入参校验失败：{err}")

    from app.db.session import async_session
    from app.models import User
    from app.modules.business_map import service as business_map_service
    from app.schemas.business_map import BusinessMapDraftUpdate

    stage = str(args.get("stage"))
    async with async_session() as db:
        user = await db.get(User, ctx.user_id)
        if user is None:
            return _error_result("当前用户不存在，无法保存阶段内容")
        current = await business_map_service.get_active_draft(db, ctx.project_id)
        try:
            merged = _merge_hypothesis_stage_data(
                current.draft_data if current is not None else None,
                args,
            )
        except ValueError as exc:
            return _error_result(str(exc))
        draft = await business_map_service.upsert_draft(
            db,
            ctx.project_id,
            BusinessMapDraftUpdate(
                draft_data=merged,
                source_session_id=ctx.source_session_id,
            ),
            user,
        )

    objects = merged.get("objects") if isinstance(merged.get("objects"), list) else []
    return _ok_result(
        f"已固化假设地图 {stage} 阶段到中间草稿（第 {draft.revision} 版，累计 {len(objects)} 个节点）。"
        "该中间草稿尚未进入待采纳区；请继续下一阶段。"
    )


async def handle_finalize_hypothesis_map_draft(
    ctx: DraftToolContext, args: dict
) -> dict:
    """把已累计的假设地图中间草稿标记为可采纳，并推送最终待采纳卡片。"""
    err = validate_tool_input(FINALIZE_HYPOTHESIS_MAP_DRAFT_SCHEMA, args)
    if err:
        return _error_result(f"finalize_hypothesis_map_draft 入参校验失败：{err}")

    from app.db.session import async_session
    from app.models import User
    from app.modules.business_map import service as business_map_service
    from app.schemas.business_map import BusinessMapDraftUpdate

    async with async_session() as db:
        user = await db.get(User, ctx.user_id)
        if user is None:
            return _error_result("当前用户不存在，无法提交最终草稿")
        current = await business_map_service.get_active_draft(db, ctx.project_id)
        if current is None:
            return _error_result("尚未保存任何假设地图阶段内容，无法提交最终草稿")
        draft_data = dict(current.draft_data) if isinstance(current.draft_data, dict) else {}
        validation_error = _validate_hypothesis_map_ready(draft_data)
        if validation_error:
            return _error_result(f"假设地图最终草稿校验失败：{validation_error}")
        draft_data["ready_for_adoption"] = True
        draft_data["workflow_status"] = "ready"
        draft = await business_map_service.upsert_draft(
            db,
            ctx.project_id,
            BusinessMapDraftUpdate(
                draft_data=draft_data,
                source_session_id=ctx.source_session_id,
            ),
            user,
        )

    is_update = (draft.revision or 1) > 1
    await ctx.publish(
        _draft_pending_event(
            "business_map_draft",
            "业务地图草稿",
            draft.id,
            ctx.project_id,
            preview=_business_map_preview(draft_data),
            previous=draft.previous_data if is_update else None,
            revision=draft.revision,
            is_update=is_update,
        )
    )
    objects = draft_data.get("objects") if isinstance(draft_data.get("objects"), list) else []
    return _ok_result(
        f"已提交假设地图最终草稿（第 {draft.revision} 版，{len(objects)} 个节点）。"
        "草稿已进入「待采纳」区，用户采纳后才写入正式业务地图。"
    )


async def handle_save_stakeholder_card_draft(
    ctx: DraftToolContext, args: dict
) -> dict:
    """保存/更新角色卡草稿 → StakeholderCard（review_status=draft）。

    M3.4.3：入参可带 ``update_draft_id`` 指定要更新的草稿卡 id（§7.2 Chat 调整循环）。
    - 给 update_draft_id：校验该卡存在、属于本项目且仍为 draft 态 → 抓取旧字段快照 →
      覆盖更新（保持 draft 态）→ 事件携带 previous 供 diff。
    - 不给：新建草稿卡（原 M3.1 行为不变）。
    """
    err = validate_tool_input(SAVE_STAKEHOLDER_CARD_DRAFT_SCHEMA, args)
    if err:
        return _error_result(f"save_stakeholder_card_draft 入参校验失败：{err}")

    from app.db.session import async_session
    from app.models import StakeholderCard, User
    from app.modules.marketing_map import service as marketing_map_service
    from app.schemas.marketing_map import StakeholderCardCreate, StakeholderCardUpdate

    update_id = args.get("update_draft_id") if isinstance(args, dict) else None
    data = dict(args)
    data.pop("update_draft_id", None)  # 非实体字段，落库前移除

    async with async_session() as db:
        user = await db.get(User, ctx.user_id)
        if user is None:
            return _error_result("当前用户不存在，无法保存草稿")

        # M5.5.1：仅新建草稿时检测去重；更新既有草稿不重复检测
        has_dup = False
        if update_id:
            old = await db.get(StakeholderCard, update_id)
            if old is None or old.project_id != ctx.project_id:
                return _error_result("待更新的角色卡草稿不存在或不属于当前项目")
            if old.review_status != "draft":
                return _error_result(
                    f"该角色卡当前状态为 {old.review_status}，仅草稿态可更新"
                )
            previous = _snapshot_card(old)
            try:
                update_payload = StakeholderCardUpdate.model_validate(data)
            except Exception as exc:  # pydantic 校验失败（如 role_type 枚举）
                return _error_result(f"角色卡字段不合法：{exc}")
            card = await marketing_map_service.update_card(
                db, ctx.project_id, update_id, update_payload
            )
            if card is None:
                return _error_result("待更新的角色卡草稿不存在")
            is_update = True
        else:
            data["review_status"] = "draft"  # AI 产出先入草稿区，采纳后才 reviewed
            try:
                payload = StakeholderCardCreate.model_validate(data)
            except Exception as exc:  # pydantic 校验失败（如 role_type 枚举）
                return _error_result(f"角色卡字段不合法：{exc}")
            card = await marketing_map_service.create_card(
                db, ctx.project_id, payload, user,
                source_session_id=ctx.source_session_id,
            )
            # M5.5.1 角色去重：新建草稿后检测项目内既有卡是否疑似同人，
            # 命中则生成 person_disambiguation 候选（前端跟进渲染确认 UI）。
            # 检测失败不阻塞草稿主流程（去重是辅助提醒）。
            try:
                has_dup = await marketing_map_service.detect_and_create_disambiguation(
                    db, ctx.project_id, card.id
                )
            except Exception:
                has_dup = False
            previous = None
            is_update = False

    await ctx.publish(
        _draft_pending_event(
            "stakeholder_card_draft",
            "角色卡草稿",
            card.id,
            ctx.project_id,
            preview=_snapshot_card(card),
            previous=previous,
            is_update=is_update,
        )
    )
    verb = "已更新角色卡草稿" if is_update else "已保存角色卡草稿"
    dup_hint = (
        "（检测到疑似重复角色，已生成去重候选待用户在前端确认：新建或合并到既有卡）"
        if has_dup else ""
    )
    return _ok_result(
        f"{verb}「{card.name}」（草稿ID #{card.id}）。"
        "等待用户采纳后才进入正式营销地图。"
        "若用户要求调整，请带 update_draft_id=<本草稿ID> 重新调用本工具覆盖更新。"
        + dup_hint
    )


async def handle_save_visit_record_draft(
    ctx: DraftToolContext, args: dict
) -> dict:
    """保存/更新拜访记录草稿 → VisitRecord（review_status=draft）。

    M3.4.3：入参可带 ``update_draft_id`` 指定要更新的草稿记录 id（§7.2 Chat 调整循环）。
    - 给 update_draft_id：校验存在、属本项目、仍为 draft 态 → 抓取旧字段快照 →
      覆盖更新（保持 draft 态）→ 事件携带 previous 供 diff。
    - 不给：新建草稿记录（原 M3.1 行为不变）。
    """
    err = validate_tool_input(SAVE_VISIT_RECORD_DRAFT_SCHEMA, args)
    if err:
        return _error_result(f"save_visit_record_draft 入参校验失败：{err}")

    from app.db.session import async_session
    from app.models import User, VisitRecord
    from app.modules.visits import service as visits_service
    from app.schemas.visit import VisitRecordCreate, VisitRecordUpdate

    update_id = args.get("update_draft_id") if isinstance(args, dict) else None
    data = dict(args)
    data.pop("update_draft_id", None)  # 非实体字段，落库前移除

    async with async_session() as db:
        user = await db.get(User, ctx.user_id)
        if user is None:
            return _error_result("当前用户不存在，无法保存草稿")

        if update_id:
            old = await db.get(VisitRecord, update_id)
            if old is None or old.project_id != ctx.project_id:
                return _error_result("待更新的拜访记录草稿不存在或不属于当前项目")
            if old.review_status != "draft":
                return _error_result(
                    f"该拜访记录当前状态为 {old.review_status}，仅草稿态可更新"
                )
            previous = _snapshot_visit(old)
            try:
                update_payload = VisitRecordUpdate.model_validate(data)
            except Exception as exc:
                return _error_result(f"拜访记录字段不合法：{exc}")
            visit = await visits_service.update_visit(
                db, ctx.project_id, update_id, update_payload
            )
            if visit is None:
                return _error_result("待更新的拜访记录草稿不存在")
            is_update = True
        else:
            data["review_status"] = "draft"
            try:
                payload = VisitRecordCreate.model_validate(data)
            except Exception as exc:
                return _error_result(f"拜访记录字段不合法：{exc}")
            visit = await visits_service.create_visit(
                db, ctx.project_id, payload, user,
                source_session_id=ctx.source_session_id,
            )
            previous = None
            is_update = False

    await ctx.publish(
        _draft_pending_event(
            "visit_record_draft",
            "拜访记录草稿",
            visit.id,
            ctx.project_id,
            preview=_snapshot_visit(visit),
            previous=previous,
            is_update=is_update,
        )
    )
    verb = "已更新拜访记录草稿" if is_update else "已保存拜访记录草稿"
    return _ok_result(
        f"{verb}（草稿ID #{visit.id}）。等待用户采纳后才进入正式时间线。"
        "若用户要求调整，请带 update_draft_id=<本草稿ID> 重新调用本工具覆盖更新。"
    )


# ─── M3.1.1：草稿工具注册机制（SDK 进程内 MCP server） ───────────

# MCP server 名：Claude 侧工具名为 mcp__<server>__<tool>
DRAFT_SERVER_NAME = "consultant_drafts"

# 三个草稿工具的裸名（注册顺序固定，便于日志/调试）
DRAFT_TOOL_NAMES = (
    "save_hypothesis_map_stage",
    "finalize_hypothesis_map_draft",
    "save_stakeholder_card_draft",
    "save_visit_record_draft",
)


def build_draft_tool_server(ctx: DraftToolContext) -> dict:
    """构造草稿工具的进程内 MCP server（注入会话上下文到各 handler 闭包）。

    返回 ``McpSdkServerConfig``（``{type:"sdk", name, instance}``），
    由 ``runner.stream_chat`` 合并进 ``ClaudeAgentOptions.mcp_servers``，
    工具名经 ``draft_tool_allowed_names()`` 加入 ``allowed_tools``。
    """
    @tool(
        "save_hypothesis_map_stage",
        "保存假设地图已确认阶段到后端中间草稿。每个阶段用户确认后调用一次；"
        "本工具不会触发待采纳卡片，最终完成后再调用 finalize_hypothesis_map_draft。",
        SAVE_HYPOTHESIS_MAP_STAGE_SCHEMA,
    )
    async def _save_hypothesis_map_stage(args):  # noqa: ANN202
        return await handle_save_hypothesis_map_stage(ctx, args)

    @tool(
        "finalize_hypothesis_map_draft",
        "提交已累计的假设地图中间草稿，触发最终待采纳卡片。"
        "本工具不接受完整地图内容，只读取后端已保存的阶段草稿。",
        FINALIZE_HYPOTHESIS_MAP_DRAFT_SCHEMA,
    )
    async def _finalize_hypothesis_map_draft(args):  # noqa: ANN202
        return await handle_finalize_hypothesis_map_draft(ctx, args)

    @tool(
        "save_stakeholder_card_draft",
        "保存营销地图角色卡草稿（客观层/主观层/行为）。用户采纳后才进入正式营销地图。",
        SAVE_STAKEHOLDER_CARD_DRAFT_SCHEMA,
    )
    async def _save_stakeholder_card_draft(args):  # noqa: ANN202
        return await handle_save_stakeholder_card_draft(ctx, args)

    @tool(
        "save_visit_record_draft",
        "保存拜访记录草稿（摘要/参与人/Key Takeaways）。用户采纳后才进入正式时间线。",
        SAVE_VISIT_RECORD_DRAFT_SCHEMA,
    )
    async def _save_visit_record_draft(args):  # noqa: ANN202
        return await handle_save_visit_record_draft(ctx, args)

    return create_sdk_mcp_server(
        name=DRAFT_SERVER_NAME,
        tools=[
            _save_hypothesis_map_stage,
            _finalize_hypothesis_map_draft,
            _save_stakeholder_card_draft,
            _save_visit_record_draft,
        ],
    )


def draft_tool_allowed_names() -> list[str]:
    """草稿工具在 Claude 侧的允许调用名（mcp__<server>__<tool>），供 allowed_tools 使用。"""
    return [f"mcp__{DRAFT_SERVER_NAME}__{name}" for name in DRAFT_TOOL_NAMES]
