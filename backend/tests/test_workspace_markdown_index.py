import json
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.modules.workspace.markdown_index import (
    INDEX_PATH,
    add_markdown_mapping,
    ensure_markdown_root,
    find_markdown_mappings_under,
    remove_markdown_mappings,
    resolve_preview_path,
)


def test_add_markdown_mapping_and_resolve_preview_path(tmp_path):
    workspace = tmp_path

    mapping = add_markdown_mapping(
        workspace,
        "uploads\\source.docx",
        "source.docx",
        ".markdown\\extracts/source/index.md",
        ".markdown\\extracts/source",
    )

    assert mapping.source_path == "uploads/source.docx"
    assert mapping.markdown_path == ".markdown/extracts/source/index.md"
    assert resolve_preview_path(workspace, "uploads/source.docx") == (
        ".markdown/extracts/source/index.md"
    )
    assert resolve_preview_path(workspace, "uploads\\source.docx") == (
        ".markdown/extracts/source/index.md"
    )
    assert resolve_preview_path(workspace, "uploads/other.pdf") == "uploads/other.pdf"


def test_ensure_markdown_root_creates_valid_directory(tmp_path):
    workspace = tmp_path

    markdown_root = ensure_markdown_root(workspace)

    assert markdown_root == workspace / ".markdown"
    assert markdown_root.is_dir()


def test_find_markdown_mappings_under_exact_file_and_directory_prefix(tmp_path):
    workspace = tmp_path
    file_mapping = add_markdown_mapping(
        workspace,
        "uploads/folder/a.pdf",
        "a.pdf",
        ".markdown/extracts/a/index.md",
        ".markdown/extracts/a",
    )
    nested_mapping = add_markdown_mapping(
        workspace,
        "uploads/folder/sub/b.pdf",
        "b.pdf",
        ".markdown/extracts/b/index.md",
        ".markdown/extracts/b",
    )
    add_markdown_mapping(
        workspace,
        "uploads/folder2/c.pdf",
        "c.pdf",
        ".markdown/extracts/c/index.md",
        ".markdown/extracts/c",
    )

    assert find_markdown_mappings_under(workspace, "uploads/folder/a.pdf") == [
        file_mapping
    ]
    assert find_markdown_mappings_under(workspace, "uploads/folder") == [
        file_mapping,
        nested_mapping,
    ]


def test_remove_markdown_mappings_deletes_extract_dir_and_preserves_unrelated(tmp_path):
    workspace = tmp_path
    remove_dir = workspace / ".markdown" / "extracts" / "remove"
    keep_dir = workspace / ".markdown" / "extracts" / "keep"
    remove_dir.mkdir(parents=True)
    keep_dir.mkdir(parents=True)
    (remove_dir / "index.md").write_text("# remove", encoding="utf-8")
    (keep_dir / "index.md").write_text("# keep", encoding="utf-8")

    remove_mapping = add_markdown_mapping(
        workspace,
        "uploads/remove.pdf",
        "remove.pdf",
        ".markdown/extracts/remove/index.md",
        ".markdown/extracts/remove",
    )
    keep_mapping = add_markdown_mapping(
        workspace,
        "uploads/keep.pdf",
        "keep.pdf",
        ".markdown/extracts/keep/index.md",
        ".markdown/extracts/keep",
    )

    remove_markdown_mappings(workspace, [remove_mapping])

    assert not remove_dir.exists()
    assert keep_dir.exists()
    assert resolve_preview_path(workspace, "uploads/remove.pdf") == "uploads/remove.pdf"
    assert find_markdown_mappings_under(workspace, "uploads") == [keep_mapping]


def test_remove_markdown_mappings_missing_extract_dir_still_cleans_index(tmp_path):
    workspace = tmp_path
    mapping = add_markdown_mapping(
        workspace,
        "uploads/missing.pdf",
        "missing.pdf",
        ".markdown/extracts/missing/index.md",
        ".markdown/extracts/missing",
    )

    remove_markdown_mappings(workspace, [mapping])

    assert resolve_preview_path(workspace, "uploads/missing.pdf") == "uploads/missing.pdf"
    index = json.loads((workspace / INDEX_PATH).read_text(encoding="utf-8"))
    assert index["mappings"] == []


def test_remove_markdown_mappings_rejects_extract_dir_outside_markdown(tmp_path):
    workspace = tmp_path
    index = {
        "mappings": [
            {
                "source_path": "uploads/bad.pdf",
                "source_name": "bad.pdf",
                "markdown_path": ".markdown/extracts/bad/index.md",
                "extract_dir": "../outside",
                "created_at": "2026-05-13T00:00:00+00:00",
            }
        ]
    }
    (workspace / ".markdown").mkdir()
    (workspace / INDEX_PATH).write_text(json.dumps(index), encoding="utf-8")
    mapping = SimpleNamespace(source_path="uploads/bad.pdf", extract_dir="../outside")

    with pytest.raises(HTTPException) as exc_info:
        remove_markdown_mappings(workspace, [mapping])

    assert exc_info.value.status_code == 500


