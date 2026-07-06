"""Office 预览:签名 URL 与 kkFileView 代理辅助函数。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import HTTPException, status
from fastapi.responses import Response, StreamingResponse

_OFFICE_SUFFIXES = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".pdf", ".csv"}
_KKFILEVIEW_TIMEOUT_SECONDS = 120.0
_IMAGE_PREVIEW_THRESHOLD_BYTES = 20 * 1024 * 1024
_FORWARDED_REQUEST_HEADERS = {"if-none-match", "if-modified-since"}
_FORWARDED_RESPONSE_HEADERS = {
    "cache-control",
    "etag",
    "expires",
    "last-modified",
    "vary",
}


def is_office_document(path: str | Path) -> bool:
    """判断文件是否应交给 kkFileView 预览。"""
    return Path(path).suffix.lower() in _OFFICE_SUFFIXES


def kkfileview_preview_type_for_size(size: int) -> str:
    """按文件大小选择 kkFileView 预览模式，大文件改用图片模式降低前端压力。"""
    return "image" if size >= _IMAGE_PREVIEW_THRESHOLD_BYTES else "pdf"


def _sign(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _encode_token(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_token(token: str) -> str:
    padding = "=" * (-len(token) % 4)
    try:
        return base64.urlsafe_b64decode(f"{token}{padding}").decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="签名无效") from exc


def create_file_token(
    username: str,
    rel_path: str,
    *,
    secret: str,
    ttl_seconds: int = 300,
    nonce: str | None = None,
) -> str:
    expires = int(time.time()) + ttl_seconds
    nonce = nonce or secrets.token_urlsafe(12)
    payload = json.dumps({"u": username, "p": rel_path, "e": expires, "n": nonce}, separators=(",", ":"))
    signature = _sign(payload, secret)
    return _encode_token(f"{payload}.{signature}")


def verify_file_token(token: str, *, secret: str) -> dict[str, str | int]:
    raw = _decode_token(token)
    if "." not in raw:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="签名无效")
    payload_raw, signature = raw.rsplit(".", 1)
    expected = _sign(payload_raw, secret)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="签名无效")
    try:
        data = json.loads(payload_raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="签名无效") from exc
    for key in ("u", "p", "e", "n"):
        if key not in data:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="签名无效")
    try:
        expires = int(data["e"])
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="签名无效") from exc
    if expires < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="签名已过期")
    return {"username": data["u"], "path": data["p"], "expires": expires, "nonce": data["n"]}


def build_internal_file_url(base_url: str, token: str, filename: str) -> str:
    root = base_url.rstrip("/")
    query = urlencode({"token": token, "fullfilename": filename})
    return f"{root}/api/workspace/internal-preview-file?{query}"


def build_kkfileview_online_preview_url(base_url: str, source_url: str, office_preview_type: str = "pdf") -> str:
    root = base_url.rstrip("/")
    encoded_source = base64.b64encode(source_url.encode("utf-8")).decode("ascii")
    query = urlencode({
        "url": encoded_source,
        "officePreviewType": office_preview_type,
    })
    return f"{root}/onlinePreview?{query}"


def create_proxy_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=_KKFILEVIEW_TIMEOUT_SECONDS, follow_redirects=True)


def rewrite_kkfileview_html(html: str, proxy_prefix: str, kk_base_url: str) -> str:
    root = kk_base_url.rstrip("/")
    proxy_root = proxy_prefix.rstrip("/")
    context_path = urlparse(root).path.rstrip("/")

    def rewrite_attr(match: re.Match[str]) -> str:
        prefix, value, quote_char = match.groups()
        lowered = value.lower()
        if (
            lowered.startswith(("http://", "https://", "//", "data:", "javascript:"))
            or value.startswith("#")
        ):
            return match.group(0)
        if value == proxy_root or value.startswith(f"{proxy_root}/"):
            return match.group(0)
        if context_path and value == context_path:
            next_value = proxy_root
        elif context_path and value.startswith(f"{context_path}/"):
            next_value = f"{proxy_root}{value[len(context_path):]}"
        elif value.startswith("/"):
            next_value = f"{proxy_root}{value}"
        else:
            next_value = f"{proxy_root}/{value}"
        return f"{prefix}{next_value}{quote_char}"

    html = html.replace(root, proxy_root)
    return re.sub(r'((?:src|href)=["\'])([^"\']+)(["\'])', rewrite_attr, html)


async def fetch_kkfileview_response(url: str) -> httpx.Response:
    async with create_proxy_client() as client:
        return await client.get(url)


async def stream_kkfileview_path(
    base_url: str,
    rel_path: str,
    query: str,
    headers: Mapping[str, str] | None = None,
) -> StreamingResponse | Response:
    safe_path = rel_path.lstrip("/")
    if "://" in safe_path or safe_path.startswith("//"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理路径无效")
    url = f"{base_url.rstrip('/')}/{safe_path}"
    if query:
        url = f"{url}?{query}"
    forwarded_headers = {
        key: value
        for key, value in (headers or {}).items()
        if key.lower() in _FORWARDED_REQUEST_HEADERS
    }
    async with create_proxy_client() as client:
        response = await client.get(url, headers=forwarded_headers)
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Office 预览服务不可用")
    content_type = response.headers.get("content-type", "application/octet-stream")
    response_headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() in _FORWARDED_RESPONSE_HEADERS
    }
    # 资源缓存依赖 kkFileView 原始响应头；代理层只筛选安全缓存头透传。
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=content_type,
        headers=response_headers,
    )
