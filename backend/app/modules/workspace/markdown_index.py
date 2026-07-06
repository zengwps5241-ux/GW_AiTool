"""Workspace markdown extraction index."""

import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import HTTPException, status

INDEX_PATH = ".markdown/index.json"


@dataclass(frozen=True)
class MarkdownMapping:
    source_path: str
    source_name: str
    markdown_path: str
    extract_dir: str
    created_at: str


def add_markdown_mapping(
    workspace: Path,
    source_path: str,
    source_name: str,
    markdown_path: str,
    extract_dir: str,
) -> MarkdownMapping:
    mapping = MarkdownMapping(
        source_path=_normalize_source_path(workspace, source_path),
        source_name=source_name,
        markdown_path=_normalize_markdown_path(workspace, markdown_path),
        extract_dir=_normalize_extract_dir(workspace, extract_dir),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    mappings = [
        existing
        for existing in _read_mappings(workspace)
        if existing.source_path != mapping.source_path
    ]
    mappings.append(mapping)
    _write_mappings(workspace, mappings)
    return mapping


def ensure_markdown_root(workspace: Path) -> Path:
    markdown_root = _markdown_root(workspace)
    try:
        markdown_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建 Markdown 目录失败:{exc}",
        )
    return _markdown_root(workspace)


def resolve_preview_path(workspace: Path, rel_path: str) -> str:
    normalized = _normalize_workspace_path(workspace, rel_path, allow_empty=False)
    for mapping in _read_mappings(workspace):
        if mapping.source_path == normalized:
            return mapping.markdown_path
    return normalized


def find_markdown_mappings_under(
    workspace: Path, rel_path: str
) -> list[MarkdownMapping]:
    normalized = _normalize_lookup_path(workspace, rel_path)
    mappings = _read_mappings(workspace)
    if normalized in ("", "."):
        return mappings
    prefix = f"{normalized.rstrip('/')}/"
    return [
        mapping
        for mapping in mappings
        if mapping.source_path == normalized or mapping.source_path.startswith(prefix)
    ]


def update_markdown_source_path(
    workspace: Path, old_source_path: str, new_source_path: str
) -> None:
    """当源文件被重命名或移动时，同步更新索引中的 source_path。"""
    old_normalized = _normalize_source_path(workspace, old_source_path)
    new_normalized = _normalize_source_path(workspace, new_source_path)
    mappings = _read_mappings(workspace)
    for i, mapping in enumerate(mappings):
        if mapping.source_path == old_normalized:
            mappings[i] = MarkdownMapping(
                source_path=new_normalized,
                source_name=mapping.source_name,
                markdown_path=mapping.markdown_path,
                extract_dir=mapping.extract_dir,
                created_at=mapping.created_at,
            )
            _write_mappings(workspace, mappings)
            return


def remove_markdown_mappings(
    workspace: Path, mappings: list[MarkdownMapping]
) -> None:
    remove_keys = {
        _normalize_source_path(workspace, mapping.source_path) for mapping in mappings
    }
    markdown_root = _markdown_root(workspace)
    current_mappings = _read_mappings(workspace)
    remaining = [
        mapping for mapping in current_mappings if mapping.source_path not in remove_keys
    ]
    remaining_extract_dirs = {mapping.extract_dir for mapping in remaining}
    candidate_extract_dirs = {
        mapping.extract_dir
        for mapping in current_mappings
        if mapping.source_path in remove_keys
        and mapping.extract_dir not in remaining_extract_dirs
    }
    extract_dirs = [
        _extract_dir_path(workspace, markdown_root, extract_dir)
        for extract_dir in candidate_extract_dirs
    ]

    for extract_dir in extract_dirs:
        if extract_dir.exists():
            try:
                shutil.rmtree(extract_dir)
            except OSError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"删除 Markdown 提取目录失败:{exc}",
                )

    _write_mappings(workspace, remaining)


def _normalize_lookup_path(workspace: Path, path: str) -> str:
    cleaned = path.strip().replace("\\", "/")
    if cleaned in ("", "."):
        return cleaned
    return _normalize_workspace_path(workspace, path, allow_empty=False)


def _normalize_source_path(workspace: Path, path: str) -> str:
    normalized = _normalize_workspace_path(workspace, path, allow_empty=False)
    target = (workspace.resolve() / normalized).resolve()
    if target.is_relative_to(_markdown_root(workspace)):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="源文件不能位于 .markdown 目录下",
        )
    return normalized