def test_remove_one_mapping_keeps_shared_extract_dir_for_remaining_mapping(tmp_path):
    workspace = tmp_path
    shared_dir = workspace / ".markdown" / "extracts" / "shared"
    shared_dir.mkdir(parents=True)
    (shared_dir / "index.md").write_text("# shared", encoding="utf-8")

    remove_mapping = add_markdown_mapping(
        workspace,
        "uploads/one.pdf",
        "one.pdf",
        ".markdown/extracts/shared/index.md",
        ".markdown/extracts/shared",
    )
    keep_mapping = add_markdown_mapping(
        workspace,
        "uploads/two.pdf",
        "two.pdf",
        ".markdown/extracts/shared/index.md",
        ".markdown/extracts/shared",
    )

    remove_markdown_mappings(workspace, [remove_mapping])

    assert shared_dir.exists()
    assert find_markdown_mappings_under(workspace, "uploads") == [keep_mapping]


def test_add_markdown_mapping_normalizes_absolute_workspace_paths(tmp_path):
    workspace = tmp_path
    source = workspace / "uploads" / "source.pdf"
    markdown = workspace / ".markdown" / "extracts" / "source" / "index.md"
    extract_dir = workspace / ".markdown" / "extracts" / "source"

    mapping = add_markdown_mapping(
        workspace,
        str(source),
        "source.pdf",
        str(markdown),
        str(extract_dir),
    )

    assert mapping.source_path == "uploads/source.pdf"
    assert mapping.markdown_path == ".markdown/extracts/source/index.md"
    assert mapping.extract_dir == ".markdown/extracts/source"


def test_add_markdown_mapping_rejects_absolute_paths_outside_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.pdf"

    with pytest.raises(HTTPException) as exc_info:
        add_markdown_mapping(
            workspace,
            str(outside),
            "outside.pdf",
            ".markdown/extracts/outside/index.md",
            ".markdown/extracts/outside",
        )

    assert exc_info.value.status_code == 500


def test_add_markdown_mapping_rejects_paths_containing_dot_dot(tmp_path):
    workspace = tmp_path

    for source_path, markdown_path, extract_dir in [
        ("uploads/../source.pdf", ".markdown/extracts/source/index.md", ".markdown/extracts/source"),
        ("uploads/source.pdf", ".markdown/../index.md", ".markdown/extracts/source"),
        ("uploads/source.pdf", ".markdown/extracts/source/index.md", ".markdown/../source"),
    ]:
        with pytest.raises(HTTPException) as exc_info:
            add_markdown_mapping(
                workspace,
                source_path,
                "source.pdf",
                markdown_path,
                extract_dir,
            )
        assert exc_info.value.status_code == 500


def test_add_markdown_mapping_rejects_markdown_paths_outside_markdown(tmp_path):
    workspace = tmp_path

    with pytest.raises(HTTPException) as markdown_exc:
        add_markdown_mapping(
            workspace,
            "uploads/source.pdf",
            "source.pdf",
            "output/index.md",
            ".markdown/extracts/source",
        )

    with pytest.raises(HTTPException) as extract_exc:
        add_markdown_mapping(
            workspace,
            "uploads/source.pdf",
            "source.pdf",
            ".markdown/extracts/source/index.md",
            "output/source",
        )

    assert markdown_exc.value.status_code == 500
    assert extract_exc.value.status_code == 500


@pytest.mark.skipif(sys.platform == "win32", reason="symlink semantics differ on Windows")
def test_markdown_index_rejects_symlinked_markdown_root(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    external_markdown = tmp_path / "external-markdown"
    external_markdown.mkdir()
    external_index = external_markdown / "index.json"
    external_index.write_text('{"mappings":[]}', encoding="utf-8")
    (workspace / ".markdown").symlink_to(external_markdown, target_is_directory=True)
    original_external_index = external_index.read_text(encoding="utf-8")

    with pytest.raises(HTTPException) as resolve_exc:
        resolve_preview_path(workspace, "uploads/source.pdf")
    with pytest.raises(HTTPException) as ensure_exc:
        ensure_markdown_root(workspace)
    with pytest.raises(HTTPException) as add_exc:
        add_markdown_mapping(
            workspace,
            "uploads/new.pdf",
            "new.pdf",
            ".markdown/extracts/new/index.md",
            ".markdown/extracts/new",
        )
    with pytest.raises(HTTPException) as remove_exc:
        remove_markdown_mappings(workspace, [])

    assert resolve_exc.value.status_code == 500
    assert ensure_exc.value.status_code == 500
    assert add_exc.value.status_code == 500
    assert remove_exc.value.status_code == 500
    assert external_index.read_text(encoding="utf-8") == original_external_index
