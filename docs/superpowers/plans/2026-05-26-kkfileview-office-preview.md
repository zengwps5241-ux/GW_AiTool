# kkFileView Office Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route Office preview through kkFileView behind a backend proxy, preview PDFs directly in the browser, and keep Markdown editing as an explicit separate mode.

**Architecture:** Backend adds focused config, signing, internal file serving, kkFileView proxy, and a separate Markdown preview endpoint. Frontend centralizes file preview classification so the standalone personal workspace and chat workspace modal use the same Office/PDF routing while the standalone workspace adds a preview/edit mode switch for converted Markdown.

**Tech Stack:** FastAPI, httpx, HMAC signing with `APP_SECRET`, pytest, React, TypeScript, Vite.

---

## File Structure

- Modify `backend/app/core/config.py`: add `app_internal_base_url` and `kkfileview_base_url`.
- Modify `backend/.env.example`: document `APP_INTERNAL_BASE_URL` and `KKFILEVIEW_BASE_URL`.
- Create `backend/app/modules/workspace/office_preview.py`: Office suffix checks, signed URL creation/verification, kkFileView URL construction, proxy response rewriting.
- Modify `backend/app/modules/workspace/preview.py`: split Office and PDF suffix rules and keep raw preview MIME classification.
- Modify `backend/app/modules/workspace/service.py`: change `/preview` to raw preview semantics and add Markdown preview service.
- Modify `backend/app/api/routes/workspace.py`: add Office preview, Office proxy, internal signed file, and Markdown preview routes.
- Modify `backend/tests/conftest.py`: reload the new workspace module.
- Modify `backend/tests/test_config.py`: cover new config defaults and env override.
- Create `backend/tests/test_workspace_office_preview.py`: cover signing, proxy URL construction, signed file access, and route errors.
- Modify `backend/tests/test_workspace_preview.py`: update PDF/raw preview expectations and add Markdown preview route coverage.
- Modify `backend/tests/test_workspace_preview_unified_service.py`: update service tests for raw preview vs Markdown preview.
- Modify `frontend/src/lib/workspace.ts`: add Office/PDF helpers and preview categories.
- Modify `frontend/src/api/client.ts`: add Office preview and Markdown preview URL helpers.
- Modify `frontend/src/components/workspace/useWorkspacePreview.ts`: support preview sources for raw vs Markdown edit.
- Modify `frontend/src/components/workspace/WorkspacePreview.tsx`: add Office/PDF iframe preview, edit mode controls, and explicit Markdown edit rendering.
- Modify `frontend/src/pages/WorkspacePage.tsx`: manage preview/edit mode and unsaved transitions.
- Modify `frontend/src/pages/ChatWorkspace.tsx`: route Office/PDF modal preview through the shared classification.
- Create `frontend/tests/workspacePreview.test.ts`: validate shared classification and URL routing.

---

### Task 1: Backend Config

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/test_config.py`

- [ ] **Step 1: Write failing config tests**

Add to `backend/tests/test_config.py`:

```python
def test_office_preview_settings_default_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "corp123")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "agent456")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "secret789")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    s = core_config.get_settings()
    assert s.app_internal_base_url == ""
    assert s.kkfileview_base_url == ""


def test_office_preview_settings_can_be_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "corp123")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "agent456")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "secret789")
    monkeypatch.setenv("APP_INTERNAL_BASE_URL", "http://backend:8000/")
    monkeypatch.setenv("KKFILEVIEW_BASE_URL", "http://kkfileview:8012/")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    s = core_config.get_settings()
    assert s.app_internal_base_url == "http://backend:8000/"
    assert s.kkfileview_base_url == "http://kkfileview:8012/"
```

- [ ] **Step 2: Verify failure**

Run:

```bash
cd backend && uv run pytest tests/test_config.py::test_office_preview_settings_default_empty tests/test_config.py::test_office_preview_settings_can_be_configured -q
```

Expected: FAIL with missing `Settings.app_internal_base_url`.

- [ ] **Step 3: Implement config fields**

In `backend/app/core/config.py`, add fields near the other integration settings:

```python
    app_internal_base_url: str = ""
    kkfileview_base_url: str = ""
