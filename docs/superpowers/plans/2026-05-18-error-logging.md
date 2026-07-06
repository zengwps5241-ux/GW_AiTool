# Error Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add minimal backend error logging for local debugging, writing traceback logs to both console and a rotating `logs/app.log` file without collecting user or business context.

**Architecture:** Add a focused logging configuration module under `app.core`, initialize it during application startup, then add `logger.exception(...)` only at existing exception boundaries. Log messages stay generic and do not include usernames, session ids, prompts, file paths, tool arguments, or tool outputs.

**Tech Stack:** Python standard `logging`, `logging.handlers.RotatingFileHandler`, FastAPI lifespan, pytest, monkeypatch/caplog.

---

## File Structure

- Create `backend/app/core/logging.py`
  - Owns logging defaults, environment parsing, handler setup, and idempotent configuration.

- Modify `backend/app/main.py`
  - Calls logging setup before environment/database initialization in lifespan.

- Modify `backend/app/modules/sessions/streaming.py`
  - Logs Claude stream exceptions at the existing SSE catch boundary.

- Modify `backend/app/modules/conversions/service.py`
  - Logs conversion task exceptions at the existing task failure boundary.

- Modify `backend/app/integrations/mineru.py`
  - Logs MinerU request and response parsing failures with generic messages.

- Modify `backend/app/modules/conversions/office_pdf.py`
  - Logs local `.doc -> pdf` conversion failures with generic messages.

- Modify `backend/app/modules/uploads/service.py`
  - Logs unexpected upload item failures with generic messages while preserving current batch response behavior.

- Create `backend/tests/test_logging_config.py`
  - Covers console/file handlers, env overrides, and rotating file parameters.

- Modify existing tests:
  - `backend/tests/test_chat_api.py`
  - `backend/tests/test_conversion_tasks_api.py`
  - `backend/tests/test_mineru_integration.py`
  - `backend/tests/test_office_pdf.py`
  - `backend/tests/test_uploads_api.py`

## Task 1: Logging Configuration Module

**Files:**
- Create: `backend/app/core/logging.py`
- Test: `backend/tests/test_logging_config.py`

- [ ] **Step 1: Write failing tests for default logging setup**

Create `backend/tests/test_logging_config.py`:

```python
import logging
from logging.handlers import RotatingFileHandler


def test_configure_logging_adds_console_and_rotating_file_handlers(tmp_path, monkeypatch):
    from app.core import logging as app_logging

    log_file = tmp_path / "logs" / "app.log"
    monkeypatch.setenv("LOG_FILE", str(log_file))
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_MAX_BYTES", raising=False)
    monkeypatch.delenv("LOG_BACKUP_COUNT", raising=False)

    app_logging.configure_logging(force=True)

    root = logging.getLogger()
    assert root.level == logging.ERROR
    assert any(isinstance(handler, logging.StreamHandler) for handler in root.handlers)
    file_handlers = [
        handler for handler in root.handlers
        if isinstance(handler, RotatingFileHandler)
    ]
    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == str(log_file)
    assert file_handlers[0].maxBytes == 10 * 1024 * 1024
    assert file_handlers[0].backupCount == 5
    assert log_file.parent.exists()
```

- [ ] **Step 2: Write failing tests for env overrides**

Append to `backend/tests/test_logging_config.py`:

```python
def test_configure_logging_uses_environment_overrides(tmp_path, monkeypatch):
    from app.core import logging as app_logging

    log_file = tmp_path / "custom.log"
    monkeypatch.setenv("LOG_FILE", str(log_file))
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("LOG_MAX_BYTES", "12345")
    monkeypatch.setenv("LOG_BACKUP_COUNT", "7")

    app_logging.configure_logging(force=True)

    root = logging.getLogger()
    file_handler = next(
        handler for handler in root.handlers
        if isinstance(handler, RotatingFileHandler)
    )
    assert root.level == logging.WARNING
    assert file_handler.baseFilename == str(log_file)
    assert file_handler.maxBytes == 12345
    assert file_handler.backupCount == 7
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
pytest backend/tests/test_logging_config.py -q
```

