"""WF01 意图路由（consultant-router Plugin 的 app 层执行模块，M3.3.1）。

路由管线（§4.3 Plugin1 / 开发计划 M3.3.1）::

    路径 A（零层）：用户点击 WF chip / 发送 /skill 斜杠命令 / 拖入文件
        → 跳过意图识别，直接路由到对应 Skill（confidence_source="chip"）
    路径 B（自然语言输入）：
        → ① LLM 意图分类（置信度 ≥ 0.7 → 直接路由，confidence_source="llm"）
        → ② 关键词兜底（命中唯一类 → 路由，confidence_source="keyword"）
        → ③ 多类命中 / 都不命中 → Chat Mode（confidence_source="chat_fallback"，
              needs_confirmation=True 标记供前端未来弹窗确认）

每次自然语言输入都会落一条 ``IntentRoutingLog``（§4.3 数据记录）。路由到
Skill 时把原提示改写为 ``/<skill-command> <原提示>``，复用 M3.4.1 既有的
斜杠命令触发机制（scan_agent_commands 已把 skills 暴露为 /command）。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import _merged_env
from app.integrations.openai import generate_chat_completion

logger = logging.getLogger(__name__)

# LLM 分类置信度阈值（≥ 此值才直接路由，否则降级到关键词兜底）
LLM_CONFIDENCE_THRESHOLD = 0.7


# ─── 7 类意图标签（§4.3） ──────────────────────────────────────────


@dataclass(frozen=True)
class IntentSpec:
    """单个意图的静态描述：标签 / 路由目标 Skill / 关键词 / 说明。"""

    label: str
    skill: str | None  # 路由目标 Skill 命令名；chat/file_upload 为 None
    keywords: tuple[str, ...]
    description: str


INTENTS: dict[str, IntentSpec] = {
    "hypothesis_map": IntentSpec(
        "hypothesis_map",
        "consultant-hypothesis-map",
        ("假设地图", "业务地图", "L1", "L2", "L3", "L4", "业务拆解"),
        "生成/更新假设业务地图（WF07）",
    ),
    "current_map_verify": IntentSpec(
        "current_map_verify",
        "consultant-verify",
        ("验证假设", "是否成立", "现状流程", "推翻假设", "假设验证"),
        "验证假设、更新现状地图（WF10）",
    ),
    "stakeholder_card": IntentSpec(
        "stakeholder_card",
        "consultant-stakeholder",
        ("角色卡", "营销地图", "决策人", "组织架构", "决策链"),
        "生成营销地图角色卡（WF12）",
    ),
    "interview_summary": IntentSpec(
        "interview_summary",
        "consultant-interview",
        ("会议纪要", "访谈整理", "拜访记录", "拜访纪要", "访谈纪要"),
        "整理拜访/访谈纪要（WF09）",
    ),
    "visit_plan": IntentSpec(
        "visit_plan",
        "consultant-visit-plan",
        ("拜访方案", "访谈提纲", "拜访准备", "拜访前方案"),
        "生成拜访前方案（WF06）",
    ),
    # file_upload 为行为触发（上传/拖入文件），不参与自然语言路由
    "file_upload": IntentSpec(
        "file_upload",
        "consultant-upload",
        (),
        "资料上传与归档（WF02，行为触发）",
    ),
    "chat": IntentSpec(
        "chat",
        None,
        (),
        "通用问答/解释/优化/总结（Chat Mode）",
    ),
}

# 可经自然语言（LLM/关键词）路由到的意图（5 个产出型 Skill + chat 兜底）。
# file_upload 仅行为触发，不在此列。
NL_ROUTABLE_LABELS = frozenset(
    {
        "hypothesis_map",
        "current_map_verify",
        "stakeholder_card",
        "interview_summary",
        "visit_plan",
        "chat",
    }
)

# 有关键词的意图（用于关键词兜底扫描）
KEYWORD_INTENTS = tuple(
    label for label, spec in INTENTS.items() if spec.keywords
)

# Skill 命令名 → 意图标签（用于识别路径 A 的斜杠命令）
_SKILL_TO_LABEL: dict[str, str] = {
    spec.skill: label for label, spec in INTENTS.items() if spec.skill
}


# ─── 路由决策结构 ────────────────────────────────────────────────


@dataclass
class RoutingDecision:
    """一次路由的完整决策结果（同时作为 IntentRoutingLog 的数据来源）。"""

    intent_label: str
    route_target: str | None
    confidence_source: str  # chip / llm / keyword / chat_fallback
    final_prompt: str
    llm_label: str | None = None
    llm_confidence: float | None = None
    keyword_hits: list[str] = field(default_factory=list)
    llm_raw: dict[str, Any] | None = None
    needs_confirmation: bool = False


# ─── 纯逻辑：斜杠命令解析 / 关键词兜底 ──────────────────────────


def parse_slash_command(prompt: str) -> tuple[str | None, str]:
    """识别路径 A 的斜杠命令。

    返回 ``(command, remainder)``：command 为去掉前导 ``/`` 的命令名（如
    ``consultant-hypothesis-map``），remainder 为命令后的剩余文本；非斜杠
    命令则 command=None、remainder=原 prompt。
    """
    s = prompt.lstrip()
    if not s.startswith("/"):
        return None, prompt
    first = s.split(None, 1)[0]
    command = first[1:]
    remainder = s[len(first):].lstrip()
    # 仅形如 [A-Za-z0-9_-]+ 的 token 才视为命令，避免误把含 / 的普通文本当命令
    if not command or not re.fullmatch(r"[A-Za-z0-9_\-]+", command):
        return None, prompt
    return command, remainder


def keyword_fallback(text: str) -> list[str]:
    """关键词兜底：返回命中的意图标签列表（去重，保持 INTENTS 顺序）。

    “命中唯一类 → 路由”：调用方据返回长度判定（len==1 可路由，>1 歧义，0 落 chat）。
    """
    if not text:
        return []
    lowered = text.lower()
    hits: list[str] = []
    for label in KEYWORD_INTENTS:
        spec = INTENTS[label]
        if any(kw.lower() in lowered for kw in spec.keywords):
            hits.append(label)
    return hits


# ─── LLM 意图分类 ───────────────────────────────────────────────


def _plugins_seed_dir() -> Path:
    """返回包内 plugins_seed 根目录（app/plugins_seed）。"""
    return Path(__file__).resolve().parents[2] / "plugins_seed"


def load_intent_classifier_prompt() -> str:
    """加载意图分类 System Prompt（单一真源 = 版本化模板资产）。"""
    path = _plugins_seed_dir() / "consultant-router" / "prompts" / "intent_classifier.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        # 资产缺失时退化为内联最小 Prompt，保证链路不中断
        return (
            "你是咨询顾问意图分类器。把用户消息分到唯一标签："
            "hypothesis_map / current_map_verify / stakeholder_card / "
            "interview_summary / visit_plan / chat。"
            "只输出 JSON：{\"label\": ..., \"confidence\": 0~1, \"reason\": ...}。"
        )


def _parse_llm_json(raw: str | None) -> dict[str, Any] | None:
    """从 LLM 文本回复中容错解析 {label, confidence, reason}。"""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    data: Any = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    label = str(data.get("label", "")).strip()
    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return {
        "label": label,
        "confidence": confidence,
        "reason": str(data.get("reason", "")),
    }


async def classify_intent_llm(text: str) -> dict[str, Any] | None:
    """调用 LLM 对自然语言做意图分类，返回解析后的 {label, confidence, reason}。

    未配置 DeepSeek 凭据 / 调用失败 / 解析失败时返回 None，由调用方降级到
    关键词兜底（与 _make_semantic_title 同一 env 模式）。
    """
    if not text.strip():
        return None
    env = _merged_env()
    api_key = env.get("ANTHROPIC_PROVIDER_DEEPSEEK_AUTH_TOKEN", "").strip()
    if not api_key:
        return None
    base_url = (
        env.get("SESSION_TITLE_OPENAI_BASE_URL", "https://api.deepseek.com").strip()
        or "https://api.deepseek.com"
    )
    model = (
        env.get("INTENT_ROUTER_OPENAI_MODEL")
        or env.get("SESSION_TITLE_OPENAI_MODEL", "deepseek-v4-flash")
    ).strip() or "deepseek-v4-flash"
    try:
        raw = await generate_chat_completion(
            api_key=api_key,
            base_url=base_url,
            model=model,
            system_prompt=load_intent_classifier_prompt(),
            user_prompt=text,
            timeout=8.0,
        )
    except Exception:
        logger.warning("意图分类 LLM 调用失败，降级关键词兜底", exc_info=True)
        return None
    return _parse_llm_json(raw)


# ─── 路由编排 ───────────────────────────────────────────────────


async def route_user_prompt(*, agent, prompt: str) -> RoutingDecision:
    """对一条用户输入执行完整三级路由，返回 RoutingDecision。

    - ``agent`` 仅用于判定是否启用（启用判定由调用方 streaming 负责），
      本函数不读 agent，保持纯函数便于单测。
    - 路径 A（斜杠命令命中已知 Skill）→ chip 直达。
    - 路径 B（自然语言）→ LLM 分类 → 关键词兜底 → chat 兜底。
    """
    command, remainder = parse_slash_command(prompt)
    analysis_text = remainder if command else prompt
    slash_intent = _SKILL_TO_LABEL.get(command) if command else None

    llm_result: dict[str, Any] | None = None
    if slash_intent is None:
        llm_result = await classify_intent_llm(analysis_text)

    keyword_hits = keyword_fallback(analysis_text)
    llm_label = llm_result.get("label") if llm_result else None
    llm_conf = llm_result.get("confidence") if llm_result else None

    # ① 路径 A：斜杠/chip 直达
    if slash_intent is not None:
        return RoutingDecision(
            intent_label=slash_intent,
            route_target=INTENTS[slash_intent].skill,
            confidence_source="chip",
            final_prompt=prompt,  # 原样（已含 /command + hint）
            llm_label=None,
            llm_confidence=None,
            keyword_hits=keyword_hits,
            llm_raw=None,
            needs_confirmation=False,
        )

    # ② LLM 高置信直接路由（含 confident chat）
    if (
        llm_result
        and llm_conf is not None
        and llm_conf >= LLM_CONFIDENCE_THRESHOLD
        and llm_label in NL_ROUTABLE_LABELS
    ):
        target = INTENTS[llm_label].skill  # chat → None
        return RoutingDecision(
            intent_label=llm_label,
            route_target=target,
            confidence_source="llm",
            final_prompt=f"/{target} {prompt}".strip() if target else prompt,
            llm_label=llm_label,
            llm_confidence=llm_conf,
            keyword_hits=keyword_hits,
            llm_raw=llm_result,
            needs_confirmation=False,
        )

    # ③ 关键词兜底：命中唯一类 → 路由
    if len(keyword_hits) == 1:
        label = keyword_hits[0]
        target = INTENTS[label].skill
        return RoutingDecision(
            intent_label=label,
            route_target=target,
            confidence_source="keyword",
            final_prompt=f"/{target} {prompt}",
            llm_label=llm_label,
            llm_confidence=llm_conf,
            keyword_hits=keyword_hits,
            llm_raw=llm_result,
            needs_confirmation=False,
        )

    # ④ Chat 兜底（多类命中标记需确认，供前端未来弹窗）
    return RoutingDecision(
        intent_label="chat",
        route_target=None,
        confidence_source="chat_fallback",
        final_prompt=prompt,
        llm_label=llm_label,
        llm_confidence=llm_conf,
        keyword_hits=keyword_hits,
        llm_raw=llm_result,
        needs_confirmation=len(keyword_hits) > 1,
    )


# ─── 落库 ───────────────────────────────────────────────────────


async def log_routing(
    db,
    *,
    session_id: str | None,
    project_id: int | None,
    user_id: int,
    prompt: str,
    decision: RoutingDecision,
):
    """把路由决策写入 IntentRoutingLog（每次自然语言输入必入一条）。"""
    from app.models import IntentRoutingLog

    entry = IntentRoutingLog(
        session_id=session_id,
        project_id=project_id,
        user_id=user_id,
        prompt=prompt,
        intent_label=decision.intent_label,
        route_target=decision.route_target,
        confidence_source=decision.confidence_source,
        llm_label=decision.llm_label,
        llm_confidence=decision.llm_confidence,
        keyword_hits=decision.keyword_hits or None,
        llm_raw=decision.llm_raw or None,
        final_prompt=decision.final_prompt,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


def router_plugin_active(agent) -> bool:  # noqa: ANN001 — 容忍 ORM/stub
    """该 Agent 是否绑定了 consultant-router（决定路由是否启用）。"""
    plugins = (getattr(agent, "plugins", None) or "")
    return "consultant-router" in [p.strip() for p in plugins.split(",") if p.strip()]