```

In `backend/.env.example`, add:

```dotenv
# Office 预览: kkFileView 仅由后端内网访问,不要暴露给用户浏览器
# APP_INTERNAL_BASE_URL=http://backend:8000
# KKFILEVIEW_BASE_URL=http://192.168.125.180:8012
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
cd backend && uv run pytest tests/test_config.py::test_office_preview_settings_default_empty tests/test_config.py::test_office_preview_settings_can_be_configured -q
```

Expected: PASS.

Commit:

```bash
git add backend/app/core/config.py backend/.env.example backend/tests/test_config.py
git commit -m "feat: 增加office预览配置"
```

---

### Task 2: Office Preview Signing

**Files:**
- Create: `backend/app/modules/workspace/office_preview.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_workspace_office_preview.py`

- [ ] **Step 1: Write signing tests**

Create `backend/tests/test_workspace_office_preview.py`:

```python
from pathlib import Path

import pytest
from fastapi import HTTPException


def test_office_suffix_detection():
    from app.modules.workspace.office_preview import is_office_document

    assert is_office_document(Path("a.docx"))
    assert is_office_document(Path("a.ppt"))
    assert is_office_document(Path("a.xlsx"))
    assert not is_office_document(Path("a.pdf"))
    assert not is_office_document(Path("a.md"))


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