Expected: FAIL because `app.core.logging` or `configure_logging` does not exist.

- [ ] **Step 4: Implement logging configuration**

Create `backend/app/core/logging.py`:

```python
"""统一错误日志配置。"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_LEVEL = "ERROR"
DEFAULT_LOG_FILE = "logs/app.log"
DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 5

_CONFIGURED = False


def _int_from_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _level_from_env() -> int:
    raw = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
    level = logging.getLevelName(raw)
    return level if isinstance(level, int) else logging.ERROR


def configure_logging(*, force: bool = False) -> None:
    """配置控制台和 rotating file 错误日志。"""
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    level = _level_from_env()
    log_file = Path(os.getenv("LOG_FILE", DEFAULT_LOG_FILE))
    max_bytes = _int_from_env("LOG_MAX_BYTES", DEFAULT_LOG_MAX_BYTES)
    backup_count = _int_from_env("LOG_BACKUP_COUNT", DEFAULT_LOG_BACKUP_COUNT)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    _CONFIGURED = True
```

- [ ] **Step 5: Run logging config tests**

Run:

```bash
pytest backend/tests/test_logging_config.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/logging.py backend/tests/test_logging_config.py
git commit -m "feat: 配置本地错误日志"
```

## Task 2: Initialize Logging During Startup

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_logging_config.py`

- [ ] **Step 1: Write failing test for startup initialization**

Append to `backend/tests/test_logging_config.py`:

```python
def test_lifespan_configures_logging_before_environment(monkeypatch):
    from importlib import reload
    from app import main

    calls: list[str] = []

    def fake_configure_logging():
        calls.append("logging")

    def fake_apply_environment():
        calls.append("environment")
        raise RuntimeError("stop after ordering check")

    monkeypatch.setattr(main.app_logging, "configure_logging", fake_configure_logging)
    monkeypatch.setattr(main.config, "apply_environment", fake_apply_environment)

    import pytest
    import asyncio

    async def run_lifespan():
        async with main._lifespan(None):
            pass

    with pytest.raises(RuntimeError, match="stop after ordering check"):
        asyncio.run(run_lifespan())

    assert calls == ["logging", "environment"]
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
pytest backend/tests/test_logging_config.py::test_lifespan_configures_logging_before_environment -q
```

Expected: FAIL because `main.app_logging` is not imported or `configure_logging` is not called.

- [ ] **Step 3: Initialize logging in lifespan**

Modify `backend/app/main.py`:

```python
from app.core import config
from app.core import logging as app_logging
```

Then update `_lifespan`:

```python
@asynccontextmanager
async def _lifespan(_: FastAPI):
    app_logging.configure_logging()
    config.apply_environment()
    await init_db()
    from app.modules.agents.workdir import ensure_all_agent_workdirs
    await ensure_all_agent_workdirs()
    yield
```

- [ ] **Step 4: Run startup logging test**

Run:

```bash
pytest backend/tests/test_logging_config.py::test_lifespan_configures_logging_before_environment -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_logging_config.py
git commit -m "feat: 启动时初始化错误日志"
```

## Task 3: Log Claude SSE Stream Exceptions

**Files:**
- Modify: `backend/app/modules/sessions/streaming.py`
- Test: `backend/tests/test_chat_api.py`

- [ ] **Step 1: Write failing test for Claude stream exception logging**

Append to `backend/tests/test_chat_api.py`:

```python
async def test_chat_stream_exception_is_logged(logged_in_client, monkeypatch, caplog):
    import logging
    import app.modules.sessions.streaming as streaming_mod

    c = logged_in_client
    sid = (await c.post("/api/sessions", json={})).json()["id"]

    async def fake_stream_chat(**kwargs):
        raise RuntimeError("claude exploded")

    monkeypatch.setattr(streaming_mod, "stream_chat", fake_stream_chat)

    with caplog.at_level(logging.ERROR, logger=streaming_mod.__name__):
        body_bytes = b""
        async with c.stream(
            "POST", f"/api/sessions/{sid}/chat", json={"prompt": "hello"}
        ) as response:
            async for chunk in response.aiter_bytes():
                body_bytes += chunk

    assert "claude exploded" in body_bytes.decode("utf-8")
    assert any(
        record.levelno == logging.ERROR
        and record.exc_info
        and "Claude stream failed" in record.getMessage()
        for record in caplog.records
    )
    assert "hello" not in caplog.text
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
pytest backend/tests/test_chat_api.py::test_chat_stream_exception_is_logged -q
```

Expected: FAIL because the exception is sent to SSE but not logged.

- [ ] **Step 3: Add logger and exception call**

Modify `backend/app/modules/sessions/streaming.py`:

```python
"""SSE 流式对话编排。"""

