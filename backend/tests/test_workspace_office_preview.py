import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException


def test_office_suffix_detection():
    from app.modules.workspace.office_preview import is_office_document

    assert is_office_document(Path("a.docx"))
    assert is_office_document(Path("a.ppt"))
    assert is_office_document(Path("a.xlsx"))
    assert is_office_document(Path("a.pdf"))
    assert is_office_document(Path("a.csv"))
    assert not is_office_document(Path("a.md"))


def test_kkfileview_proxy_timeout_is_two_minutes(monkeypatch):
    """首次转码较慢，kkFileView 预览代理应等待 2 分钟。"""
    from app.modules.workspace.office_preview import create_proxy_client

    for key in ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "http_proxy", "https_proxy"):
        monkeypatch.delenv(key, raising=False)
    client = create_proxy_client()

    try:
        assert client.timeout.connect == 120.0
        assert client.timeout.read == 120.0
        assert client.timeout.write == 120.0
        assert client.timeout.pool == 120.0
    finally:
        asyncio.run(client.aclose())


def test_rewrite_kkfileview_html_keeps_already_proxied_image_paths():
    """图片预览返回的 guoyu-src 可能已经带代理前缀，不能重复改写。"""
    from app.modules.workspace.office_preview import rewrite_kkfileview_html

    html = (
        '<img src="/api/workspace/kkfileview/images/loading.gif" '
        'guoyu-src="/api/workspace/kkfileview/reportdocx/0.jpg">'
    )

    rewritten = rewrite_kkfileview_html(
        html,
        "/api/workspace/kkfileview",
        "http://kkfileview:8012",
    )

    assert 'src="/api/workspace/kkfileview/images/loading.gif"' in rewritten
    assert 'guoyu-src="/api/workspace/kkfileview/reportdocx/0.jpg"' in rewritten
    assert "/api/workspace/kkfileview/api/workspace/kkfileview" not in rewritten


def test_signed_file_token_round_trip(monkeypatch):
    from app.modules.workspace.office_preview import create_file_token, verify_file_token

    monkeypatch.setattr("app.modules.workspace.office_preview.time.time", lambda: 1000)
    token = create_file_token("alice", "docs/a.docx", secret="secret", ttl_seconds=300, nonce="n1")

    assert verify_file_token(token, secret="secret") == {
        "username": "alice",
        "path": "docs/a.docx",
        "expires": 1300,
        "nonce": "n1",
    }


def test_signed_file_token_path_with_pipe(monkeypatch):
    """验证路径中包含 '|' 时不会导致 token 解析失败。"""
    from app.modules.workspace.office_preview import create_file_token, verify_file_token

    monkeypatch.setattr("app.modules.workspace.office_preview.time.time", lambda: 1000)
    token = create_file_token("alice", "docs|report/a.docx", secret="secret", ttl_seconds=300, nonce="n1")

    assert verify_file_token(token, secret="secret") == {
        "username": "alice",
        "path": "docs|report/a.docx",
        "expires": 1300,
        "nonce": "n1",
    }


def test_signed_file_token_rejects_tampering(monkeypatch):
    from app.modules.workspace.office_preview import create_file_token, verify_file_token

    monkeypatch.setattr("app.modules.workspace.office_preview.time.time", lambda: 1000)
    token = create_file_token("alice", "docs/a.docx", secret="secret", ttl_seconds=300, nonce="n1")
    # 篡改 token 中的签名部分（最后一位字符翻转）
    bad = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(HTTPException) as exc:
        verify_file_token(bad, secret="secret")

    assert exc.value.status_code == 403


def test_signed_file_token_rejects_expired(monkeypatch):
    from app.modules.workspace.office_preview import create_file_token, verify_file_token

    monkeypatch.setattr("app.modules.workspace.office_preview.time.time", lambda: 1000)
    token = create_file_token("alice", "docs/a.docx", secret="secret", ttl_seconds=1, nonce="n1")
    monkeypatch.setattr("app.modules.workspace.office_preview.time.time", lambda: 1002)

    with pytest.raises(HTTPException) as exc:
        verify_file_token(token, secret="secret")

    assert exc.value.status_code == 401


def test_signed_file_token_rejects_wrong_secret(monkeypatch):
    from app.modules.workspace.office_preview import create_file_token, verify_file_token

    monkeypatch.setattr("app.modules.workspace.office_preview.time.time", lambda: 1000)
    token = create_file_token("alice", "docs/a.docx", secret="secret", ttl_seconds=300, nonce="n1")

    with pytest.raises(HTTPException) as exc:
        verify_file_token(token, secret="wrong")

    assert exc.value.status_code == 403


def test_signed_file_token_rejects_malformed_no_dot(monkeypatch):
    """缺少 payload 与 signature 之间的分隔符 '.' 时应 403。"""
    from app.modules.workspace.office_preview import _encode_token, verify_file_token

    bad_token = _encode_token("just_payload_no_signature")

    with pytest.raises(HTTPException) as exc:
        verify_file_token(bad_token, secret="secret")

    assert exc.value.status_code == 403