def test_signed_file_token_rejects_tampering(monkeypatch):
    from app.modules.workspace.office_preview import create_file_token, verify_file_token

    monkeypatch.setattr("app.modules.workspace.office_preview.time.time", lambda: 1000)
    token = create_file_token("alice", "docs/a.docx", secret="secret", ttl_seconds=300, nonce="n1")
    bad = token.replace("docs/a.docx", "docs/b.docx")

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
```

- [ ] **Step 2: Verify failure**

Run:

```bash
cd backend && uv run pytest tests/test_workspace_office_preview.py -q
```

Expected: FAIL because `office_preview.py` does not exist.

- [ ] **Step 3: Implement signing module**

Create `backend/app/modules/workspace/office_preview.py`:

```python
"""Office 预览:签名 URL 与 kkFileView 代理辅助函数。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import HTTPException, status

_OFFICE_SUFFIXES = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
_TOKEN_SEPARATOR = "|"


def is_office_document(path: str | Path) -> bool:
    """判断文件是否应交给 kkFileView 预览。"""
    return Path(path).suffix.lower() in _OFFICE_SUFFIXES


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
    payload = _TOKEN_SEPARATOR.join([username, rel_path, str(expires), nonce])
    signature = _sign(payload, secret)
    return _encode_token(_TOKEN_SEPARATOR.join([payload, signature]))


def verify_file_token(token: str, *, secret: str) -> dict[str, str | int]:
    raw = _decode_token(token)
    parts = raw.split(_TOKEN_SEPARATOR)
    if len(parts) != 5:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="签名无效")
    username, rel_path, expires_raw, nonce, signature = parts
    payload = _TOKEN_SEPARATOR.join([username, rel_path, expires_raw, nonce])
    expected = _sign(payload, secret)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="签名无效")
    try:
        expires = int(expires_raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="签名无效") from exc
    if expires < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="签名已过期")
    return {"username": username, "path": rel_path, "expires": expires, "nonce": nonce}


def build_internal_file_url(base_url: str, token: str, filename: str) -> str:
    root = base_url.rstrip("/")
    query = urlencode({"token": token, "fullfilename": filename})
    return f"{root}/api/workspace/internal-preview-file?{query}"


def build_kkfileview_online_preview_url(base_url: str, source_url: str) -> str:
    root = base_url.rstrip("/")
    encoded_source = base64.b64encode(source_url.encode("utf-8")).decode("ascii")
    return f"{root}/onlinePreview?url={quote(encoded_source, safe='')}"
```

- [ ] **Step 4: Reload module in tests**

In `backend/tests/conftest.py`, update workspace module imports:

```python
        office_preview,
```

Add:

```python
    reload(office_preview)
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
cd backend && uv run pytest tests/test_workspace_office_preview.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/app/modules/workspace/office_preview.py backend/tests/conftest.py backend/tests/test_workspace_office_preview.py
git commit -m "feat: 增加office预览签名"
```

---

### Task 3: Backend Raw Preview and Markdown Preview Split

**Files:**
- Modify: `backend/app/modules/workspace/preview.py`
- Modify: `backend/app/modules/workspace/service.py`
- Modify: `backend/app/api/routes/workspace.py`
- Modify: `backend/tests/test_workspace_preview.py`
- Modify: `backend/tests/test_workspace_preview_unified_service.py`

- [ ] **Step 1: Update failing tests for new semantics**

In `backend/tests/test_workspace_preview.py`, replace the PDF Markdown preview tests with:

```python
async def test_preview_pdf_returns_raw_pdf_even_with_markdown_mapping(logged_in_client):
    """普通预览 PDF 时返回原 PDF，编辑 Markdown 另走 markdown-preview。"""
    from app.core.config import user_workspace
    from app.modules.workspace.markdown_index import add_markdown_mapping

    ws = user_workspace("alice")
    (ws / "uploads").mkdir()
    (ws / "uploads" / "a.pdf").write_bytes(b"%PDF")
    (ws / ".markdown" / "a" / "hybrid_auto").mkdir(parents=True)
    (ws / ".markdown" / "a" / "hybrid_auto" / "a.md").write_text("# Converted", encoding="utf-8")
    add_markdown_mapping(
        ws,
        source_path="uploads/a.pdf",
        source_name="a.pdf",
        markdown_path=".markdown/a/hybrid_auto/a.md",
        extract_dir=".markdown/a",
    )

    r = await logged_in_client.get("/api/workspace/preview", params={"path": "uploads/a.pdf"})

    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.headers.get("x-resolved-preview-path") == "uploads/a.pdf"
    assert r.content == b"%PDF"


async def test_markdown_preview_source_pdf_returns_mapped_markdown(logged_in_client):
    """编辑 Markdown 时，PDF 源文件仍返回转换后的 Markdown。"""
    from app.core.config import user_workspace
    from app.modules.workspace.markdown_index import add_markdown_mapping

    ws = user_workspace("alice")
    (ws / "uploads").mkdir()
    (ws / "uploads" / "a.pdf").write_bytes(b"%PDF")
    (ws / ".markdown" / "a" / "hybrid_auto").mkdir(parents=True)
    (ws / ".markdown" / "a" / "hybrid_auto" / "a.md").write_text("# Converted", encoding="utf-8")
    add_markdown_mapping(
        ws,
        source_path="uploads/a.pdf",
        source_name="a.pdf",
        markdown_path=".markdown/a/hybrid_auto/a.md",
        extract_dir=".markdown/a",
    )

    r = await logged_in_client.get("/api/workspace/markdown-preview", params={"path": "uploads/a.pdf"})

    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("text/plain")
    assert r.headers.get("x-resolved-preview-path") == ".markdown/a/hybrid_auto/a.md"
    assert r.text == "# Converted"
```

In `backend/tests/test_workspace_preview_unified_service.py`, update:

```python
def test_raw_preview_pdf_without_markdown_mapping_returns_file_response(tmp_path):
    """普通预览 PDF 不再要求 Markdown 映射。"""
    from fastapi.responses import FileResponse
    from app.modules.workspace.service import preview_workspace_item

    workspace = tmp_path
    (workspace / "raw.pdf").write_bytes(b"%PDF")

    response = preview_workspace_item(workspace, "raw.pdf")

    assert isinstance(response, FileResponse)


def test_markdown_preview_pdf_without_mapping_raises_unified_hint(tmp_path):
    """Markdown 编辑预览没有映射时，仍返回统一提示。"""
    from app.modules.workspace.service import preview_workspace_markdown_item

    workspace = tmp_path
    (workspace / "raw.pdf").write_bytes(b"%PDF")

    with pytest.raises(HTTPException) as exc:
        preview_workspace_markdown_item(workspace, "raw.pdf")

    assert exc.value.status_code == 409
    assert "尚未生成转换后的 Markdown" in exc.value.detail
```

- [ ] **Step 2: Verify failure**

Run:

```bash
cd backend && uv run pytest tests/test_workspace_preview.py::test_preview_pdf_returns_raw_pdf_even_with_markdown_mapping tests/test_workspace_preview.py::test_markdown_preview_source_pdf_returns_mapped_markdown tests/test_workspace_preview_unified_service.py -q
```

Expected: FAIL because `/markdown-preview` and `preview_workspace_markdown_item` do not exist, and `/preview` still maps PDF to Markdown.

- [ ] **Step 3: Split suffix rules**

In `backend/app/modules/workspace/preview.py`, replace `_CONVERTIBLE_SUFFIXES` with:

```python
_OFFICE_SUFFIXES = {
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
}

_CONVERTIBLE_SUFFIXES = _OFFICE_SUFFIXES | {".pdf"}
```

Keep `is_convertible_document` unchanged for Markdown editing and conversion workflows.

- [ ] **Step 4: Change raw preview and add Markdown preview service**

In `backend/app/modules/workspace/service.py`, change `preview_workspace_item` so it no longer calls `resolve_preview_path`. It should use `source_target` directly:

```python
def preview_workspace_item(workspace: Path, rel_path: str):
    workspace_root = workspace.resolve()
    target = resolve_inside_workspace(workspace, rel_path)
    if not target.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    if target.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目录不支持预览,请下载")

    mime = guess_mime(target)
    kind = preview_kind(mime)
    if kind is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="该类型不支持预览,请下载",
        )
    # 保留现有大小限制和响应头逻辑。
```

Add a new function that contains the old mapping behavior:

```python
def preview_workspace_markdown_item(workspace: Path, rel_path: str):
    workspace_root = workspace.resolve()
    source_target = resolve_inside_workspace(workspace, rel_path)
    mapped_rel_path = resolve_preview_path(workspace, rel_path)
    if mapped_rel_path == rel_path and is_convertible_document(source_target):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_CONVERTED_MARKDOWN_MISSING,
        )
    target = resolve_inside_workspace(workspace, mapped_rel_path)
    if not target.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    if target.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目录不支持预览,请下载")
    mime = guess_mime(target)
    kind = preview_kind(mime)
    if kind != "text":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="该类型不支持文本编辑",
        )
    headers = inline_headers(mime)
    headers["X-Resolved-Preview-Path"] = quote(target.relative_to(workspace_root).as_posix(), safe="/._-")
    return FileResponse(path=target, media_type=mime, headers=headers)
```

Reuse the same size-limit block from `preview_workspace_item` for text files.

- [ ] **Step 5: Add route**

In `backend/app/api/routes/workspace.py`, import `preview_workspace_markdown_item` and add:

```python
@router.get("/markdown-preview")
def preview_workspace_markdown_route(
    path: str = Query(..., description="相对于工作区的文件路径"),
    user: User = Depends(current_user),
):
    return preview_workspace_markdown_item(user_workspace(user.username), path)
```

- [ ] **Step 6: Run tests and commit**

Run:

```bash
cd backend && uv run pytest tests/test_workspace_preview.py tests/test_workspace_preview_unified_service.py -q
```

Expected: PASS after updating stale assertions that expected `/preview` to return Markdown for PDF.

Commit:

```bash
git add backend/app/modules/workspace/preview.py backend/app/modules/workspace/service.py backend/app/api/routes/workspace.py backend/tests/test_workspace_preview.py backend/tests/test_workspace_preview_unified_service.py
git commit -m "feat: 拆分原文件预览和markdown预览"
```

---

### Task 4: Office Preview Routes and kkFileView Proxy

**Files:**
- Modify: `backend/app/modules/workspace/office_preview.py`
- Modify: `backend/app/api/routes/workspace.py`
- Modify: `backend/tests/test_workspace_office_preview.py`

- [ ] **Step 1: Add route tests**

Append to `backend/tests/test_workspace_office_preview.py`:

```python
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
    (ws / "a.pdf").write_bytes(b"%PDF")

    r = await logged_in_client.get("/api/workspace/office-preview", params={"path": "a.pdf"})

    assert r.status_code == 400
    assert "仅 Office 文件支持" in r.json()["detail"]


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
        return httpx.Response(200, text="<html><script src=\"/js/app.js\"></script></html>", headers={"content-type": "text/html"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("app.modules.workspace.office_preview.create_proxy_client", lambda: httpx.AsyncClient(transport=transport))

    r = await logged_in_client.get("/api/workspace/office-preview", params={"path": "a.docx"})

    assert r.status_code == 200
    assert seen["url"].startswith("http://kkfileview:8012/onlinePreview?url=")
    assert "/api/workspace/office-preview/proxy/js/app.js" in r.text
```

- [ ] **Step 2: Verify failure**

Run:

```bash
cd backend && uv run pytest tests/test_workspace_office_preview.py -q
```

Expected: FAIL because routes and proxy client functions do not exist.

- [ ] **Step 3: Implement proxy helpers**

Add to `backend/app/modules/workspace/office_preview.py`:

```python
import re
from collections.abc import AsyncIterator

import httpx
from fastapi.responses import Response, StreamingResponse


def create_proxy_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30.0, follow_redirects=True)


def rewrite_kkfileview_html(html: str, proxy_prefix: str, kk_base_url: str) -> str:
    root = kk_base_url.rstrip("/")
    html = html.replace(root, proxy_prefix.rstrip(""))
    html = re.sub(r'((?:src|href)=["\'])/([^"\']+)', rf"\1{proxy_prefix}/\2", html)
    return html


async def fetch_kkfileview_response(url: str) -> httpx.Response:
    async with create_proxy_client() as client:
        return await client.get(url)


async def stream_kkfileview_path(base_url: str, rel_path: str, query: str) -> StreamingResponse | Response:
    safe_path = rel_path.lstrip("/")
    if "://" in safe_path or safe_path.startswith("//"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理路径无效")
    url = f"{base_url.rstrip('/')}/{safe_path}"
    if query:
        url = f"{url}?{query}"
    response = await fetch_kkfileview_response(url)
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Office 预览服务不可用")
    content_type = response.headers.get("content-type", "application/octet-stream")
    return Response(content=response.content, media_type=content_type)
```

- [ ] **Step 4: Implement routes**

In `backend/app/api/routes/workspace.py`, add async routes:

```python
from fastapi import Request
from fastapi.responses import FileResponse, Response

from app.core.config import get_settings
from app.modules.workspace.office_preview import (
    build_internal_file_url,
    build_kkfileview_online_preview_url,
    create_file_token,
    fetch_kkfileview_response,
    is_office_document,
    rewrite_kkfileview_html,
    stream_kkfileview_path,
    verify_file_token,
)
from app.modules.workspace.paths import resolve_inside_workspace
from app.modules.workspace.preview import guess_mime, inline_headers
```

Add:

```python
@router.get("/office-preview")
async def office_preview_route(
    path: str = Query(..., description="相对于工作区的 Office 文件路径"),
    user: User = Depends(current_user),
):
    settings = get_settings()
    if not settings.app_internal_base_url or not settings.kkfileview_base_url:
        raise HTTPException(status_code=503, detail="Office 预览服务未配置")
    workspace = user_workspace(user.username)
    target = resolve_inside_workspace(workspace, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not is_office_document(target):
        raise HTTPException(status_code=400, detail="仅 Office 文件支持 kkFileView 预览")

    rel_path = target.relative_to(workspace.resolve()).as_posix()
    token = create_file_token(user.username, rel_path, secret=settings.app_secret)
    source_url = build_internal_file_url(settings.app_internal_base_url, token, target.name)
    kk_url = build_kkfileview_online_preview_url(settings.kkfileview_base_url, source_url)
    response = await fetch_kkfileview_response(kk_url)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Office 预览服务不可用")
    content_type = response.headers.get("content-type", "text/html")
    body = response.text if "text/html" in content_type else response.content
    if isinstance(body, str):
        body = rewrite_kkfileview_html(
            body,
            "/api/workspace/office-preview/proxy",
            settings.kkfileview_base_url,
        )
    return Response(content=body, media_type=content_type)


@router.get("/office-preview/proxy/{rel_path:path}")
async def office_preview_proxy_route(rel_path: str, request: Request):
    settings = get_settings()
    if not settings.kkfileview_base_url:
        raise HTTPException(status_code=503, detail="Office 预览服务未配置")
    return await stream_kkfileview_path(settings.kkfileview_base_url, rel_path, request.url.query)


@router.get("/internal-preview-file")
def internal_preview_file_route(token: str = Query(...)):
    settings = get_settings()
    data = verify_file_token(token, secret=settings.app_secret)
    workspace = user_workspace(str(data["username"]))
    target = resolve_inside_workspace(workspace, str(data["path"]))
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not is_office_document(target):
        raise HTTPException(status_code=400, detail="仅 Office 文件支持")
    headers = inline_headers(guess_mime(target))
    headers["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(target.name, safe='')}"
    return FileResponse(path=target, media_type=guess_mime(target), headers=headers)
```

Ensure `HTTPException` and `quote` are imported.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
cd backend && uv run pytest tests/test_workspace_office_preview.py tests/test_workspace_preview.py tests/test_workspace_preview_unified_service.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/app/modules/workspace/office_preview.py backend/app/api/routes/workspace.py backend/tests/test_workspace_office_preview.py
git commit -m "feat: 代理kkfileview office预览"
```

---

### Task 5: Frontend Shared Preview Classification and API URLs

**Files:**
- Modify: `frontend/src/lib/workspace.ts`
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/tests/workspacePreview.test.ts`

- [ ] **Step 1: Write failing frontend classification test**

Create `frontend/tests/workspacePreview.test.ts`:

```ts
import assert from "node:assert/strict";
import {
  isOfficeName,
  isPdfName,
  workspacePreviewCategory,
} from "../src/lib/workspace";
import { api } from "../src/api/client";

assert.equal(isOfficeName("a.doc"), true);
assert.equal(isOfficeName("a.docx"), true);
assert.equal(isOfficeName("a.pptx"), true);
assert.equal(isOfficeName("a.xlsx"), true);
assert.equal(isOfficeName("a.pdf"), false);
assert.equal(isPdfName("a.pdf"), true);
assert.equal(isPdfName("a.docx"), false);

assert.equal(workspacePreviewCategory("a.docx"), "office");
assert.equal(workspacePreviewCategory("a.pdf"), "pdf");
assert.equal(workspacePreviewCategory("a.md"), "text");
assert.equal(workspacePreviewCategory("a.png"), "image");

assert.equal(
  api.workspaceOfficePreviewUrl("dir/a.docx"),
  "/api/workspace/office-preview?path=dir%2Fa.docx",
);
assert.equal(
  api.workspaceMarkdownPreviewUrl("dir/a.docx"),
  "/api/workspace/markdown-preview?path=dir%2Fa.docx",
);
```

- [ ] **Step 2: Verify failure**

Run:

```bash
cd frontend && npm exec --package tsx -- tsx tests/workspacePreview.test.ts
```

Expected: FAIL with missing exports such as `isOfficeName` or `workspaceOfficePreviewUrl`.

- [ ] **Step 3: Implement helpers**

In `frontend/src/lib/workspace.ts`, change Office constants:

```ts
const OFFICE_EXTS = new Set(["doc", "docx", "ppt", "pptx", "xls", "xlsx"]);
const CONVERTIBLE_EXTS = new Set([...OFFICE_EXTS, "pdf"]);
```

Add:

```ts
export function isOfficeName(name: string): boolean {
  return OFFICE_EXTS.has(fileExt(name));
}

export function isPdfName(name: string): boolean {
  return fileExt(name) === "pdf";
}
```

Change `isConvertibleName`:

```ts
export function isConvertibleName(name: string): boolean {
  return CONVERTIBLE_EXTS.has(fileExt(name));
}
```

Extend `WorkspacePreviewCategory`:

```ts
export type WorkspacePreviewCategory =
  | "text"
  | "office"
  | "pdf"
  | "image"
  | "video"
  | "audio"
  | "unsupported";
```

Change `workspacePreviewCategory`:

```ts
  if (OFFICE_EXTS.has(ext)) return "office";
  if (ext === "pdf") return "pdf";
```

In `frontend/src/api/client.ts`, add:

```ts
  workspaceOfficePreviewUrl: (path: string) =>
    `/api/workspace/office-preview?path=${encodeURIComponent(path)}`,

  workspaceMarkdownPreviewUrl: (path: string) =>
    `/api/workspace/markdown-preview?path=${encodeURIComponent(path)}`,
```

- [ ] **Step 4: Run checks and commit**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS after resolving TypeScript errors.

Commit:

```bash
git add frontend/src/lib/workspace.ts frontend/src/api/client.ts frontend/tests/workspacePreview.test.ts
git commit -m "feat: 增加工作空间预览分类"
```

---

### Task 6: Frontend Preview Hook Supports Raw and Markdown Sources

**Files:**
- Modify: `frontend/src/components/workspace/useWorkspacePreview.ts`

- [ ] **Step 1: Update hook signature**

Change the signature to accept a mode:

```ts
export type WorkspacePreviewSource = "raw" | "markdown";

export function useWorkspacePreview(
  path: string | null,
  name: string | null,
  reloadKey = 0,
  source: WorkspacePreviewSource = "raw",
): WorkspacePreviewState {
```

- [ ] **Step 2: Update fetch decision**

Replace `shouldFetchText` calculation with:

```ts
  const shouldFetchText = Boolean(
    name &&
      (
        category === "text" ||
        source === "markdown"
      ),
  );
```

When fetching text, use:

```ts
        const url =
          source === "markdown"
            ? api.workspaceMarkdownPreviewUrl(path)
            : api.workspacePreviewUrl(path);
        const result = await fetchPreviewText(url, abort.signal);
```

Add `source` to the effect dependency list and to the loaded-key state. The stale-preview check should include source:

```ts
  const [loadedSource, setLoadedSource] = useState<WorkspacePreviewSource>("raw");
  ...
  setLoadedSource(source);
  ...
  const isCurrentPreview = loadedPath === path && loadedName === name && loadedSource === source;
```

- [ ] **Step 3: Run build and commit**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

Commit:

```bash
git add frontend/src/components/workspace/useWorkspacePreview.ts
git commit -m "feat: 支持markdown预览数据源"
```

---

### Task 7: Standalone Workspace Preview/Edit Split

**Files:**
- Modify: `frontend/src/components/workspace/WorkspacePreview.tsx`
- Modify: `frontend/src/pages/WorkspacePage.tsx`

- [ ] **Step 1: Add preview mode state in page**

In `frontend/src/pages/WorkspacePage.tsx`, add:

```ts
  const [previewMode, setPreviewMode] = useState<"preview" | "edit">("preview");
```

Pass source into hook:

```ts
  const preview = useWorkspacePreview(
    selected?.type === "file" ? selected.path : null,
    selected?.type === "file" ? selected.name : null,
    previewReloadKey,
    previewMode === "edit" ? "markdown" : "raw",
  );
```

Reset mode when selecting a new node:

```ts
    setPreviewMode("preview");
```

Add helpers:

```ts
  const switchToEdit = useCallback(() => {
    setDirty(false);
    setContent("");
    lastAppliedPreviewRef.current = null;
    setPreviewMode("edit");
    setPreviewReloadKey((v) => v + 1);
  }, []);

  const switchToPreview = useCallback(() => {
    const go = () => {
      setDirty(false);
      setContent("");
      lastAppliedPreviewRef.current = null;
      setPreviewMode("preview");
      setPreviewReloadKey((v) => v + 1);
    };
    if (dirty) {
      confirmUnsaved(go);
      return;
    }
    go();
  }, [confirmUnsaved, dirty]);
```

Pass `mode`, `onEdit`, and `onBackToPreview` to `WorkspacePreview`.

- [ ] **Step 2: Update preview component props**

In `frontend/src/components/workspace/WorkspacePreview.tsx`, extend props:

```ts
  mode: "preview" | "edit";
  onEdit: () => void;
  onBackToPreview: () => void;
```

Import helpers:

```ts
import { isMarkdownPreview, isOfficeName, isPdfName, isTextualMime } from "@/lib/workspace";
```

- [ ] **Step 3: Render toolbar actions**

Compute:

```ts
  const markdownEditable = props.mode === "edit" && preview.text !== null && isTextualMime(preview.mime);
  const canEditMarkdown = isOfficeName(node.name) || isPdfName(node.name);
```

In toolbar, render:

```tsx
        {canEditMarkdown && props.mode === "preview" && (
          <button onClick={props.onEdit} disabled={preview.loading} style={toolbarBtnStyle}>
            编辑
          </button>
        )}
        {props.mode === "edit" && (
          <button onClick={props.onBackToPreview} disabled={preview.loading} style={toolbarBtnStyle}>
            返回预览
          </button>
        )}
```

Render reload/save only for `markdownEditable`.

- [ ] **Step 4: Render Office/PDF preview**

Before text rendering, add:

```tsx
        {!preview.loading && !preview.error && props.mode === "preview" && preview.category === "office" && (
          <iframe
            title={node.name}
            src={api.workspaceOfficePreviewUrl(node.path)}
            style={{ width: "100%", height: "100%", minHeight: 520, border: "none", background: "#fff" }}
          />
        )}

        {!preview.loading && !preview.error && props.mode === "preview" && preview.category === "pdf" && (
          <iframe
            title={node.name}
            src={api.workspacePreviewUrl(node.path)}
            style={{ width: "100%", height: "100%", minHeight: 520, border: "none", background: "#fff" }}
          />
        )}
```

Change existing editable rendering condition from `editable` to `markdownEditable || (props.mode === "preview" && editable && preview.category === "text")` so ordinary text behavior remains.

Change converted Markdown warning to show only in edit mode:

```tsx
      {convertedMarkdown && props.mode === "edit" && (
```

- [ ] **Step 5: Run build and commit**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

Commit:

```bash
git add frontend/src/pages/WorkspacePage.tsx frontend/src/components/workspace/WorkspacePreview.tsx
git commit -m "feat: 拆分office预览和markdown编辑"
```

---

### Task 8: Chat Workspace Modal Uses Same Office/PDF Preview Rules

**Files:**
- Modify: `frontend/src/pages/ChatWorkspace.tsx`

- [ ] **Step 1: Import helpers**

Ensure `ChatWorkspace.tsx` imports `isOfficeName` and `isPdfName` from `@/lib/workspace` wherever existing helpers are imported.

- [ ] **Step 2: Render Office/PDF iframe in modal**

Inside `PreviewModal`, add:

```ts
  const officePreview = isOfficeName(name);
  const pdfPreview = isPdfName(name);
```

Adjust loading/error logic so Office/PDF do not depend on text fetch:

```ts
  const loading = officePreview || pdfPreview ? false : preview.loading;
```

In the body before text preview:

```tsx
          {!previewError && !loading && officePreview && (
            <iframe
              title={name}
              src={api.workspaceOfficePreviewUrl(path)}
              style={{ width: "100%", height: isFullscreen ? "calc(100vh - 48px)" : "75vh", border: "none", background: "#fff" }}
              onError={() => setErrMsg("Office 预览服务不可用")}
            />
          )}
          {!previewError && !loading && pdfPreview && (
            <iframe
              title={name}
              src={api.workspacePreviewUrl(path)}
              style={{ width: "100%", height: isFullscreen ? "calc(100vh - 48px)" : "75vh", border: "none", background: "#fff" }}
              onError={() => setErrMsg("加载失败")}
            />
          )}
```

Guard the existing text/media unsupported blocks with `!officePreview && !pdfPreview`.

- [ ] **Step 3: Run build and commit**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

Commit:

```bash
git add frontend/src/pages/ChatWorkspace.tsx
git commit -m "feat: 聊天空间复用office和pdf预览"
```

---

### Task 9: Full Verification

**Files:**
- No source edits unless verification reveals defects.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
cd backend && uv run pytest tests/test_config.py tests/test_workspace_office_preview.py tests/test_workspace_preview.py tests/test_workspace_preview_unified_service.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Check git status**

Run:

```bash
git status --short
```

Expected: only intentional changes are present. The pre-existing untracked `design/动态多智能体编排系统设计文档-v2.md` may remain untracked and must not be committed.

- [ ] **Step 4: Final commit if fixes were required**

If verification fixes were made, commit only those files:

```bash
git add backend/app backend/tests frontend/src frontend/tests
git commit -m "fix: 完善office预览验证"
```

If no fixes were required, do not create an empty commit.

---

## Self-Review

- Spec coverage: configuration, backend proxy, signed internal file access, raw PDF preview, separated Markdown edit preview, standalone workspace UI, chat workspace modal, errors, and tests are each covered by a task.
- Placeholder scan: no unresolved placeholder wording or intentionally vague delayed work remains.
- Type consistency: frontend category names are `office` and `pdf`; API helpers are `workspaceOfficePreviewUrl` and `workspaceMarkdownPreviewUrl`; backend route names match the spec.