import asyncio
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
```

Then update the existing catch:

```python
        except Exception as exc:
            logger.exception("Claude stream failed")
            await queue.put({"type": "error", "message": str(exc)})
            await queue.put({"__internal": "done", "session_id": prior_session_id})
```

- [ ] **Step 4: Run test**

Run:

```bash
pytest backend/tests/test_chat_api.py::test_chat_stream_exception_is_logged -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/sessions/streaming.py backend/tests/test_chat_api.py
git commit -m "feat: 记录Claude流式异常"
```

## Task 4: Log Conversion Task Exceptions

**Files:**
- Modify: `backend/app/modules/conversions/service.py`
- Test: `backend/tests/test_conversion_tasks_api.py`

- [ ] **Step 1: Write failing test for conversion task logging**

Append to `backend/tests/test_conversion_tasks_api.py`:

```python
async def test_run_conversion_task_exception_is_logged(app_env, monkeypatch, caplog):
    import logging

    from app.db.session import async_session
    from app.models.conversion_task import ConversionTask
    from app.modules.conversions import service as conversions_service
    from app.modules.conversions.service import create_conversion_task, run_conversion_task

    ws = Path("user_workspaces/alice")
    (ws / "docs").mkdir(parents=True)
    (ws / "docs" / "broken.pdf").write_bytes(b"%PDF-1.4")

    async def fake_convert_source_to_markdown(*args, **kwargs):
        raise RuntimeError("conversion exploded")

    monkeypatch.setattr(
        conversions_service,
        "convert_source_to_markdown",
        fake_convert_source_to_markdown,
    )

    async with async_session() as session:
        task = await create_conversion_task(
            session,
            username="alice",
            workspace=ws,
            source_path="docs/broken.pdf",
        )
        task_id = task.id

    with caplog.at_level(logging.ERROR, logger=conversions_service.__name__):
        await run_conversion_task(task_id)

    async with async_session() as session:
        task = await session.get(ConversionTask, task_id)
        assert task.status == "failed"
        assert "conversion exploded" in task.error_message

    assert any(
        record.levelno == logging.ERROR
        and record.exc_info
        and "Conversion task failed" in record.getMessage()
        for record in caplog.records
    )
    assert "docs/broken.pdf" not in caplog.text
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
pytest backend/tests/test_conversion_tasks_api.py::test_run_conversion_task_exception_is_logged -q
```

Expected: FAIL because task failure is persisted but not logged.

- [ ] **Step 3: Add logger and exception call**

Modify imports in `backend/app/modules/conversions/service.py`:

```python
import logging
```

Add near constants:

```python
logger = logging.getLogger(__name__)
```

Update catch:

```python
        except Exception as exc:
            logger.exception("Conversion task failed")
            task.status = "failed"
            task.error_message = str(exc)
