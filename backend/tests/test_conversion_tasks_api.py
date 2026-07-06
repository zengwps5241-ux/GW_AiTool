from pathlib import Path
from sqlalchemy import select

import pytest


async def test_conversion_tasks_table_exists_and_stale_running_tasks_requeue(app_env):
    from app.db.session import async_session
    from app.models.conversion_task import ConversionTask
    from app.db import migrations

    async with async_session() as session:
        task = ConversionTask(
            username="alice",
            source_path="docs/report.pdf",
            source_name="report.pdf",
            status="running",
        )
        session.add(task)
        await session.commit()
        task_id = task.id

    await migrations.init_db()

    async with async_session() as session:
        task = await session.get(ConversionTask, task_id)
        assert task is not None
        assert task.status == "queued"
        assert task.error_message is None


async def test_list_conversion_tasks_for_current_user(logged_in_client):
    from app.db.session import async_session
    from app.models.conversion_task import ConversionTask

    async with async_session() as session:
        session.add(ConversionTask(
            username="alice",
            source_path="docs/report.pdf",
            source_name="report.pdf",
            status="queued",
        ))
        session.add(ConversionTask(
            username="bob",
            source_path="docs/other.pdf",
            source_name="other.pdf",
            status="queued",
        ))
        await session.commit()

    res = await logged_in_client.get("/api/conversion-tasks")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["source_path"] == "docs/report.pdf"
    assert body[0]["status"] == "queued"


