"""文件上传 API 测试。"""

from io import BytesIO
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


async def test_upload_requires_auth(client):
    """未登录用户不能上传文件。"""
    files = {"files": ("a.txt", b"hello", "text/plain")}
    r = await client.post("/api/uploads", files=files)
    assert r.status_code == 401


async def test_upload_single_file(logged_in_client):
    """上传单文件,返回元数据并落盘到用户工作区。"""
    c = logged_in_client
    files = {"files": ("note.txt", b"hello world", "text/plain")}
    r = await c.post("/api/uploads", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["succeeded"] == 1
    item = body["items"][0]
    assert item["name"] == "note.txt"
    assert item["size"] == len(b"hello world")
    assert item["path"] == "note.txt"
    assert item["preview_path"] == item["path"]
    assert item["agent_path"] == item["path"]
    assert item["converted"] is False

    # 验证文件实际落盘到用户工作区
    from app.core.config import user_workspace
    workspace = user_workspace("alice")
    target = workspace / item["path"]
    assert target.exists()
    assert target.read_bytes() == b"hello world"


async def test_upload_txt_returns_unconverted_paths(logged_in_client, monkeypatch):
    """txt 文件不触发转换,预览和 agent 路径保持源文件路径。"""
    from app.modules.uploads import service as uploads_service

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("txt upload must not call MinerU")

    monkeypatch.setattr(
        uploads_service,
        "convert_document_to_markdown",
        fail_if_called,
    )
    c = logged_in_client
    files = {"files": ("note.txt", b"plain text", "text/plain")}

    r = await c.post("/api/uploads", files=files)

    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["path"] == "note.txt"
    assert item["preview_path"] == item["path"]
    assert item["agent_path"] == item["path"]
    assert item["converted"] is False


async def test_upload_pdf_creates_queued_conversion_task(logged_in_client, monkeypatch):
    from app.modules.conversions import service as conversions_service

    async def noop_run_conversion_task(task_id):
        pass

    monkeypatch.setattr(
        conversions_service,
        "run_conversion_task",
        noop_run_conversion_task,
    )

    files = {"files": ("report.pdf", b"%PDF-1.4", "application/pdf")}
    res = await logged_in_client.post("/api/uploads", files=files)

    assert res.status_code == 200
    item = res.json()["items"][0]
    assert item["status"] == "success"
    assert item["converted"] is False
    assert item["conversion_task_id"] is not None

    tasks = await logged_in_client.get("/api/conversion-tasks")
    assert tasks.status_code == 200
    body = tasks.json()
    assert body[0]["source_path"] == item["path"]
    assert body[0]["status"] == "queued"


async def test_upload_multi_pdf_creates_queued_tasks(logged_in_client, monkeypatch):
    from app.modules.conversions import service as conversions_service

    async def noop_run_conversion_task(task_id):
        pass

    monkeypatch.setattr(
        conversions_service,
        "run_conversion_task",
        noop_run_conversion_task,
    )

    files = [
        ("files", ("first.pdf", b"%PDF-1.7 first", "application/pdf")),
        ("files", ("second.pdf", b"%PDF-1.7 second", "application/pdf")),
    ]
    r = await logged_in_client.post("/api/uploads", files=files)

    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["succeeded"] == 2
    assert body["summary"]["failed"] == 0
    for item in body["items"]:
        assert item["converted"] is False
        assert item["conversion_task_id"] is not None

    tasks = await logged_in_client.get("/api/conversion-tasks")
    assert tasks.status_code == 200
    assert len(tasks.json()) == 2


async def test_upload_multiple_files(logged_in_client):
    """同时上传多个文件。"""
    c = logged_in_client
    files = [
        ("files", ("a.txt", b"AAA", "text/plain")),
        ("files", ("b.txt", b"BBB", "text/plain")),
    ]
    r = await c.post("/api/uploads", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["total"] == 2
    assert body["summary"]["succeeded"] == 2
    # 路径互不相同
    assert body["items"][0]["path"] != body["items"][1]["path"]


async def test_upload_sanitizes_filename(logged_in_client):
    """危险路径片段和字符被剥离,保留中文。"""
    c = logged_in_client
    # 试图通过路径片段写入到工作区外
    files = {"files": ("../../etc/secret.txt", b"data", "text/plain")}
    r = await c.post("/api/uploads", files=files)
    assert r.status_code == 200
    body = r.json()
    item = body["items"][0]
    # 路径分隔符被剥离,只保留文件名部分
    assert "../" not in item["path"]
    assert item["name"] == "secret.txt"


async def test_upload_preserves_chinese_filename(logged_in_client):
    """中文文件名不会被错误清洗。"""
    c = logged_in_client
    files = {"files": ("会议纪要.md", "# 标题\n".encode("utf-8"), "text/markdown")}
    r = await c.post("/api/uploads", files=files)
    assert r.status_code == 200
    body = r.json()
    item = body["items"][0]
    assert item["name"] == "会议纪要.md"
    assert "会议纪要.md" in item["path"]


async def test_upload_to_target_dir_preserves_relative_path(logged_in_client):
    files = [
        ("files", ("纪要.md", b"# hi", "text/markdown")),
    ]
    data = {
        "target_dir": "客户A",
        "relative_paths": json.dumps(["项目资料/会议/纪要.md"]),
    }

    res = await logged_in_client.post("/api/uploads", data=data, files=files)

    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["succeeded"] == 1
    assert body["summary"]["failed"] == 0
    item = body["items"][0]
    assert item["status"] == "success"
    assert item["path"] == "客户A/项目资料/会议/纪要.md"
    assert Path("user_workspaces/alice/客户A/项目资料/会议/纪要.md").read_text(encoding="utf-8") == "# hi"


async def test_upload_partial_failure_keeps_successful_files(logged_in_client):
    files = [
        ("files", ("ok.txt", b"ok", "text/plain")),
        ("files", ("bad.txt", b"bad", "text/plain")),
    ]
    data = {
        "target_dir": "",
        "relative_paths": json.dumps(["ok.txt", "../bad.txt"]),
    }

    res = await logged_in_client.post("/api/uploads", data=data, files=files)

    assert res.status_code == 200
    body = res.json()
    assert body["summary"] == {"total": 2, "succeeded": 1, "failed": 1}
    assert body["items"][0]["status"] == "success"
    assert body["items"][1]["status"] == "failed"
    assert "路径" in body["items"][1]["error"]
    assert Path("user_workspaces/alice/ok.txt").read_text(encoding="utf-8") == "ok"


async def test_oversized_upload_does_not_leave_partial_file(logged_in_client, monkeypatch):
    """单文件上传失败时不能留下半截目标文件,避免用户看到损坏文件。"""
    from app.modules.uploads import service as uploads_service

    monkeypatch.setattr(uploads_service, "_MAX_FILE_SIZE", 3)
    files = {
        "files": (
            "large.docx",
            b"abcdef",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }

    res = await logged_in_client.post("/api/uploads", files=files)

    assert res.status_code == 200
    body = res.json()
    assert body["summary"] == {"total": 1, "succeeded": 0, "failed": 1}
    assert body["items"][0]["status"] == "failed"
    assert "超过" in body["items"][0]["error"]
    assert not Path("user_workspaces/alice/large.docx").exists()
    assert not list(Path("user_workspaces/alice").glob(".large.docx.uploading*"))


async def test_upload_item_exception_is_logged(tmp_path, monkeypatch, caplog):
    import logging

    from starlette.datastructures import UploadFile

    from app.modules.uploads import service as uploads_service

    def boom(path):
        raise RuntimeError("dedupe exploded")

    monkeypatch.setattr(uploads_service, "_dedupe_path", boom)

    with caplog.at_level(logging.ERROR, logger=uploads_service.__name__):
        body = await uploads_service.save_uploaded_files(
            [UploadFile(filename="note.txt", file=BytesIO(b"hello"))],
            tmp_path,
        )

    assert body["summary"] == {"total": 1, "succeeded": 0, "failed": 1}
    assert "dedupe exploded" in body["items"][0]["error"]
    assert any(
        record.levelno == logging.ERROR
        and record.exc_info
        and "Upload item failed" in record.getMessage()
        for record in caplog.records
    )
    assert "note.txt" not in caplog.text