```

- [ ] **Step 4: Run test**

Run:

```bash
pytest backend/tests/test_conversion_tasks_api.py::test_run_conversion_task_exception_is_logged -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/conversions/service.py backend/tests/test_conversion_tasks_api.py
git commit -m "feat: 记录转换任务异常"
```

## Task 5: Log MinerU Integration Exceptions

**Files:**
- Modify: `backend/app/integrations/mineru.py`
- Test: `backend/tests/test_mineru_integration.py`

- [ ] **Step 1: Write failing test for MinerU HTTP errors**

Append to `backend/tests/test_mineru_integration.py`:

```python
async def test_mineru_non_2xx_is_logged(tmp_path, caplog):
    import logging

    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF")

    with caplog.at_level(logging.ERROR, logger=mineru.__name__):
        with pytest.raises(mineru.MineruConversionError):
            await mineru.convert_document_to_markdown(
                source_path=source_path,
                output_root=tmp_path / ".markdown" / "converted",
                api_url="https://mineru.example/convert",
                timeout_seconds=12.5,
                transport=_transport(httpx.Response(503, content=b"unavailable")),
            )

    assert any(
        record.levelno == logging.ERROR
        and "MinerU request returned non-success status" in record.getMessage()
        for record in caplog.records
    )
    assert str(source_path) not in caplog.text
```

- [ ] **Step 2: Write failing test for invalid zip logging**

Append to `backend/tests/test_mineru_integration.py`:

```python
async def test_mineru_invalid_zip_is_logged(tmp_path, caplog):
    import logging

    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF")

    with caplog.at_level(logging.ERROR, logger=mineru.__name__):
        with pytest.raises(mineru.MineruConversionError, match="invalid zip"):
            await mineru.convert_document_to_markdown(
                source_path=source_path,
                output_root=tmp_path / ".markdown" / "converted",
                api_url="https://mineru.example/convert",
                timeout_seconds=12.5,
                transport=_transport(httpx.Response(200, content=b"not a zip")),
            )

    assert any(
        record.levelno == logging.ERROR
        and record.exc_info
        and "MinerU returned invalid zip" in record.getMessage()
        for record in caplog.records
    )
    assert str(source_path) not in caplog.text
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
pytest backend/tests/test_mineru_integration.py::test_mineru_non_2xx_is_logged backend/tests/test_mineru_integration.py::test_mineru_invalid_zip_is_logged -q
```

Expected: FAIL because MinerU errors are not logged.

- [ ] **Step 4: Add logging to MinerU module**

Modify `backend/app/integrations/mineru.py`:

```python
import logging
```

Add near constants:

```python
logger = logging.getLogger(__name__)
```

Update `except httpx.HTTPError`:

```python
    except httpx.HTTPError as exc:
        logger.exception("MinerU request failed")
        raise MineruConversionError(f"MinerU request failed: {exc}") from exc
```

Update non-2xx branch:

```python
    if not 200 <= response.status_code < 300:
        logger.error("MinerU request returned non-success status")
        raise MineruConversionError(
            f"MinerU conversion failed with HTTP status {response.status_code}"
        )
```

Update invalid zip branch:

```python
    except BadZipFile as exc:
        logger.exception("MinerU returned invalid zip")
        raise MineruConversionError("invalid zip returned by MinerU") from exc
```

- [ ] **Step 5: Run MinerU tests**

Run:

```bash
pytest backend/tests/test_mineru_integration.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/integrations/mineru.py backend/tests/test_mineru_integration.py
git commit -m "feat: 记录MinerU转换异常"
```

## Task 6: Log Office PDF Conversion Exceptions

**Files:**
- Modify: `backend/app/modules/conversions/office_pdf.py`
- Test: `backend/tests/test_office_pdf.py`

- [ ] **Step 1: Write failing tests for Office PDF logging**

Append to `backend/tests/test_office_pdf.py`:

```python
async def test_temporary_pdf_for_doc_missing_converter_is_logged(tmp_path, monkeypatch, caplog):
    import logging

    from app.modules.conversions import office_pdf

    source = tmp_path / "legacy.doc"
    source.write_bytes(b"doc")
    monkeypatch.setattr(office_pdf.shutil, "which", lambda name: None)

    with caplog.at_level(logging.ERROR, logger=office_pdf.__name__):
        with pytest.raises(office_pdf.OfficePdfConversionError):
            async with office_pdf.temporary_pdf_for_doc(source):
                raise AssertionError("context should not be entered")

    assert any(
        record.levelno == logging.ERROR
        and "Office PDF converter is not available" in record.getMessage()
        for record in caplog.records
    )
    assert str(source) not in caplog.text