def test_signed_file_token_rejects_non_integer_expires(monkeypatch):
    """expires 字段为非整数时应 403。"""
    from app.modules.workspace.office_preview import _encode_token, _sign, verify_file_token

    payload = '{"u":"alice","p":"docs/a.docx","e":"not_an_int","n":"n1"}'
    signature = _sign(payload, "secret")
    bad_token = _encode_token(f"{payload}.{signature}")

    with pytest.raises(HTTPException) as exc:
        verify_file_token(bad_token, secret="secret")

    assert exc.value.status_code == 403


async def test_office_preview_requires_config(logged_in_client):
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "a.docx").write_bytes(b"PK")

    r = await logged_in_client.get("/api/workspace/office-preview", params={"path": "a.docx"})

    assert r.status_code == 503
    assert "Office 预览服务未配置" in r.json()["detail"]


async def test_office_preview_rejects_non_office(logged_in_client, monkeypatch):
    from app.core.config import get_settings, user_workspace

    settings = get_settings()
    monkeypatch.setattr(settings, "app_internal_base_url", "http://backend:8000")
    monkeypatch.setattr(settings, "kkfileview_base_url", "http://kkfileview:8012")
    ws = user_workspace("alice")
    (ws / "a.md").write_text("# title")

    r = await logged_in_client.get("/api/workspace/office-preview", params={"path": "a.md"})

    assert r.status_code == 400
    assert "仅 Office/PDF 文件支持" in r.json()["detail"]


async def test_internal_preview_file_serves_signed_office(logged_in_client, monkeypatch):
    from app.core.config import get_settings, user_workspace
    from app.modules.workspace.office_preview import create_file_token

    settings = get_settings()
    ws = user_workspace("alice")
    (ws / "a.docx").write_bytes(b"PK")
    token = create_file_token("alice", "a.docx", secret=settings.app_secret, ttl_seconds=300, nonce="n1")

    r = await logged_in_client.get("/api/workspace/internal-preview-file", params={"token": token})

    assert r.status_code == 200
    assert r.content == b"PK"
    assert "inline" in r.headers.get("content-disposition", "")


async def test_internal_preview_file_allows_anonymous_with_valid_token(client):
    """internal-preview-file 已被加入 auth_guard 白名单，允许匿名访问。"""
    from app.core.config import get_settings, user_workspace
    from app.modules.workspace.office_preview import create_file_token

    settings = get_settings()
    ws = user_workspace("alice")
    (ws / "a.docx").write_bytes(b"PK")
    token = create_file_token("alice", "a.docx", secret=settings.app_secret, ttl_seconds=300)

    r = await client.get("/api/workspace/internal-preview-file", params={"token": token})

    assert r.status_code == 200
    assert r.content == b"PK"


async def test_office_preview_builds_kkfileview_request(logged_in_client, monkeypatch):
    import httpx
    from app.core.config import get_settings, user_workspace

    settings = get_settings()
    monkeypatch.setattr(settings, "app_internal_base_url", "http://backend:8000")
    monkeypatch.setattr(settings, "kkfileview_base_url", "http://kkfileview:8012")
    ws = user_workspace("alice")
    (ws / "a.docx").write_bytes(b"PK")
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            text="<html><link rel='stylesheet' href='xlsx/css/luckysheet.css' /><script src=\"/js/app.js\"></script></html>",
            headers={"content-type": "text/html"},
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("app.modules.workspace.office_preview.create_proxy_client", lambda: httpx.AsyncClient(transport=transport))

    r = await logged_in_client.get("/api/workspace/office-preview", params={"path": "a.docx"})

    assert r.status_code == 200
    assert seen["url"].startswith("http://kkfileview:8012/onlinePreview?url=")
    assert "/api/workspace/kkfileview/js/app.js" in r.text
    assert "/api/workspace/kkfileview/xlsx/css/luckysheet.css" in r.text