async def test_retry_conversion_task_creates_new_queued_task(logged_in_client):
    ws = Path("user_workspaces/alice")
    (ws / "docs").mkdir(parents=True)
    (ws / "docs" / "report.pdf").write_bytes(b"%PDF-1.4")

    res = await logged_in_client.post(
        "/api/conversion-tasks/retry",
        json={"source_path": "docs/report.pdf"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["source_path"] == "docs/report.pdf"
    assert body["source_name"] == "report.pdf"
    assert body["status"] == "queued"


async def test_retry_conversion_task_schedules_background_task(logged_in_client, monkeypatch):
    from app.api.routes import conversion_tasks as routes

    scheduled = []

    def fake_schedule(background_tasks, task_id):
        scheduled.append(task_id)

    monkeypatch.setattr(routes, "schedule_conversion_task", fake_schedule)

    ws = Path("user_workspaces/alice")
    (ws / "docs").mkdir(parents=True)
    (ws / "docs" / "report.pdf").write_bytes(b"%PDF-1.4")

    res = await logged_in_client.post(
        "/api/conversion-tasks/retry",
        json={"source_path": "docs/report.pdf"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "queued"
    assert len(scheduled) == 1
    assert scheduled[0] == body["id"]


@pytest.mark.parametrize("status", ["queued", "running"])
async def test_retry_conversion_task_rejects_duplicate_pending_task(logged_in_client, status):
    from app.db.session import async_session
    from app.models.conversion_task import ConversionTask

    ws = Path("user_workspaces/alice")
    (ws / "docs").mkdir(parents=True)
    (ws / "docs" / "report.pdf").write_bytes(b"%PDF-1.4")

    async with async_session() as session:
        session.add(
            ConversionTask(
                username="alice",
                source_path="docs/report.pdf",
                source_name="report.pdf",
                status=status,
            )
        )
        await session.commit()

    res = await logged_in_client.post(
        "/api/conversion-tasks/retry",
        json={"source_path": "docs/report.pdf"},
    )

    assert res.status_code == 409
    assert res.json()["detail"] == "已存在转换任务"


async def test_run_conversion_task_success_writes_mapping(app_env, monkeypatch):
    from app.db.session import async_session
    from app.integrations.mineru import MineruMarkdownResult
    from app.modules.conversions.service import create_conversion_task, run_conversion_task

    ws = Path("user_workspaces/alice")
    (ws / "docs").mkdir(parents=True)
    (ws / "docs" / "report.pdf").write_bytes(b"%PDF-1.4")

    async def fake_convert_document_to_markdown(
        source_path, output_root, api_url, timeout_seconds, max_concurrent_requests
    ):
        md = output_root / "hybrid_auto" / "report.md"
        md.parent.mkdir(parents=True)
        md.write_text("# Report\n", encoding="utf-8")
        return MineruMarkdownResult(
            markdown_path=md,
            markdown_rel_path=md.relative_to(ws.resolve()).as_posix(),
            asset_dir=None,
            extract_dir=md.parent,
        )

    from app.modules.conversions import service as conversions_service
    monkeypatch.setattr(
        conversions_service,
        "convert_document_to_markdown",
        fake_convert_document_to_markdown,
    )

    async with async_session() as session:
        task = await create_conversion_task(
            session,
            username="alice",
            workspace=ws,
            source_path="docs/report.pdf",
        )
        task_id = task.id

    await run_conversion_task(task_id)

    async with async_session() as session:
        task = await session.get(type(task), task_id)
        assert task.status == "succeeded"
        assert task.markdown_path.endswith("report.md")


async def test_run_conversion_task_success_replaces_old_markdown_by_index(
    app_env, monkeypatch
):
    from app.db.session import async_session
    from app.integrations.mineru import MineruMarkdownResult
    from app.modules.conversions.service import create_conversion_task, run_conversion_task
    from app.modules.workspace.markdown_index import add_markdown_mapping, resolve_preview_path

    ws = Path("user_workspaces/alice")
    (ws / "docs").mkdir(parents=True)
    (ws / "docs" / "report.pdf").write_bytes(b"%PDF-1.4")
    old_dir = ws / ".markdown" / "report"
    old_dir.mkdir(parents=True)
    (old_dir / "old.md").write_text("# Old\n", encoding="utf-8")
    add_markdown_mapping(
        ws,
        source_path="docs/report.pdf",
        source_name="report.pdf",
        markdown_path=".markdown/report/old.md",
        extract_dir=".markdown/report",
    )

    async def fake_convert_document_to_markdown(
        source_path, output_root, api_url, timeout_seconds, max_concurrent_requests
    ):
        # 重新转换先写入临时目录，成功后服务层再替换旧 Markdown 目录。
        assert output_root != old_dir.resolve()
        md = output_root / "hybrid_auto" / "report.md"
        md.parent.mkdir(parents=True)
        md.write_text("# New\n", encoding="utf-8")
        return MineruMarkdownResult(
            markdown_path=md,
            markdown_rel_path=md.relative_to(ws.resolve()).as_posix(),
            asset_dir=None,
            extract_dir=output_root,
        )

    from app.modules.conversions import service as conversions_service
    monkeypatch.setattr(
        conversions_service,
        "convert_document_to_markdown",
        fake_convert_document_to_markdown,
    )

    async with async_session() as session:
        task = await create_conversion_task(
            session,
            username="alice",
            workspace=ws,
            source_path="docs/report.pdf",
        )
        task_id = task.id

    await run_conversion_task(task_id)

    assert not (ws / ".markdown" / "report" / "old.md").exists()
    assert (ws / ".markdown" / "report" / "hybrid_auto" / "report.md").read_text(
        encoding="utf-8"
    ) == "# New\n"
    assert resolve_preview_path(ws, "docs/report.pdf") == (
        ".markdown/report/hybrid_auto/report.md"
    )

    async with async_session() as session:
        task = await session.get(type(task), task_id)
        assert task.status == "succeeded"
        assert task.markdown_path == ".markdown/report/hybrid_auto/report.md"


async def test_enqueue_pending_conversion_tasks_restores_queued_tasks(app_env, monkeypatch):
    from app.db.session import async_session
    from app.models.conversion_task import ConversionTask
    from app.modules.conversions import service as conversions_service

    scheduled: list[int] = []

    async def fake_enqueue_conversion_task(task_id):
        scheduled.append(task_id)

    monkeypatch.setattr(
        conversions_service,
        "enqueue_conversion_task",
        fake_enqueue_conversion_task,
    )

    async with async_session() as session:
        queued = ConversionTask(
            username="alice",
            source_path="docs/queued.pdf",
            source_name="queued.pdf",
            status="queued",
        )
        succeeded = ConversionTask(
            username="alice",
            source_path="docs/succeeded.pdf",
            source_name="succeeded.pdf",
            status="succeeded",
        )
        session.add_all([queued, succeeded])
        await session.commit()
        queued_id = queued.id

    await conversions_service.enqueue_pending_conversion_tasks()

    assert scheduled == [queued_id]


async def test_start_conversion_task_dispatcher_uses_configured_worker_count(app_env, monkeypatch):
    from app.modules.conversions import service as conversions_service

    monkeypatch.setattr(conversions_service.get_settings(), "mineru_max_concurrent_requests", 3)
    await conversions_service.start_conversion_task_dispatcher()

    try:
        assert len(conversions_service._dispatcher_workers) == 3
    finally:
        await conversions_service.stop_conversion_task_dispatcher()


async def test_run_conversion_task_doc_uses_temporary_pdf_and_maps_source(
    app_env, monkeypatch
):
    from contextlib import asynccontextmanager

    from app.db.session import async_session
    from app.integrations.mineru import MineruMarkdownResult
    from app.modules.conversions.service import create_conversion_task, run_conversion_task
    from app.modules.workspace.markdown_index import resolve_preview_path

    ws = Path("user_workspaces/alice")
    (ws / "docs").mkdir(parents=True)
    source_doc = ws / "docs" / "legacy.doc"
    source_doc.write_bytes(b"legacy doc bytes")
    temp_pdf = ws / "docs" / "legacy.tmp.pdf"
    seen: dict[str, Path] = {}

    @asynccontextmanager
    async def fake_temporary_pdf_for_doc(source_path):
        seen["doc_source"] = source_path
        temp_pdf.write_bytes(b"%PDF-1.4")
        try:
            yield temp_pdf
        finally:
            temp_pdf.unlink(missing_ok=True)

    async def fake_convert_document_to_markdown(
        source_path, output_root, api_url, timeout_seconds, max_concurrent_requests
    ):
        seen["mineru_source"] = source_path
        md = output_root / "hybrid_auto" / "legacy.md"
        md.parent.mkdir(parents=True)
        md.write_text("# Legacy\n", encoding="utf-8")
        return MineruMarkdownResult(
            markdown_path=md,
            markdown_rel_path=md.relative_to(ws.resolve()).as_posix(),
            asset_dir=None,
            extract_dir=md.parent,
        )

    from app.modules.conversions import service as conversions_service

    monkeypatch.setattr(
        conversions_service,
        "temporary_pdf_for_doc",
        fake_temporary_pdf_for_doc,
    )
    monkeypatch.setattr(
        conversions_service,
        "convert_document_to_markdown",
        fake_convert_document_to_markdown,
    )

    async with async_session() as session:
        task = await create_conversion_task(
            session,
            username="alice",
            workspace=ws,
            source_path="docs/legacy.doc",
        )
        task_id = task.id

    await run_conversion_task(task_id)

    assert seen["doc_source"] == source_doc.resolve()
    assert seen["mineru_source"] == temp_pdf
    assert not temp_pdf.exists()
    assert resolve_preview_path(ws, "docs/legacy.doc").endswith("legacy.md")

    async with async_session() as session:
        task = await session.get(type(task), task_id)
        assert task.status == "succeeded"
        assert task.source_path == "docs/legacy.doc"
        assert task.markdown_path.endswith("legacy.md")


async def test_convert_source_to_markdown_doc_uses_temporary_pdf(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager

    from app.integrations.mineru import MineruMarkdownResult
    from app.modules.conversions import service as conversions_service

    source_doc = tmp_path / "legacy.doc"
    source_doc.write_bytes(b"legacy doc bytes")
    temp_pdf = tmp_path / "legacy.pdf"
    output_root = tmp_path / ".markdown" / "legacy"
    seen: dict[str, Path] = {}

    @asynccontextmanager
    async def fake_temporary_pdf_for_doc(source_path):
        seen["doc_source"] = source_path
        temp_pdf.write_bytes(b"%PDF")
        try:
            yield temp_pdf
        finally:
            temp_pdf.unlink(missing_ok=True)

    async def fake_convert_document_to_markdown(
        source_path, output_root, api_url, timeout_seconds, max_concurrent_requests
    ):
        seen["mineru_source"] = source_path
        md = output_root / "hybrid_auto" / "legacy.md"
        md.parent.mkdir(parents=True)
        md.write_text("# Legacy\n", encoding="utf-8")
        return MineruMarkdownResult(
            markdown_path=md,
            markdown_rel_path=".markdown/legacy/hybrid_auto/legacy.md",
            asset_dir=None,
            extract_dir=output_root,
        )

    monkeypatch.setattr(
        conversions_service,
        "temporary_pdf_for_doc",
        fake_temporary_pdf_for_doc,
    )
    monkeypatch.setattr(
        conversions_service,
        "convert_document_to_markdown",
        fake_convert_document_to_markdown,
    )

    result = await conversions_service.convert_source_to_markdown(
        source_doc,
        output_root,
        api_url="https://mineru.example/convert",
        timeout_seconds=10,
        max_concurrent_requests=2,
    )

    assert seen["doc_source"] == source_doc
    assert seen["mineru_source"] == temp_pdf
    assert result.markdown_path.name == "legacy.md"
    assert not temp_pdf.exists()


async def test_run_conversion_task_exception_is_logged(tmp_path, monkeypatch, caplog):
    import logging
    from types import SimpleNamespace

    from app.modules.conversions import service as conversions_service
    from app.modules.conversions.service import run_conversion_task

    ws = tmp_path / "user_workspaces" / "alice"
    (ws / "docs").mkdir(parents=True)
    (ws / "docs" / "broken.pdf").write_bytes(b"%PDF-1.4")
    task = SimpleNamespace(
        id=1,
        username="alice",
        source_path="docs/broken.pdf",
        source_name="broken.pdf",
        status="queued",
        started_at=None,
        finished_at=None,
        error_message=None,
        markdown_path=None,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, statement):
            task.status = "running"
            task.started_at = object()
            task.finished_at = None
            task.error_message = None

            class Result:
                def scalar_one_or_none(self):
                    return task.id

            return Result()

        async def get(self, model, task_id):
            return task

        async def commit(self):
            pass

    async def fake_convert_source_to_markdown(*args, **kwargs):
        raise RuntimeError("conversion exploded")

    monkeypatch.setattr(conversions_service, "async_session", lambda: FakeSession())
    monkeypatch.setattr(conversions_service, "user_workspace", lambda username: ws)
    monkeypatch.setattr(
        conversions_service,
        "convert_source_to_markdown",
        fake_convert_source_to_markdown,
    )

    with caplog.at_level(logging.ERROR, logger=conversions_service.__name__):
        await run_conversion_task(task.id)

    assert task.status == "failed"
    assert "conversion exploded" in task.error_message

    assert any(
        record.levelno == logging.ERROR
        and record.exc_info
        and "Conversion task failed" in record.getMessage()
        for record in caplog.records
    )
    assert "docs/broken.pdf" not in caplog.text


async def test_list_conversion_tasks_pagination(logged_in_client):
    from app.db.session import async_session
    from app.models.conversion_task import ConversionTask

    async with async_session() as session:
        for i in range(5):
            session.add(ConversionTask(
                username="alice",
                source_path=f"docs/file{i}.pdf",
                source_name=f"file{i}.pdf",
                status="queued",
            ))
        await session.commit()

    res = await logged_in_client.get("/api/conversion-tasks?limit=2&offset=0")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert body[0]["source_name"] == "file4.pdf"
    assert body[1]["source_name"] == "file3.pdf"

    res = await logged_in_client.get("/api/conversion-tasks?limit=2&offset=2")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert body[0]["source_name"] == "file2.pdf"
    assert body[1]["source_name"] == "file1.pdf"

    res = await logged_in_client.get("/api/conversion-tasks?limit=2&offset=4")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["source_name"] == "file0.pdf"
