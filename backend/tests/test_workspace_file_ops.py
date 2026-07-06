from pathlib import Path

from sqlalchemy import select


async def test_read_and_save_text_file(logged_in_client):
    ws = Path("user_workspaces/alice")
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "notes.md").write_text("# Old\n", encoding="utf-8")

    res = await logged_in_client.get("/api/workspace/preview", params={"path": "notes.md"})
    assert res.status_code == 200
    assert res.text == "# Old\n"

    res = await logged_in_client.put(
        "/api/workspace/content",
        json={"path": "notes.md", "content": "# New\n"},
    )
    assert res.status_code == 200
    assert res.json()["path"] == "notes.md"
    assert (ws / "notes.md").read_text(encoding="utf-8") == "# New\n"


async def test_reject_binary_content_edit(logged_in_client):
    ws = Path("user_workspaces/alice")
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "image.png").write_bytes(b"\x89PNG")

    res = await logged_in_client.put(
        "/api/workspace/content",
        json={"path": "image.png", "content": "bad"},
    )
    assert res.status_code == 415


async def test_save_converted_markdown_through_source_file(logged_in_client):
    """Office/PDF 编辑保存的是转换后的 Markdown，不反写源文件。"""
    from app.core.config import user_workspace
    from app.modules.workspace.markdown_index import add_markdown_mapping

    ws = user_workspace("alice")
    (ws / "uploads").mkdir()
    (ws / "uploads" / "a.pdf").write_bytes(b"%PDF")
    (ws / ".markdown" / "a").mkdir(parents=True)
    (ws / ".markdown" / "a" / "a.md").write_text("# Old", encoding="utf-8")
    add_markdown_mapping(
        ws,
        source_path="uploads/a.pdf",
        source_name="a.pdf",
        markdown_path=".markdown/a/a.md",
        extract_dir=".markdown/a",
    )

    res = await logged_in_client.put(
        "/api/workspace/content",
        json={"path": "uploads/a.pdf", "content": "# New"},
    )

    assert res.status_code == 200
    assert res.json()["path"] == ".markdown/a/a.md"
    assert (ws / ".markdown" / "a" / "a.md").read_text(encoding="utf-8") == "# New"
    assert (ws / "uploads" / "a.pdf").read_bytes() == b"%PDF"


async def test_save_office_without_markdown_returns_unified_hint(logged_in_client):
    ws = Path("user_workspaces/alice")
    (ws / "uploads").mkdir(parents=True)
    (ws / "uploads" / "a.pdf").write_bytes(b"%PDF")

    res = await logged_in_client.put(
        "/api/workspace/content",
        json={"path": "uploads/a.pdf", "content": "# New"},
    )

    assert res.status_code == 409
    assert "尚未生成转换后的 Markdown" in res.json()["detail"]


async def test_create_rename_and_move_file(logged_in_client):
    res = await logged_in_client.post(
        "/api/workspace/file",
        json={"path": "docs/a.md", "kind": "file", "content": "# A\n"},
    )
    assert res.status_code == 200

    res = await logged_in_client.patch(
        "/api/workspace/file/rename",
        json={"path": "docs/a.md", "new_name": "b.md"},
    )
    assert res.status_code == 200

    res = await logged_in_client.patch(
        "/api/workspace/file/move",
        json={"path": "docs/b.md", "target_dir": "archive"},
    )
    assert res.status_code == 200
    assert Path("user_workspaces/alice/archive/b.md").read_text(encoding="utf-8") == "# A\n"


async def test_rename_converted_source_updates_markdown_mapping(logged_in_client):
    """重命名已转换的源文件时，markdown 索引和 ConversionTask 的 source_path 同步更新。"""
    from app.core.config import user_workspace
    from app.db.session import async_session
    from app.models.conversion_task import ConversionTask
    from app.modules.workspace.markdown_index import (
        add_markdown_mapping,
        resolve_preview_path,
    )

    ws = user_workspace("alice")
    (ws / "uploads").mkdir()
    (ws / "uploads" / "a.pdf").write_bytes(b"%PDF")
    (ws / ".markdown" / "a").mkdir(parents=True)
    add_markdown_mapping(
        ws,
        source_path="uploads/a.pdf",
        source_name="a.pdf",
        markdown_path=".markdown/a/a.md",
        extract_dir=".markdown/a",
    )

    async with async_session() as session:
        task = ConversionTask(
            username="alice",
            source_path="uploads/a.pdf",
            source_name="a.pdf",
            status="succeeded",
            markdown_path=".markdown/a/a.md",
        )
        session.add(task)
        await session.commit()

    res = await logged_in_client.patch(
        "/api/workspace/file/rename",
        json={"path": "uploads/a.pdf", "new_name": "b.pdf"},
    )
    assert res.status_code == 200
    assert res.json()["path"] == "uploads/b.pdf"

    # markdown 索引已更新
    assert resolve_preview_path(ws, "uploads/b.pdf") == ".markdown/a/a.md"
    assert resolve_preview_path(ws, "uploads/a.pdf") == "uploads/a.pdf"

    # ConversionTask 的 source_path 已更新
    async with async_session() as session:
        result = await session.execute(
            select(ConversionTask).where(ConversionTask.id == task.id)
        )
        updated_task = result.scalar_one()
        assert updated_task.source_path == "uploads/b.pdf"