def _normalize_markdown_path(workspace: Path, path: str) -> str:
    normalized = _normalize_workspace_path(workspace, path, allow_empty=False)
    _require_under_markdown(workspace, normalized, allow_markdown_root=False)
    return normalized


def _normalize_extract_dir(workspace: Path, path: str) -> str:
    normalized = _normalize_workspace_path(workspace, path, allow_empty=False)
    _require_under_markdown(workspace, normalized, allow_markdown_root=False)
    return normalized


def _normalize_workspace_path(
    workspace: Path, path: str, *, allow_empty: bool
) -> str:
    cleaned = path.strip().replace("\\", "/")
    if cleaned == "":
        if allow_empty:
            return ""
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Markdown 索引路径不能为空",
        )
    if ".." in PurePosixPath(cleaned).parts:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Markdown 索引路径不能包含 ..",
        )

    workspace_root = workspace.resolve()
    input_path = Path(cleaned)
    if input_path.is_absolute():
        try:
            target = input_path.resolve()
            return target.relative_to(workspace_root).as_posix()
        except (OSError, RuntimeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Markdown 索引路径越出工作区",
            )

    try:
        target = (workspace_root / cleaned).resolve()
        return target.relative_to(workspace_root).as_posix()
    except (OSError, RuntimeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Markdown 索引路径越出工作区",
        )


def _require_under_markdown(
    workspace: Path, rel_path: str, *, allow_markdown_root: bool
) -> None:
    markdown_root = _markdown_root(workspace)
    target = (workspace.resolve() / rel_path).resolve()
    if target == markdown_root and allow_markdown_root:
        return
    if target == markdown_root or not target.is_relative_to(markdown_root):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Markdown 索引路径越出 .markdown",
        )


def _index_file(workspace: Path) -> Path:
    return _markdown_root(workspace) / "index.json"


def _markdown_root(workspace: Path) -> Path:
    try:
        workspace_root = workspace.resolve()
        markdown_root = workspace_root / ".markdown"
        if markdown_root.exists():
            resolved = markdown_root.resolve()
            if resolved != markdown_root or not resolved.is_relative_to(workspace_root):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Markdown 目录不能是符号链接或越出工作区",
                )
        return markdown_root
    except (OSError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Markdown 目录路径无效:{exc}",
        )


def _extract_dir_path(workspace: Path, markdown_root: Path, extract_dir: str) -> Path:
    try:
        normalized = _normalize_extract_dir(workspace, extract_dir)
        target = (workspace.resolve() / normalized).resolve()
    except (OSError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Markdown 提取目录路径无效:{exc}",
        )
    if target == markdown_root or not target.is_relative_to(markdown_root):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Markdown 提取目录越出 .markdown",
        )
    return target


def _read_mappings(workspace: Path) -> list[MarkdownMapping]:
    index_file = _index_file(workspace)
    if not index_file.exists():
        return []
    try:
        raw = json.loads(index_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Markdown 索引 JSON 无效:{exc}",
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取 Markdown 索引失败:{exc}",
        )

    items = raw.get("mappings") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Markdown 索引格式无效",
        )
    return [_mapping_from_dict(workspace, item) for item in items]


def _mapping_from_dict(workspace: Path, item: Any) -> MarkdownMapping:
    if not isinstance(item, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Markdown 索引条目格式无效",
        )
    try:
        return MarkdownMapping(
            source_path=_normalize_source_path(workspace, str(item["source_path"])),
            source_name=str(item["source_name"]),
            markdown_path=_normalize_markdown_path(
                workspace, str(item["markdown_path"])
            ),
            extract_dir=_normalize_extract_dir(workspace, str(item["extract_dir"])),
            created_at=str(item["created_at"]),
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Markdown 索引条目缺少字段:{exc}",
        )


def _write_mappings(workspace: Path, mappings: list[MarkdownMapping]) -> None:
    index_file = _index_file(workspace)
    index_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"mappings": [asdict(mapping) for mapping in mappings]}
    fd: int | None = None
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=".index.", suffix=".tmp", dir=index_file.parent
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = None
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_name, index_file)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"写入 Markdown 索引失败:{exc}",
        )
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_name is not None:
            try:
                if Path(tmp_name).exists():
                    Path(tmp_name).unlink()
            except OSError:
                pass