```

- [ ] **Step 2: Write failing test for LibreOffice execution failure logging**

Append to `backend/tests/test_office_pdf.py`:

```python
async def test_temporary_pdf_for_doc_process_failure_is_logged(tmp_path, monkeypatch, caplog):
    import logging

    from app.modules.conversions import office_pdf

    source = tmp_path / "legacy.doc"
    source.write_bytes(b"doc")

    class FakeProcess:
        returncode = 1

        async def communicate(self):
            return b"", b"failed"

    async def fake_create_subprocess_exec(*args, stdout=None, stderr=None):
        return FakeProcess()

    monkeypatch.setattr(office_pdf.shutil, "which", lambda name: "/usr/bin/libreoffice")
    monkeypatch.setattr(office_pdf.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with caplog.at_level(logging.ERROR, logger=office_pdf.__name__):
        with pytest.raises(office_pdf.OfficePdfConversionError):
            async with office_pdf.temporary_pdf_for_doc(source):
                raise AssertionError("context should not be entered")

    assert any(
        record.levelno == logging.ERROR
        and "Office PDF conversion process failed" in record.getMessage()
        for record in caplog.records
    )
    assert str(source) not in caplog.text
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
pytest backend/tests/test_office_pdf.py::test_temporary_pdf_for_doc_missing_converter_is_logged backend/tests/test_office_pdf.py::test_temporary_pdf_for_doc_process_failure_is_logged -q
```

Expected: FAIL because Office PDF conversion errors are not logged.

- [ ] **Step 4: Add logging to office_pdf module**

Modify `backend/app/modules/conversions/office_pdf.py`:

```python
import logging
```

Add near constants:

```python
logger = logging.getLogger(__name__)
```

Update `_office_converter_binary`:

```python
    if not binary:
        logger.error("Office PDF converter is not available")
        raise OfficePdfConversionError("DOC 转 PDF 失败，请确认 LibreOffice 已安装")
```

Update process failure:

```python
        if proc.returncode != 0:
            detail = (stderr or stdout).decode("utf-8", errors="ignore").strip()
            logger.error("Office PDF conversion process failed")
            raise OfficePdfConversionError(
                f"DOC 转 PDF 失败：{detail or 'LibreOffice 执行失败'}"
            )
```

Update timeout:

```python
        except TimeoutError as exc:
            proc.kill()
            await proc.communicate()
            logger.exception("Office PDF conversion timed out")
            raise OfficePdfConversionError("DOC 转 PDF 失败，LibreOffice 执行超时") from exc
```

Update no PDF branch:

```python
            if not candidates:
                logger.error("Office PDF conversion produced no PDF")
                raise OfficePdfConversionError("DOC 转 PDF 失败，未生成 PDF 文件")
```

- [ ] **Step 5: Run Office PDF tests**

Run:

```bash
pytest backend/tests/test_office_pdf.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/conversions/office_pdf.py backend/tests/test_office_pdf.py
git commit -m "feat: 记录Office转PDF异常"
```

## Task 7: Log Upload Item Exceptions

**Files:**
- Modify: `backend/app/modules/uploads/service.py`
- Test: `backend/tests/test_uploads_api.py`

- [ ] **Step 1: Write failing test for upload item exception logging**

Append to `backend/tests/test_uploads_api.py`:

```python
async def test_upload_item_exception_is_logged(logged_in_client, monkeypatch, caplog):
    import logging

    from app.modules.uploads import service as uploads_service

    def boom(path):
        raise RuntimeError("dedupe exploded")

    monkeypatch.setattr(uploads_service, "_dedupe_path", boom)

    with caplog.at_level(logging.ERROR, logger=uploads_service.__name__):
        res = await logged_in_client.post(
            "/api/uploads",
            files={"files": ("note.txt", b"hello", "text/plain")},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["summary"] == {"total": 1, "succeeded": 0, "failed": 1}
    assert "dedupe exploded" in body["items"][0]["error"]
    assert any(
        record.levelno == logging.ERROR
        and record.exc_info
        and "Upload item failed" in record.getMessage()
        for record in caplog.records
    )
    assert "note.txt" not in caplog.text
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
pytest backend/tests/test_uploads_api.py::test_upload_item_exception_is_logged -q
```

Expected: FAIL because upload item failures are not logged.

- [ ] **Step 3: Add logger and exception call**

Modify `backend/app/modules/uploads/service.py`:

```python
import logging
```

Add near constants:

```python
logger = logging.getLogger(__name__)
```

Update catch:

```python
        except Exception as exc:
            logger.exception("Upload item failed")
            items.append({
                "name": original,
                "path": None,
                "size": 0,
                "preview_path": None,
                "agent_path": None,
                "converted": False,
                "conversion_task_id": None,
                "status": "failed",
                "error": str(exc),
            })
```

- [ ] **Step 4: Run upload tests**

Run:

```bash
pytest backend/tests/test_uploads_api.py::test_upload_item_exception_is_logged backend/tests/test_uploads_api.py::test_oversized_upload_does_not_leave_partial_file -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/uploads/service.py backend/tests/test_uploads_api.py
git commit -m "feat: 记录上传异常"
```

## Task 8: Final Verification

**Files:**
- No source edits expected.

- [ ] **Step 1: Run focused logging test suite**

Run:

```bash
pytest \
  backend/tests/test_logging_config.py \
  backend/tests/test_chat_api.py::test_chat_stream_exception_is_logged \
  backend/tests/test_conversion_tasks_api.py::test_run_conversion_task_exception_is_logged \
  backend/tests/test_mineru_integration.py::test_mineru_non_2xx_is_logged \
  backend/tests/test_mineru_integration.py::test_mineru_invalid_zip_is_logged \
  backend/tests/test_office_pdf.py \
  backend/tests/test_uploads_api.py::test_upload_item_exception_is_logged \
  -q
```

Expected: PASS. If database-backed tests cannot run because local Postgres is unavailable, run the non-DB subset and record the exact database connection error in the final handoff.

- [ ] **Step 2: Verify no sensitive context was added to logs**

Run:

```bash
rg -n "logger\\.(exception|error|warning|info)" backend/app
```

Expected: new log calls use generic messages only:

```text
Claude stream failed
Conversion task failed
MinerU request failed
MinerU request returned non-success status
MinerU returned invalid zip
Office PDF converter is not available
Office PDF conversion process failed
Office PDF conversion timed out
Office PDF conversion produced no PDF
Upload item failed
```

- [ ] **Step 3: Verify status**

Run:

```bash
git status --short
```

Expected: no uncommitted files from the logging implementation. Pre-existing unrelated files such as `docker/Dockerfile.bak` may remain untracked and must not be committed.

## Self-Review

Spec coverage:

- Console and file logging: Task 1.
- Rotating log files: Task 1.
- Startup initialization: Task 2.
- Claude SSE exception boundary: Task 3.
- Conversion task exception boundary: Task 4.
- MinerU exception boundary: Task 5.
- Office PDF exception boundary: Task 6.
- Upload exception boundary: Task 7.
- No user/business context: enforced in every task test by checking sensitive sample values are absent from `caplog.text`.

Placeholder scan:

- This plan contains no placeholder markers, open-ended implementation steps, or unscoped “add tests” instructions.

Type consistency:

- `configure_logging(force: bool = False)` is defined in Task 1 and imported as `app_logging.configure_logging()` in Task 2.
- Logger names consistently use `logging.getLogger(__name__)`.
- All log assertions use standard pytest `caplog`.
