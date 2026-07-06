import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import select


async def _create_upload_task(logged_in_client, filename="a.txt", relative_path="a.txt", size=0):
    payload = {
        "target_dir": "docs",
        "items": [{"filename": filename, "relative_path": relative_path, "size": size}],
    }
    r = await logged_in_client.post("/api/upload-tasks", json=payload)
    assert r.status_code == 200
    return r.json()[0]


async def test_create_upload_tasks_persists_queued_items(logged_in_client):
    payload = {
        "target_dir": "docs",
        "items": [
            {"filename": "a.txt", "relative_path": "a.txt", "size": 12},
            {"filename": "b.pdf", "relative_path": "nested/b.pdf", "size": 34},
        ],
    }

    r = await logged_in_client.post("/api/upload-tasks", json=payload)

    assert r.status_code == 200
    data = r.json()
    assert [item["filename"] for item in data] == ["a.txt", "b.pdf"]
    assert [item["status"] for item in data] == ["queued", "queued"]
    assert [item["progress"] for item in data] == [0, 0]
    assert data[0]["target_dir"] == "docs"
    assert data[0]["relative_path"] == "a.txt"
    assert data[0]["saved_path"] == "docs/a.txt"
    assert data[1]["saved_path"] == "docs/nested/b.pdf"


async def test_create_upload_tasks_dedupes_duplicate_paths_in_same_batch(logged_in_client):
    payload = {
        "target_dir": "docs",
        "items": [
            {"filename": "a.txt", "relative_path": "a.txt", "size": 12},
            {"filename": "a.txt", "relative_path": "a.txt", "size": 34},
        ],
    }

    r = await logged_in_client.post("/api/upload-tasks", json=payload)

    assert r.status_code == 200
    data = r.json()
    assert [item["saved_path"] for item in data] == ["docs/a.txt", "docs/a (1).txt"]


async def test_create_upload_tasks_rejects_absolute_target_dir(logged_in_client):
    payload = {
        "target_dir": "/docs",
        "items": [
            {"filename": "a.txt", "relative_path": "a.txt", "size": 12},
        ],
    }

    r = await logged_in_client.post("/api/upload-tasks", json=payload)

    assert r.status_code == 400


async def test_upload_task_file_saves_file_and_marks_success(logged_in_client):
    from app.core.config import user_workspace

    task = await _create_upload_task(logged_in_client)

    r = await logged_in_client.post(
        f"/api/upload-tasks/{task['id']}/file",
        files={"file": ("a.txt", b"hello upload task", "text/plain")},
    )

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "succeeded"
    assert data["progress"] == 100
    assert data["size"] == len(b"hello upload task")
    assert data["saved_path"] == "docs/a.txt"
    target = user_workspace("alice") / data["saved_path"]
    assert target.read_bytes() == b"hello upload task"


async def test_upload_progress_updates_running_task(logged_in_client):
    task = await _create_upload_task(logged_in_client)

    r = await logged_in_client.patch(
        f"/api/upload-tasks/{task['id']}/progress",
        json={"progress": 50},
    )

    assert r.status_code == 409


async def test_abandon_marks_unfinished_upload_tasks_failed(logged_in_client):
    from app.db.session import async_session
    from app.models import UploadTask

    queued = await _create_upload_task(logged_in_client, filename="queued.txt", relative_path="queued.txt")
    running = await _create_upload_task(logged_in_client, filename="running.txt", relative_path="running.txt")
    succeeded = await _create_upload_task(logged_in_client, filename="done.txt", relative_path="done.txt")

    async with async_session() as session:
        running_task = await session.get(UploadTask, running["id"])
        succeeded_task = await session.get(UploadTask, succeeded["id"])
        running_task.status = "running"
        succeeded_task.status = "succeeded"
        await session.commit()

    r = await logged_in_client.post("/api/upload-tasks/abandon", json={"ids": [queued["id"], running["id"], succeeded["id"]]})

    assert r.status_code == 200
    async with async_session() as session:
        result = await session.execute(
            select(UploadTask).where(UploadTask.id.in_([queued["id"], running["id"], succeeded["id"]]))
        )
        tasks = {task.id: task for task in result.scalars().all()}
    assert tasks[queued["id"]].status == "failed"
    assert tasks[running["id"]].status == "failed"
    assert tasks[succeeded["id"]].status == "succeeded"
    assert tasks[queued["id"]].error_message == "页面刷新导致上传中断，请重新上传"
    assert tasks[running["id"]].error_message == "页面刷新导致上传中断，请重新上传"


