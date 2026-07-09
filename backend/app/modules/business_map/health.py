"""五维健康自动计算（M2.1.9）。

⚠️ 简单规则版本（开发计划风险 #5：M2.1.9 先实现简单规则，P5 打磨时对齐总纲）。
完整计算规则需对齐《企业数字健康分层地图 · 整体说明（V2.0）》总纲文档（本仓库未含），
当前以「关键字段完整度」启发式给出 1-5 分占位，待总纲落地后替换 _rule_score。

五维（固定 key，与 payload.fiveDimHealth 对齐）：
- L5_数字意识 / L4_数字神经 / L3_数字器官 / L2_数字血液 / L1_数字骨架
"""

from __future__ import annotations

from typing import Any

# 五维 key 及人类可读描述
FIVE_DIM_KEYS: dict[str, str] = {
    "L5_数字意识": "战略分解与IT投资匹配度",
    "L4_数字神经": "跨环节流程效率与协同",
    "L3_数字器官": "IT系统覆盖度与用户满意度",
    "L2_数字血液": "数据准确性、及时性、共享程度",
    "L1_数字骨架": "基础设施弹性、经济性、可持续性",
}

# 各层级参与完整度计算的关键字段（取自规格 §5.2 payload）
_LEVEL_KEY_FIELDS: dict[str, list[str]] = {
    "L1": ["coreActivities", "capabilityChain", "itSystems", "organization"],
    "L2": [
        "domainGoal",
        "valueStream",
        "subScenarios",
        "coreCapabilities",
        "supportITSystems",
        "keyOrganizations",
        "keyDataEntities",
        "disconnectionPoints",
    ],
    "L3": [
        "businessObjective",
        "businessProcess",
        "keyActivities",
        "capabilityUnits",
        "dataFlow",
        "positions",
        "supportSystems",
        "painPoints",
        "ontologyExtraction",
        "aiOpportunity",
    ],
    # L4 不计算五维健康（规格 L4 无 fiveDimHealth）
}


def _filled_count(payload: dict[str, Any] | None, keys: list[str]) -> int:
    """统计 payload 中非空的关键字段数。"""
    if not payload:
        return 0
    count = 0
    for k in keys:
        v = payload.get(k)
        if v in (None, "", [], {}):
            continue
        count += 1
    return count


def _rule_score(level: str, filled: int, total: int) -> int:
    """简单规则：按关键字段完整度映射 1-5 分。

    占位规则——filled 比例越高分越高。待总纲文档落地后替换为正式观测体系。
    """
    if total <= 0:
        return 3
    ratio = filled / total
    if ratio >= 0.9:
        return 5
    if ratio >= 0.7:
        return 4
    if ratio >= 0.4:
        return 3
    if ratio >= 0.2:
        return 2
    return 1


def compute_five_dim_health(
    payload: dict[str, Any] | None, level: str
) -> dict[str, dict[str, Any]]:
    """计算并返回五维健康评分字典。

    返回结构（与 payload.fiveDimHealth 一致）：
        { "L5_数字意识": {"score": 3, "desc": "..."}, ... }

    L4 节点不计算五维健康（返回空 dict）。
    """
    if level not in _LEVEL_KEY_FIELDS:
        return {}
    keys = _LEVEL_KEY_FIELDS[level]
    filled = _filled_count(payload, keys)
    score = _rule_score(level, filled, len(keys))
    return {dim: {"score": score, "desc": desc} for dim, desc in FIVE_DIM_KEYS.items()}


def merge_health_into_payload(
    payload: dict[str, Any] | None,
    health: dict[str, dict[str, Any]],
    source: str = "auto",
) -> dict[str, Any]:
    """把五维健康写入 payload.fiveDimHealth，并标记 _healthSource。

    返回新的 payload dict（不就地修改 None）。
    """
    out = dict(payload or {})
    out["fiveDimHealth"] = health
    out["_healthSource"] = source
    return out
