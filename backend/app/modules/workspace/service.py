"""工作空间业务逻辑组合。"""

import shutil
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse

from app.modules.workspace.archive import iter_zip, walk_filtered
from app.modules.workspace.markdown_index import (
    find_markdown_mappings_under,
    remove_markdown_mappings,
    resolve_preview_path,
)
from app.modules.workspace.paths import list_dir, resolve_inside_workspace
from app.modules.workspace.preview import (
    guess_mime,
    inline_headers,
    is_convertible_document,
    preview_kind,
    _PREVIEW_LIMITS,
    _MB,
)

_CONVERTED_MARKDOWN_MISSING = "尚未生成转换后的 Markdown，请等待转换完成或重新转换"


def get_workspace_tree(
    workspace: Path, conversion_meta: dict[str, dict] | None = None
) -> list:
    # 通过 markdown 索引把 ``源文件 -> .markdown 内 md 路径`` 一并下发,
    # 前端在工作空间引用文件时即可直接给智能体 markdown 路径。
    mappings = find_markdown_mappings_under(workspace, ".")
    agent_paths = {m.source_path: m.markdown_path for m in mappings}
    return list_dir(
        workspace, rel_base="", depth=0, agent_paths=agent_paths, conversion_meta=conversion_meta
    )


def delete_workspace_item(workspace: Path, rel_path: str) -> None:
    target = resolve_inside_workspace(workspace, rel_path)
    if target.resolve() == workspace.resolve():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="禁止删除工作区根目录"
        )
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="文件或目录不存在"
        )
    mappings = find_markdown_mappings_under(workspace, rel_path)
    remove_markdown_mappings(workspace, mappings)
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除失败:{exc}",
        )


def download_workspace_item(workspace: Path, rel_path: str):
    target = resolve_inside_workspace(workspace, rel_path)
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="文件或目录不存在"
        )

    if target.is_file():
        quoted = quote(target.name, safe="")
        return FileResponse(
            path=target,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quoted}",
                "Cache-Control": "no-store",
            },
        )

    if target.resolve() == workspace.resolve():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不允许下载整个工作区,请选择具体子目录",
        )

    ws_root = workspace.resolve()
    quoted = quote(f"{target.name}.zip", safe="")
    return StreamingResponse(
        iter_zip(target, ws_root),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted}",
            "Cache-Control": "no-store",
        },
    )


def download_workspace_markdown(workspace: Path, rel_path: str):
    """下载 Office/PDF 源文件对应的 Markdown 提取目录 zip。"""
    source = resolve_inside_workspace(workspace, rel_path)
    if not source.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="文件或目录不存在"
        )
    if not source.is_file() or not is_convertible_document(source):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅 Office/PDF 源文件支持下载 Markdown",
        )

    normalized_rel_path = source.relative_to(workspace.resolve()).as_posix()
    mapping = next(
        (
            item
            for item in find_markdown_mappings_under(workspace, rel_path)
            if item.source_path == normalized_rel_path
        ),
        None,
    )
    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_CONVERTED_MARKDOWN_MISSING,
        )

    extract_dir = resolve_inside_workspace(workspace, mapping.extract_dir)
    markdown_root = (workspace.resolve() / ".markdown").resolve()
    if (
        not extract_dir.exists()
        or not extract_dir.is_dir()
        or extract_dir == markdown_root
        or not extract_dir.is_relative_to(markdown_root)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_CONVERTED_MARKDOWN_MISSING,
        )

    quoted = quote(f"{source.stem}-markdown.zip", safe="")
    return StreamingResponse(
        iter_zip(extract_dir, workspace.resolve()),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted}",
            "Cache-Control": "no-store",
        },
    )


def preview_workspace_item(workspace: Path, rel_path: str):
    """普通预览：直接返回源文件，不做 Markdown 映射。"""
    workspace_root = workspace.resolve()
    target = resolve_inside_workspace(workspace, rel_path)
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在"
        )
    if target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="目录不支持预览,请下载",
        )

    mime = guess_mime(target)
    kind = preview_kind(mime)
    if kind is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="该类型不支持预览,请下载",
        )

    if kind in _PREVIEW_LIMITS:
        limit = _PREVIEW_LIMITS[kind]
        try:
            size = target.stat().st_size
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"读取文件元数据失败:{exc}",
            )
        if size > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"文件 {size / _MB:.1f} MB 超过 {kind} 类型预览上限 "
                       f"{limit // _MB} MB,请下载",
            )

    headers = inline_headers(mime)
    headers["X-Resolved-Preview-Path"] = quote(
        target.relative_to(workspace_root).as_posix(),
        safe="/._-",
    )
    return FileResponse(
        path=target,
        media_type=mime,
        headers=headers,
    )


def preview_workspace_markdown_item(workspace: Path, rel_path: str):
    """Markdown 编辑预览：将 Office/PDF 源文件映射到转换后的 Markdown。"""
    workspace_root = workspace.resolve()
    source_target = resolve_inside_workspace(workspace, rel_path)
    mapped_rel_path = resolve_preview_path(workspace, rel_path)
    if mapped_rel_path == rel_path and is_convertible_document(source_target):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_CONVERTED_MARKDOWN_MISSING,
        )
    target = (
        source_target
        if source_target == (workspace / mapped_rel_path).resolve()
        else resolve_inside_workspace(workspace, mapped_rel_path)
    )
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在"
        )
    if target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="目录不支持预览,请下载",
        )

    mime = guess_mime(target)
    kind = preview_kind(mime)
    if kind is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="该类型不支持预览,请下载",
        )

    if kind in _PREVIEW_LIMITS:
        limit = _PREVIEW_LIMITS[kind]
        try:
            size = target.stat().st_size
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"读取文件元数据失败:{exc}",
            )
        if size > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"文件 {size / _MB:.1f} MB 超过 {kind} 类型预览上限 "
                       f"{limit // _MB} MB,请下载",
            )

    headers = inline_headers(mime)
    headers["X-Resolved-Preview-Path"] = quote(
        target.relative_to(workspace_root).as_posix(),
        safe="/._-",
    )
    return FileResponse(
        path=target,
        media_type=mime,
        headers=headers,
    )
