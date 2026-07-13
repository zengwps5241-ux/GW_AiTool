"""consultant-search Plugin 的 3 个 MCP 工具（M3.3.2）。

机制
----
用 ``claude_agent_sdk.create_sdk_mcp_server`` 把 ``search_web`` /
``search_company_registry`` / ``fetch_webpage`` 注册为**进程内 MCP 工具**
（与 M3.1 草稿工具同模式，决策 #29），Claude 在对话中调用
``mcp__consultant_search__<tool>`` 时由本模块 handler 执行：

- ``search_web``：联网搜索公开信息，结果归档到用户个人空间「公开信息/」
- ``search_company_registry``：查询企业工商信息（企查查/天眼查 API 待对接，
  未配置时返回明确提示，§4.3「后续对接」）
- ``fetch_webpage``：抓取指定 URL 转 Markdown

外部 HTTP 调用全部隔离在模块级 ``_http_*`` 函数中，便于单测 monkeypatch；
真实连通性由运营任务（CC-21）保证，不由自动化测试覆盖。会话级上下文
（workspace_root / project_id / user_id / source_session_id）由
``runner.stream_chat`` 经 ``SearchToolContext`` 闭包注入。
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

from app.core.config import _merged_env
from app.integrations.claude.tools import validate_tool_input

logger = logging.getLogger(__name__)


# ─── 工具输入 JSON Schema（单一真源：工具定义 + 入参校验） ────────

SEARCH_WEB_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
    },
    "required": ["query"],
    "additionalProperties": False,
}

COMPANY_REGISTRY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "company_name": {"type": "string", "minLength": 1},
    },
    "required": ["company_name"],
    "additionalProperties": False,
}

FETCH_WEBPAGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "format": "uri", "minLength": 1},
    },
    "required": ["url"],
    "additionalProperties": False,
}


@dataclass
class SearchToolContext:
    """单轮对话的搜索工具上下文（由 runner 注入，handler 闭包读取）。

    - workspace_root：搜索结果归档根目录（用户个人空间）；为 None 则不归档
    - project_id / user_id / source_session_id：归档路径归属与审计
    - project_name：项目名，用于按项目名归类归档路径（§6.2）
    """

    workspace_root: Path | None
    project_id: int | None
    user_id: int
    source_session_id: str | None
    project_name: str | None = None


# ─── 结果构造 ─────────────────────────────────────────────────


def _ok_result(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "is_error": False}


def _error_result(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


def _format_search_results(query: str, results: list[dict]) -> str:
    if not results:
        return f"搜索「{query}」未返回结果。"
    lines = [f"# 搜索结果：{query}", ""]
    for i, r in enumerate(results, 1):
        title = str(r.get("title") or "").strip() or "(无标题)"
        url = str(r.get("url") or r.get("link") or "").strip()
        snippet = str(r.get("snippet") or r.get("content") or "").strip()
        lines.append(f"## {i}. {title}")
        if url:
            lines.append(f"链接：{url}")
        if snippet:
            lines.append(snippet)
        lines.append("")
    return "\n".join(lines).strip()


def _format_registry(company_name: str, data: dict) -> str:
    lines = [f"# 工商信息：{company_name}", ""]
    for key, value in data.items():
        lines.append(f"- **{key}**：{value}")
    return "\n".join(lines)


# ─── 工作空间归档（个人空间「公开信息/」，同名去重） ─────────────


_SAFE_CHARS = re.compile(r"[^\w一-龥\-]+")


def _safe_slug(text: str, maxlen: int = 60) -> str:
    """把查询/URL 转为安全的文件名片段（保留中文/字母数字/连字符）。"""
    slug = _SAFE_CHARS.sub("-", text.strip()).strip("-")
    if not slug:
        slug = "search"
    return slug[:maxlen]


def _archive_public_info(
    ctx: SearchToolContext, filename: str, markdown: str
) -> tuple[Path | None, bool]:
    """把搜索结果归档到 workspace_root/{项目名}/资料/公开信息/<filename>。

    有项目名时按 §6.2 归档到项目子目录；无项目时退回根 公开信息/（向后兼容）。
    返回 ``(path, newly_written)``：workspace_root 为 None 时不归档；
    同名文件已存在则跳过写入（§7.8 同一关键词不重复归档的去重语义）。
    """
    if ctx.workspace_root is None:
        return None, False
    # §6.2：项目级会话 → {项目名}/资料/公开信息/；非项目 → 公开信息/
    if ctx.project_name:
        from app.core.utils import safe_filename

        pn = safe_filename(ctx.project_name)
        archive_dir = ctx.workspace_root / (pn or "file") / "资料" / "公开信息"
    else:
        archive_dir = ctx.workspace_root / "公开信息"
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("公开信息归档目录创建失败：%s", archive_dir, exc_info=True)
        return None, False
    path = archive_dir / filename
    if path.exists():
        return path, False  # 已归档，去重
    try:
        path.write_text(markdown, encoding="utf-8")
    except OSError:
        logger.warning("公开信息归档写入失败：%s", path, exc_info=True)
        return None, False
    return path, True


# ─── 外部 HTTP 调用 seam（单测 monkeypatch 目标） ────────────────


def _web_search_configured() -> bool:
    """是否配置了 web 搜索后端（WEB_SEARCH_API_URL + 凭据）。"""
    env = _merged_env()
    return bool(env.get("WEB_SEARCH_API_URL", "").strip()) and bool(
        (
            env.get("WEB_SEARCH_API_KEY", "").strip()
            or env.get("ZHIPU_WEB_SEARCH_API_KEY", "").strip()
        )
    )


def _company_registry_configured() -> bool:
    env = _merged_env()
    return bool(env.get("COMPANY_REGISTRY_API_KEY", "").strip())


async def _http_web_search(query: str, max_results: int) -> list[dict]:
    """默认 web 搜索实现：调用 WEB_SEARCH_API_URL（GET，query 参数）。

    约定响应为 ``{"results": [{title, url, snippet}, ...]}`` 或直接为列表。
    真实后端形态由运营在 .env 配置；本函数仅做容错解析。
    """
    env = _merged_env()
    base = env["WEB_SEARCH_API_URL"].strip()
    api_key = (
        env.get("WEB_SEARCH_API_KEY", "").strip()
        or env.get("ZHIPU_WEB_SEARCH_API_KEY", "").strip()
    )
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            base, params={"query": query, "count": max_results}, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
    if isinstance(data, dict):
        results = data.get("results") or data.get("data") or []
    else:
        results = data
    if not isinstance(results, list):
        return []
    out: list[dict] = []
    for item in results[:max_results]:
        if isinstance(item, dict):
            out.append(
                {
                    "title": item.get("title") or item.get("name") or "",
                    "url": item.get("url") or item.get("link") or "",
                    "snippet": item.get("snippet") or item.get("content") or "",
                }
            )
    return out


async def _http_company_registry(company_name: str) -> dict | None:
    """默认企业工商信息查询（COMPANY_REGISTRY_API_URL + KEY）。未配置返回 None。"""
    env = _merged_env()
    base = env.get("COMPANY_REGISTRY_API_URL", "").strip()
    api_key = env.get("COMPANY_REGISTRY_API_KEY", "").strip()
    if not base:
        return None
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            base, params={"name": company_name}, headers={"Authorization": f"Bearer {api_key}"}
        )
        resp.raise_for_status()
        data = resp.json()
    return data if isinstance(data, dict) else None


def _html_to_text(raw: str) -> str:
    """极简 HTML→文本：去 script/style，转 <br>/<p>，剥标签，反转义。"""
    raw = re.sub(r"<script\b.*?</script>", "", raw, flags=re.S | re.I)
    raw = re.sub(r"<style\b.*?</style>", "", raw, flags=re.S | re.I)
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    raw = re.sub(r"</p\s*>", "\n\n", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", "", raw)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


async def _http_fetch_webpage(url: str) -> str:
    """抓取 URL 并转文本：HTML 走 _html_to_text，其他类型原样返回（截断）。"""
    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; consultant-search/1.0)"},
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "").lower()
        body = resp.text
    if "html" in content_type:
        return _html_to_text(body)
    return body


# ─── 工具 handler ─────────────────────────────────────────────


async def handle_search_web(ctx: SearchToolContext, args: dict) -> dict:
    """search_web：联网搜索公开信息，归档到个人空间「公开信息/」。"""
    err = validate_tool_input(SEARCH_WEB_SCHEMA, args)
    if err:
        return _error_result(f"search_web 入参校验失败：{err}")
    query = str(args["query"]).strip()
    max_results = int(args.get("max_results") or 5)

    if not _web_search_configured():
        return _ok_result(
            f"web 搜索后端未配置（需在 .env 设置 WEB_SEARCH_API_URL 与凭据）。"
            f"本次未执行联网搜索，请基于已有资料回答「{query}」，或建议用户配置搜索源。"
        )
    try:
        results = await _http_web_search(query, max_results)
    except Exception as exc:  # noqa: BLE001 — 外部调用，笼统捕获并回写 Claude
        logger.warning("search_web 调用失败", exc_info=True)
        return _error_result(f"search_web 调用失败：{exc}")
    markdown = _format_search_results(query, results)
    path, newly = _archive_public_info(ctx, f"{_safe_slug(query)}.md", markdown)
    note = f"\n\n（已归档到个人空间：{path.relative_to(ctx.workspace_root)}）" if newly and path else ""
    return _ok_result(markdown + note)


async def handle_search_company_registry(ctx: SearchToolContext, args: dict) -> dict:
    """search_company_registry：查询企业工商信息（企查查/天眼查，§4.3 后续对接）。"""
    err = validate_tool_input(COMPANY_REGISTRY_SCHEMA, args)
    if err:
        return _error_result(f"search_company_registry 入参校验失败：{err}")
    name = str(args["company_name"]).strip()

    if not _company_registry_configured():
        return _ok_result(
            f"企业工商信息接口（企查查/天眼查）尚未对接（COMPANY_REGISTRY_API_KEY 未配置），"
            f"无法查询「{name}」的工商登记信息。"
        )
    try:
        data = await _http_company_registry(name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_company_registry 调用失败", exc_info=True)
        return _error_result(f"search_company_registry 调用失败：{exc}")
    if not data:
        return _ok_result(f"未查询到「{name}」的工商信息。")
    markdown = _format_registry(name, data)
    path, newly = _archive_public_info(ctx, f"{_safe_slug(name)}-工商.md", markdown)
    note = f"\n\n（已归档：{path.relative_to(ctx.workspace_root)}）" if newly and path else ""
    return _ok_result(markdown + note)


async def handle_fetch_webpage(ctx: SearchToolContext, args: dict) -> dict:
    """fetch_webpage：抓取指定 URL 转 Markdown，归档到个人空间。"""
    err = validate_tool_input(FETCH_WEBPAGE_SCHEMA, args)
    if err:
        return _error_result(f"fetch_webpage 入参校验失败：{err}")
    url = str(args["url"]).strip()
    if not url.lower().startswith(("http://", "https://")):
        return _error_result("fetch_webpage 仅支持 http/https URL")

    try:
        text = await _http_fetch_webpage(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_webpage 抓取失败", exc_info=True)
        return _error_result(f"fetch_webpage 抓取失败：{exc}")
    # 截断超长内容，避免单条工具结果撑爆上下文
    truncated = text[:8000]
    markdown = f"# 抓取：{url}\n\n{truncated}"
    path, newly = _archive_public_info(ctx, f"{_safe_slug(url)}.md", markdown)
    note = f"\n\n（已归档：{path.relative_to(ctx.workspace_root)}）" if newly and path else ""
    return _ok_result(markdown + note)


# ─── MCP server 注册 ──────────────────────────────────────────


# MCP server 名：Claude 侧工具名为 mcp__<server>__<tool>
SEARCH_SERVER_NAME = "consultant_search"
SEARCH_TOOL_NAMES = ("search_web", "search_company_registry", "fetch_webpage")


def build_search_tool_server(ctx: SearchToolContext) -> dict:
    """构造搜索工具的进程内 MCP server（注入 SearchToolContext 到各 handler 闭包）。

    返回 ``McpSdkServerConfig``，由 ``runner.stream_chat`` 合并进
    ``ClaudeAgentOptions.mcp_servers``，工具名经 ``search_tool_allowed_names()``
    加入 ``allowed_tools``。
    """

    @tool(
        "search_web",
        "搜索公开信息（联网）。返回网页片段列表并归档到个人空间「公开信息/」。"
        "WF07 生成假设地图时用于补充目标公司的公开情报。",
        SEARCH_WEB_SCHEMA,
    )
    async def _search_web(args):  # noqa: ANN202
        return await handle_search_web(ctx, args)

    @tool(
        "search_company_registry",
        "查询企业工商登记信息（企查查/天眼查）。未对接时返回提示。",
        COMPANY_REGISTRY_SCHEMA,
    )
    async def _search_company_registry(args):  # noqa: ANN202
        return await handle_search_company_registry(ctx, args)

    @tool(
        "fetch_webpage",
        "抓取指定 URL 页面并转为 Markdown 文本，归档到个人空间。",
        FETCH_WEBPAGE_SCHEMA,
    )
    async def _fetch_webpage(args):  # noqa: ANN202
        return await handle_fetch_webpage(ctx, args)

    return create_sdk_mcp_server(
        name=SEARCH_SERVER_NAME,
        tools=[_search_web, _search_company_registry, _fetch_webpage],
    )


def search_tool_allowed_names() -> list[str]:
    """搜索工具在 Claude 侧的允许调用名（mcp__<server>__<tool>）。"""
    return [f"mcp__{SEARCH_SERVER_NAME}__{name}" for name in SEARCH_TOOL_NAMES]


def search_plugin_active(agent) -> bool:  # noqa: ANN001 — 容忍 ORM/stub
    """该 Agent 是否绑定了 consultant-search（决定是否挂载搜索工具）。"""
    plugins = getattr(agent, "plugins", None) or ""
    return "consultant-search" in [
        p.strip() for p in plugins.split(",") if p.strip()
    ]
