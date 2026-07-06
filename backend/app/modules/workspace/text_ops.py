"""工作空间文本编辑与文件管理操作。"""

import shutil
from pathlib import Path

from fastapi import HTTPException, status

from app.core.utils import safe_filename
from app.modules.workspace.markdown_index import (
    resolve_preview_path,
    update_markdown_source_path,
)
from app.modules.workspace.paths import resolve_inside_workspace
from app.modules.workspace.preview import is_convertible_document

TEXT_SUFFIXES = {
    ".txt", ".md", ".markdown", ".py", ".js", ".ts", ".tsx", ".json",
    ".yaml", ".yml", ".toml", ".css", ".html", ".sh", ".sql", ".log", ".env",
}
MAX_TEXT_BYTES = 2 * 1024 * 1024
_CONVERTED_MARKDOWN_MISSING = "尚未生成转换后的 Markdown，请等待转换完成或重新转换"


def ensure_editable_text_path(path: Path) -> None:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="该文件类型不支持文本编辑")
    if ".markdown" in path.parts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不允许直接编辑 .markdown 目录")


def _ensure_editable_resolved_path(path: Path, *, allow_markdown: bool) -> None:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="该文件类型不支持文本编辑",
        )
    if not allow_markdown and ".markdown" in path.parts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不允许直接编辑 .markdown 目录",
        )


def _resolve_content_target(workspace: Path, rel_path: str) -> tuple[Path, str, bool]:
    source = resolve_inside_workspace(workspace, rel_path)
    mapped_rel_path = resolve_preview_path(workspace, rel_path)
    if mapped_rel_path == rel_path and is_convertible_document(source):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_CONVERTED_MARKDOWN_MISSING,
        )
    allow_markdown = mapped_rel_path != rel_path
    target = resolve_inside_workspace(workspace, mapped_rel_path)
    return target, mapped_rel_path, allow_markdown


def read_text_file(workspace: Path, rel_path: str) -> dict:
    target = resolve_inside_workspace(workspace, rel_path)
    ensure_editable_text_path(target)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    size = target.stat().st_size
    if size > MAX_TEXT_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="文件过大")
    return {
        "path": rel_path,
        "content": target.read_text(encoding="utf-8"),
        "size": size,
        "mtime": target.stat().st_mtime,
    }


def save_text_file(workspace: Path, rel_path: str, content: str) -> dict:
    target = resolve_inside_workspace(workspace, rel_path)
    ensure_editable_text_path(target)
    if len(content.encode("utf-8")) > MAX_TEXT_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="内容过大")
    target.write_text(content, encoding="utf-8")
    return read_text_file(workspace, rel_path)


def save_content_file(workspace: Path, rel_path: str, content: str) -> dict:
    """按统一预览解析规则保存可编辑内容。

    普通文本文件保存原文件；Office/PDF 源文件保存其转换后的 Markdown。
    """
    target, resolved_path, allow_markdown = _resolve_content_target(workspace, rel_path)
    _ensure_editable_resolved_path(target, allow_markdown=allow_markdown)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    if len(content.encode("utf-8")) > MAX_TEXT_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="内容过大")
    target.write_text(content, encoding="utf-8")
    size = target.stat().st_size
    return {
        "path": resolved_path,
        "content": content,
        "size": size,
        "mtime": target.stat().st_mtime,
    }


def resolve_content_write_path(workspace: Path, rel_path: str) -> str:
    """返回保存接口实际会写入的工作区相对路径。"""
    target, resolved_path, allow_markdown = _resolve_content_target(workspace, rel_path)
    _ensure_editable_resolved_path(target, allow_markdown=allow_markdown)
    return resolved_path


def create_workspace_item(workspace: Path, rel_path: str, kind: str, content: str = "") -> dict:
    target = resolve_inside_workspace(workspace, rel_path)
    if target.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="目标已存在")
    if kind == "dir":
        target.mkdir(parents=True)
    elif kind == "file":
        ensure_editable_text_path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="kind 只能是 file 或 dir")
    return {"path": target.relative_to(workspace.resolve()).as_posix()}


def rename_workspace_item(workspace: Path, rel_path: str, new_name: str) -> dict:
    source = resolve_inside_workspace(workspace, rel_path)
    if not source.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源路径不存在")
    name = safe_filename(new_name)
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新名称无效")
    target = source.parent / name
    if target.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="目标已存在")
    source.rename(target)
    new_rel = target.resolve().relative_to(workspace.resolve()).as_posix()
    update_markdown_source_path(workspace, rel_path, new_rel)
    return {"path": new_rel}


def move_workspace_item(workspace: Path, rel_path: str, target_dir: str) -> dict:
    source = resolve_inside_workspace(workspace, rel_path)
    dest_dir = workspace if not target_dir else resolve_inside_workspace(workspace, target_dir)
    if not dest_dir.exists():
        dest_dir.mkdir(parents=True)
    if not dest_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标不是目录")
    target = dest_dir / source.name
    if target.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="目标已存在")
    shutil.move(str(source), str(target))
    new_rel = target.resolve().relative_to(workspace.resolve()).as_posix()
    update_markdown_source_path(workspace, rel_path, new_rel)
    return {"path": new_rel}
