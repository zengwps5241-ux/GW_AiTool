"""工作空间统一预览/编辑规则的服务层测试。"""

import pytest
from fastapi import HTTPException


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


def test_save_content_writes_plain_text_source_file(tmp_path):
    """普通文本型文件保存原文件。"""
    from app.modules.workspace.text_ops import save_content_file

    workspace = tmp_path
    (workspace / "note.txt").write_text("old", encoding="utf-8")

    result = save_content_file(workspace, "note.txt", "new")

    assert result["path"] == "note.txt"
    assert (workspace / "note.txt").read_text(encoding="utf-8") == "new"


def test_save_content_writes_converted_markdown_for_pdf_source(tmp_path):
    """Office/PDF 保存写入转换后的 Markdown，不反写源文件。"""
    from app.modules.workspace.markdown_index import add_markdown_mapping
    from app.modules.workspace.text_ops import save_content_file

    workspace = tmp_path
    (workspace / "uploads").mkdir()
    (workspace / "uploads" / "a.pdf").write_bytes(b"%PDF")
    (workspace / ".markdown" / "a").mkdir(parents=True)
    (workspace / ".markdown" / "a" / "a.md").write_text("# Old", encoding="utf-8")
    add_markdown_mapping(
        workspace,
        source_path="uploads/a.pdf",
        source_name="a.pdf",
        markdown_path=".markdown/a/a.md",
        extract_dir=".markdown/a",
    )

    result = save_content_file(workspace, "uploads/a.pdf", "# New")

    assert result["path"] == ".markdown/a/a.md"
    assert (workspace / ".markdown" / "a" / "a.md").read_text(encoding="utf-8") == "# New"
    assert (workspace / "uploads" / "a.pdf").read_bytes() == b"%PDF"


def test_save_content_pdf_without_markdown_mapping_raises_unified_hint(tmp_path):
    """Office/PDF 没有 Markdown 映射时，保存也给同一提示。"""
    from app.modules.workspace.text_ops import save_content_file

    workspace = tmp_path
    (workspace / "raw.pdf").write_bytes(b"%PDF")

    with pytest.raises(HTTPException) as exc:
        save_content_file(workspace, "raw.pdf", "# New")

    assert exc.value.status_code == 409
    assert "尚未生成转换后的 Markdown" in exc.value.detail


def test_preview_inline_headers_disable_cache():
    """统一预览接口要禁止缓存，避免保存后继续看到旧文件内容。"""
    from app.modules.workspace.preview import inline_headers

    headers = inline_headers("text/plain; charset=utf-8")

    assert headers["Cache-Control"] == "no-store"