async def test_abandon_can_use_explicit_upload_failure_message(logged_in_client):
    from app.db.session import async_session
    from app.models import UploadTask

    queued = await _create_upload_task(logged_in_client, filename="failed.txt", relative_path="failed.txt")

    r = await logged_in_client.post(
        "/api/upload-tasks/abandon",
        json={"ids": [queued["id"]], "error_message": "上传失败，请重新上传"},
    )

    assert r.status_code == 200
    async with async_session() as session:
        saved = await session.get(UploadTask, queued["id"])
    assert saved.status == "failed"
    assert saved.error_message == "上传失败，请重新上传"


async def test_upload_success_creates_conversion_task_for_convertible_file(logged_in_client, monkeypatch):
    from app.modules.uploads import tasks as upload_task_service

    scheduled = []

    def fake_schedule(background_tasks, task_id):
        scheduled.append(task_id)

    monkeypatch.setattr(upload_task_service, "schedule_conversion_task", fake_schedule)
    task = await _create_upload_task(logged_in_client, filename="report.pdf", relative_path="report.pdf")

    r = await logged_in_client.post(
        f"/api/upload-tasks/{task['id']}/file",
        files={"file": ("report.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert r.status_code == 200
    tasks = await logged_in_client.get("/api/conversion-tasks")
    assert tasks.status_code == 200
    body = tasks.json()
    assert body[0]["source_path"] == "docs/report.pdf"
    assert scheduled == [body[0]["id"]]


async def test_concurrent_upload_claim_allows_only_one_running(logged_in_client):
    """同一个任务并发提交时，只有一个请求能成功领取并落盘。"""
    from app.core.config import user_workspace
    from app.db.session import async_session
    from app.models import UploadTask
    from app.modules.uploads import tasks as upload_task_service

    task = await _create_upload_task(logged_in_client, filename="one.txt", relative_path="one.txt")
    workspace = user_workspace("alice")
    tmp_prefix = workspace / "docs" / ".one.txt.uploading"

    class BlockingUpload:
        def __init__(self, payload: bytes):
            self.payload = payload
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.sent = False
            self.closed = False

        async def read(self, size):
            if self.sent:
                return b""
            self.started.set()
            await asyncio.wait_for(self.release.wait(), timeout=2)
            self.sent = True
            return self.payload

        async def close(self):
            self.closed = True

    first_upload = BlockingUpload(b"first payload")
    async with async_session() as first_session:
        first_task = asyncio.create_task(
            upload_task_service.save_upload_task_file(
                first_session,
                username="alice",
                workspace=workspace,
                task_id=task["id"],
                file=first_upload,
            )
        )
        await asyncio.wait_for(first_upload.started.wait(), timeout=2)

        second_response = await logged_in_client.post(
            f"/api/upload-tasks/{task['id']}/file",
            files={"file": ("one.txt", b"second payload", "text/plain")},
        )
        assert second_response.status_code == 409

        first_upload.release.set()
        first_result = await first_task
    assert first_result.status == "succeeded"

    target = workspace / "docs/one.txt"
    assert target.read_bytes() == b"first payload"
    assert not tmp_prefix.exists()

    async with async_session() as session:
        saved = await session.get(UploadTask, task["id"])
    assert saved.status == "succeeded"


@pytest.mark.parametrize(
    "raised",
    [
        RuntimeError("conversion backend unavailable"),
        HTTPException(status_code=500, detail="conversion failed"),
    ],
)
async def test_upload_success_ignores_conversion_task_failures(logged_in_client, monkeypatch, raised):
    from app.db.session import async_session
    from app.models import UploadTask
    from app.modules.uploads import tasks as upload_task_service

    async def failing_create_conversion_task(*args, **kwargs):
        raise raised

    monkeypatch.setattr(upload_task_service, "create_conversion_task", failing_create_conversion_task)
    task = await _create_upload_task(logged_in_client, filename="report.pdf", relative_path="report.pdf")

    r = await logged_in_client.post(
        f"/api/upload-tasks/{task['id']}/file",
        files={"file": ("report.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert r.status_code == 200
    assert r.json()["status"] == "succeeded"
    async with async_session() as session:
        saved = await session.get(UploadTask, task["id"])
    assert saved.status == "succeeded"


async def test_abandoned_running_upload_is_not_marked_succeeded_or_converted(logged_in_client, monkeypatch):
    from app.core.config import user_workspace
    from app.db.session import async_session
    from app.models import UploadTask
    from app.modules.uploads import tasks as upload_task_service
    from app.schemas import UploadTaskAbandonIn

    class BlockingUpload:
        def __init__(self):
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.sent = False
            self.closed = False

        async def read(self, size):
            if self.sent:
                return b""
            self.started.set()
            await asyncio.wait_for(self.release.wait(), timeout=2)
            self.sent = True
            return b"%PDF-1.4 abandoned upload"

        async def close(self):
            self.closed = True

    created_conversions = []

    async def fake_create_conversion_task(*args, **kwargs):
        created_conversions.append(kwargs["source_path"])

    monkeypatch.setattr(upload_task_service, "create_conversion_task", fake_create_conversion_task)
    task = await _create_upload_task(logged_in_client, filename="abandoned.pdf", relative_path="abandoned.pdf")
    upload = BlockingUpload()
    workspace = user_workspace("alice")

    async with async_session() as upload_session:
        upload_coro = asyncio.create_task(
            upload_task_service.save_upload_task_file(
                upload_session,
                username="alice",
                workspace=workspace,
                task_id=task["id"],
                file=upload,
            )
        )
        await asyncio.wait_for(upload.started.wait(), timeout=2)
        async with async_session() as abandon_session:
            await upload_task_service.abandon_upload_tasks(
                abandon_session,
                username="alice",
                data=UploadTaskAbandonIn(ids=[task["id"]]),
            )
        upload.release.set()
        await upload_coro

    target = workspace / "docs/abandoned.pdf"
    async with async_session() as session:
        saved = await session.get(UploadTask, task["id"])
    assert saved.status == "failed"
    assert not target.exists()
    assert created_conversions == []


async def test_abandoned_upload_does_not_delete_existing_target_file(logged_in_client, monkeypatch):
    """上传期间同路径出现正常文件时，abandon 后不能覆盖或删除该文件。"""
    from app.core.config import user_workspace
    from app.db.session import async_session
    from app.models import UploadTask
    from app.modules.uploads import tasks as upload_task_service
    from app.schemas import UploadTaskAbandonIn

    class BlockingUpload:
        def __init__(self):
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.sent = False

        async def read(self, size):
            if self.sent:
                return b""
            self.started.set()
            await asyncio.wait_for(self.release.wait(), timeout=2)
            self.sent = True
            return b"uploaded bytes must not survive"

        async def close(self):
            pass

    task = await _create_upload_task(logged_in_client, filename="race.txt", relative_path="race.txt")
    workspace = user_workspace("alice")
    target = workspace / "docs/race.txt"
    normal_content = b"normal file created during upload"
    upload = BlockingUpload()

    async with async_session() as upload_session:
        upload_coro = asyncio.create_task(
            upload_task_service.save_upload_task_file(
                upload_session,
                username="alice",
                workspace=workspace,
                task_id=task["id"],
                file=upload,
            )
        )
        await asyncio.wait_for(upload.started.wait(), timeout=2)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(normal_content)
        async with async_session() as abandon_session:
            await upload_task_service.abandon_upload_tasks(
                abandon_session,
                username="alice",
                data=UploadTaskAbandonIn(ids=[task["id"]]),
            )
        upload.release.set()
        await upload_coro

    async with async_session() as session:
        saved = await session.get(UploadTask, task["id"])
    assert saved.status == "failed"
    assert target.read_bytes() == normal_content


async def test_create_upload_tasks_requires_items(logged_in_client):
    r = await logged_in_client.post("/api/upload-tasks", json={"target_dir": "docs"})

    assert r.status_code == 422


async def test_create_upload_tasks_rejects_negative_size(logged_in_client):
    payload = {
        "target_dir": "docs",
        "items": [
            {"filename": "a.txt", "relative_path": "a.txt", "size": -1},
        ],
    }

    r = await logged_in_client.post("/api/upload-tasks", json=payload)

    assert r.status_code == 422


async def test_create_upload_tasks_rejects_symlink_escape(logged_in_client, tmp_path):
    workspace = tmp_path / "user_workspaces" / "alice"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (workspace / "linked").symlink_to(outside_dir, target_is_directory=True)
    payload = {
        "target_dir": "",
        "items": [
            {"filename": "a.txt", "relative_path": "linked/a.txt", "size": 12},
        ],
    }

    r = await logged_in_client.post("/api/upload-tasks", json=payload)

    assert r.status_code == 400
