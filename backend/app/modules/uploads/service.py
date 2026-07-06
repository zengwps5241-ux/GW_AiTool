"""文件上传业务逻辑。"""

import json
import logging
import os
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings
from app.core.utils import safe_filename
from app.integrations.mineru import MineruConversionError, convert_document_to_markdown
from app.modules.conversions.service import create_conversion_task, is_convertible_path
from app.modules.workspace.markdown_index import (
    MarkdownMapping,
    add_markdown_mapping,
    ensure_markdown_root,
    remove_markdown_mappings,
)
from app.modules.workspace.paths import resolve_inside_workspace

logger = logging.getLogger(__name__)

_MAX_FILE_SIZE = 200 * 1024 * 1024
_CONVERTIBLE_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
}


def _safe_relative_parts(path: str) -> list[str]:
    parts: list[str] = []
    for raw in path.replace("\\", "/").split("/"):
        if raw in {"", ".", ".."}:
            raise ValueError("路径包含非法片段")
        part = safe_filename(raw)
        if not part:
            raise ValueError("路径包含非法片段")
        parts.append(part)
    if not parts:
        raise ValueError("路径不能为空")
    return parts


def _dedupe_path(target: Path) -> Path:
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    idx = 1
    while True:
        candidate = parent / f"{stem} ({idx}){suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


def _upload_tmp_path(target: Path) -> Path:
    """独占预留目标文件的同目录临时路径。"""
    tmp_target, out = _open_upload_tmp_file(target)
    out.close()
    return tmp_target


def _open_upload_tmp_file(target: Path) -> tuple[Path, BinaryIO]:
    """独占创建上传临时文件,避免并发请求共享同一个临时路径。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    idx = 0
    while True:
        suffix = "" if idx == 0 else f".{idx}"
        tmp_target = target.parent / f".{target.name}.uploading{suffix}"
        try:
            fd = os.open(tmp_target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            idx += 1
            continue
        return tmp_target, os.fdopen(fd, "wb")


async def save_uploaded_files(
    files: list[UploadFile],
    workspace: Path,
    *,
    target_dir: str = "",
    relative_paths: list[str] | None = None,
    username: str | None = None,
    session=None,
) -> dict:
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未提供任何文件")

    base_dir = workspace if not target_dir else resolve_inside_workspace(workspace, target_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []

    for idx, f in enumerate(files):
        original = safe_filename(f.filename or "file")
        rel_input = relative_paths[idx] if relative_paths and idx < len(relative_paths) else original
        try:
            parts = _safe_relative_parts(rel_input)
            parts[-1] = safe_filename(parts[-1] or original)
            target = _dedupe_path(base_dir.joinpath(*parts))
            target.parent.mkdir(parents=True, exist_ok=True)

            total = 0
            tmp_target, out = _open_upload_tmp_file(target)
            try:
                with out:
                    while True:
                        chunk = await f.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > _MAX_FILE_SIZE:
                            raise ValueError(
                                f"文件 {original} 超过 {_MAX_FILE_SIZE // (1024 * 1024)} MB 上限"
                            )
                        out.write(chunk)
                tmp_target.replace(target)
            except Exception:
                tmp_target.unlink(missing_ok=True)
                raise

            rel_source_path = target.resolve().relative_to(workspace.resolve()).as_posix()
            item = {
                "name": original,
                "path": rel_source_path,
                "size": total,
                "preview_path": rel_source_path,
                "agent_path": rel_source_path,
                "converted": False,
                "conversion_task_id": None,
                "status": "success",
                "error": None,
            }
            if username and session is not None and is_convertible_path(target):
                task = await create_conversion_task(
                    session,
                    username=username,
                    workspace=workspace,
                    source_path=rel_source_path,
                )
                item["conversion_task_id"] = task.id
            items.append(item)
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
        finally:
            await f.close()

    succeeded = sum(1 for item in items if item["status"] == "success")
    return {
        "summary": {"total": len(items), "succeeded": succeeded, "failed": len(items) - succeeded},
        "items": items,
    }