async def test_office_preview_allows_pdf_for_kkfileview(logged_in_client, monkeypatch):
    """PDF 也应走 kkFileView 链路，避免和 Office 预览体验不一致。"""
    import httpx
    from app.core.config import get_settings, user_workspace

    settings = get_settings()
    monkeypatch.setattr(settings, "app_internal_base_url", "http://backend:8000")
    monkeypatch.setattr(settings, "kkfileview_base_url", "http://kkfileview:8012")
    ws = user_workspace("alice")
    (ws / "a.pdf").write_bytes(b"%PDF")
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, text="<html>pdf</html>", headers={"content-type": "text/html"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("app.modules.workspace.office_preview.create_proxy_client", lambda: httpx.AsyncClient(transport=transport))

    r = await logged_in_client.get("/api/workspace/office-preview", params={"path": "a.pdf"})

    assert r.status_code == 200
    assert seen["url"].startswith("http://kkfileview:8012/onlinePreview?url=")


async def test_office_preview_uses_pdf_preview_for_files_under_20mb(logged_in_client, monkeypatch):
    """小于 20MB 的文档应使用 kkFileView 的 PDF 预览模式。"""
    import httpx
    from urllib.parse import parse_qs, urlparse
    from app.core.config import get_settings, user_workspace

    settings = get_settings()
    monkeypatch.setattr(settings, "app_internal_base_url", "http://backend:8000")
    monkeypatch.setattr(settings, "kkfileview_base_url", "http://kkfileview:8012")
    ws = user_workspace("alice")
    (ws / "small.docx").write_bytes(b"PK")
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, text="<html>doc</html>", headers={"content-type": "text/html"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("app.modules.workspace.office_preview.create_proxy_client", lambda: httpx.AsyncClient(transport=transport))

    r = await logged_in_client.get("/api/workspace/office-preview", params={"path": "small.docx"})

    assert r.status_code == 200
    query = parse_qs(urlparse(seen["url"]).query)
    assert query["officePreviewType"] == ["pdf"]


async def test_office_preview_uses_image_preview_for_files_at_least_20mb(logged_in_client, monkeypatch):
    """20MB 及以上的大文件应使用 kkFileView 的图片预览模式。"""
    import httpx
    from urllib.parse import parse_qs, urlparse
    from app.core.config import get_settings, user_workspace

    settings = get_settings()
    monkeypatch.setattr(settings, "app_internal_base_url", "http://backend:8000")
    monkeypatch.setattr(settings, "kkfileview_base_url", "http://kkfileview:8012")
    ws = user_workspace("alice")
    with (ws / "large.docx").open("wb") as f:
        f.truncate(20 * 1024 * 1024)
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, text="<html>doc</html>", headers={"content-type": "text/html"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("app.modules.workspace.office_preview.create_proxy_client", lambda: httpx.AsyncClient(transport=transport))

    r = await logged_in_client.get("/api/workspace/office-preview", params={"path": "large.docx"})

    assert r.status_code == 200
    query = parse_qs(urlparse(seen["url"]).query)
    assert query["officePreviewType"] == ["image"]


async def test_kkfileview_context_path_is_proxied(client, monkeypatch):
    """kkFileView 部署在 /kkfileview 下时，同源 /kkfileview/* 请求应转发到内网服务。"""
    import httpx
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "kkfileview_base_url", "http://localhost:8012/kkfileview")
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            content=b"body{color:#111}",
            headers={"content-type": "text/css"},
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("app.modules.workspace.office_preview.create_proxy_client", lambda: httpx.AsyncClient(transport=transport))

    r = await client.get("/kkfileview/css/theme.css")

    assert r.status_code == 200
    assert seen["url"] == "http://localhost:8012/kkfileview/css/theme.css"
    assert r.headers.get("content-type", "").startswith("text/css")
    assert r.content == b"body{color:#111}"


async def test_kkfileview_relative_xlsx_asset_under_workspace_api_is_proxied(logged_in_client, monkeypatch):
    """office-preview 页面里的 xlsx/... 相对资源应改写到 /api/workspace/kkfileview/... 后代理。"""
    import httpx
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "kkfileview_base_url", "http://localhost:8012/kkfileview")
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            content=b".luckysheet{display:block}",
            headers={"content-type": "text/css"},
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("app.modules.workspace.office_preview.create_proxy_client", lambda: httpx.AsyncClient(transport=transport))

    r = await logged_in_client.get("/api/workspace/kkfileview/xlsx/css/luckysheet.css")

    assert r.status_code == 200
    assert seen["url"] == "http://localhost:8012/kkfileview/xlsx/css/luckysheet.css"
    assert r.headers.get("content-type", "").startswith("text/css")
    assert r.content == b".luckysheet{display:block}"


async def test_kkfileview_asset_proxy_preserves_cache_headers(client, monkeypatch):
    """代理静态资源时应透传缓存头，让浏览器能复用 kkFileView 的样式和脚本。"""
    import httpx
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "kkfileview_base_url", "http://localhost:8012/kkfileview")
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["if_none_match"] = request.headers.get("if-none-match")
        return httpx.Response(
            304,
            headers={
                "etag": '"asset-v1"',
                "cache-control": "public, max-age=31536000",
            },
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("app.modules.workspace.office_preview.create_proxy_client", lambda: httpx.AsyncClient(transport=transport))

    r = await client.get("/kkfileview/js/app.js", headers={"if-none-match": '"asset-v1"'})

    assert r.status_code == 304
    assert seen["if_none_match"] == '"asset-v1"'
    assert r.headers.get("etag") == '"asset-v1"'
    assert r.headers.get("cache-control") == "public, max-age=31536000"
