"""consultant-defense Plugin 的两道防线（M3.3.3）。

- **防线 1（道层 System Prompt 注入）**：在每个对话 Session 初始化时把
  ``dao_layer.md`` 全文注入 System Prompt（不可被 RAG 覆盖）。由
  ``runner.stream_chat`` 在组装 system_prompt.append 时前置拼接。
- **防线 2（PostOutputFilter 确定性指纹匹配）**：对 LLM 产出的
  ``assistant_text`` 做 100% 确定性指纹匹配，过滤 ``never_visible`` 内容
  （不依赖 LLM 判断）。由 ``streaming.on_message`` 在写入 run_state / SSE
  前应用。思维链（assistant_thinking）不过滤（§8.2）。

资产单一真源 = 版本化模板 ``app/plugins_seed/consultant-defense/rules/``
（claude_data/ 被 gitignore）。绑定判定：Agent.plugins 含 consultant-defense。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# 指纹命中后的统一替换文本（确定性、对用户可见、不泄露原内容）
_REDACTION = "[已过滤]"


def _plugins_seed_dir() -> Path:
    """返回包内 plugins_seed 根目录（app/plugins_seed）。

    defense.py 位于 app/integrations/claude/，parents[2] = app。
    """
    return Path(__file__).resolve().parents[2] / "plugins_seed"


# ─── 防线 1：道层 System Prompt ───────────────────────────────


def load_dao_layer_prompt() -> str:
    """加载道层 System Prompt 全文（rules/dao_layer.md）。

    资产缺失时返回空串（不阻断对话，仅缺失道层注入）。
    """
    path = _plugins_seed_dir() / "consultant-defense" / "rules" / "dao_layer.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("dao_layer.md 资产缺失，防线1 未注入", exc_info=True)
        return ""


# ─── 防线 2：PostOutputFilter 指纹匹配 ─────────────────────────


def load_never_visible_rules() -> list[dict]:
    """加载 never_visible 指纹规则（rules/never_visible.json）。

    每条形如 ``{"id": ..., "type": "substring"|"regex", "pattern": ..., "reason": ...}``。
    资产缺失或非法时返回空列表（不过滤）。
    """
    path = _plugins_seed_dir() / "consultant-defense" / "rules" / "never_visible.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("never_visible.json 资产缺失/非法，防线2 规则为空", exc_info=True)
        return []
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict) and r.get("pattern")]


def _compile_rules(rules: list[dict]) -> list[tuple[str, re.Pattern | str, str]]:
    """把规则预编译为 (id, compiled, type) 列表。

    substring → 保留原字符串（用 str.replace）；regex → 编译为 Pattern，
    非法正则跳过并告警。
    """
    compiled: list[tuple[str, re.Pattern | str, str]] = []
    for r in rules:
        rid = str(r.get("id") or "")
        rtype = str(r.get("type") or "substring").lower()
        pattern = r.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            continue
        if rtype == "regex":
            try:
                compiled.append((rid, re.compile(pattern), "regex"))
            except re.error:
                logger.warning("never_visible 正则非法，已跳过：%s", pattern)
        else:
            compiled.append((rid, pattern, "substring"))
    return compiled


def apply_output_filter(text: str, rules: list[dict] | None = None) -> str:
    """对文本应用确定性指纹过滤，返回过滤后文本。

    - ``rules`` 为 None 时加载默认资产规则。
    - 命中片段替换为 ``[已过滤]``；不依赖任何 LLM 判断。
    - 无命中 / 空规则 → 原样返回。
    """
    if not text:
        return text
    if rules is None:
        rules = load_never_visible_rules()
    if not rules:
        return text
    out = text
    for _rid, pat, rtype in _compile_rules(rules):
        if rtype == "regex":
            out = pat.sub(_REDACTION, out)  # type: ignore[union-attr]
        else:
            out = out.replace(pat, _REDACTION)  # type: ignore[arg-type]
    return out


# ─── 绑定判定 ─────────────────────────────────────────────────


def defense_plugin_active(agent) -> bool:  # noqa: ANN001 — 容忍 ORM/stub
    """该 Agent 是否绑定了 consultant-defense（决定两道防线是否启用）。"""
    plugins = getattr(agent, "plugins", None) or ""
    return "consultant-defense" in [
        p.strip() for p in plugins.split(",") if p.strip()
    ]
