from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile, ZipInfo

import httpx

from app.core.utils import safe_filename

MAX_ZIP_ENTRIES = 1_000
MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_ZIP_FILE_SIZE_BYTES = 128 * 1024 * 1024
_ZIP_COPY_CHUNK_SIZE = 1024 * 1024

logger = logging.getLogger(__name__)
_request_limiters: dict[int, asyncio.Semaphore] = {}


class MineruConversionError(RuntimeError):
    pass


@dataclass(frozen=True)
class MineruMarkdownResult:
    markdown_path: Path
    markdown_rel_path: str
    asset_dir: Path | None
    extract_dir: Path


async def convert_document_to_markdown(
    source_path: Path,
    output_root: Path,
    api_url: str,
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None = None,
    max_concurrent_requests: int = 2,
) -> MineruMarkdownResult:
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.",
            suffix=".tmp",
            dir=output_root.parent,
        )
    )
    try:
        archive_bytes = await _request_conversion_with_limit(
            source_path=source_path,
            api_url=api_url,
            timeout_seconds=timeout_seconds,
            transport=transport,
            max_concurrent_requests=max_concurrent_requests,
        )
        _extract_zip_safely(archive_bytes, staging_root)
        _flatten_single_top_dir(staging_root)
        staging_markdown_path = _find_markdown_path(staging_root)
        markdown_rel_to_extract = staging_markdown_path.relative_to(staging_root)
        _publish_staging_output(staging_root, output_root)
        markdown_path = output_root / markdown_rel_to_extract
        asset_dir = markdown_path.parent / "images"
        return MineruMarkdownResult(
            markdown_path=markdown_path,
            markdown_rel_path=_workspace_relative_path(markdown_path),
            asset_dir=asset_dir if asset_dir.is_dir() else None,
            extract_dir=output_root,
        )
    except BaseException:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise


def _get_request_limiter(max_concurrent_requests: int) -> asyncio.Semaphore:
    """按配置值复用进程内全局信号量，限制同时打到 MinerU 的请求数。"""
    limit = max(1, int(max_concurrent_requests))
    limiter = _request_limiters.get(limit)
    if limiter is None:
        limiter = asyncio.Semaphore(limit)
        _request_limiters[limit] = limiter
    return limiter


async def _request_conversion_with_limit(
    source_path: Path,
    api_url: str,
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None,
    max_concurrent_requests: int,
) -> bytes:
    limiter = _get_request_limiter(max_concurrent_requests)
    async with limiter:
        return await _request_conversion(
            source_path=source_path,
            api_url=api_url,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )


async def _request_conversion(
    source_path: Path,
    api_url: str,
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None,
) -> bytes:
    data = {
        "image_analysis": "true",
        "return_md": "true",
        "return_images": "true",
        "table_enable": "true",
        "response_format_zip": "true",
        "return_original_file": "false",
        "formula_enable": "true",
    }
    try:
        async with httpx.AsyncClient(transport=transport, timeout=timeout_seconds) as client:
            with source_path.open("rb") as source_file:
                response = await client.post(
                    api_url,
                    data=data,
                    files={"files": (source_path.name, source_file)},
                )
    except httpx.HTTPError as exc:
        logger.exception("MinerU request failed")
        raise MineruConversionError(f"MinerU request failed: {exc}") from exc

    if not 200 <= response.status_code < 300:
        logger.error("MinerU request returned non-success status")
        raise MineruConversionError(
            f"MinerU conversion failed with HTTP status {response.status_code}"
        )
    return response.content


def _safe_zip_entry_name(name: str) -> str:
    """对 zip 条目名中的每个路径组件进行安全清理，保留目录结构。"""
    normalized = name.replace("\\", "/")
    if normalized.startswith("/"):
        raise MineruConversionError(f"unsafe zip entry: {name}")
    parts = normalized.split("/")
    # 显式拒绝路径穿越段，避免被 safe_filename 静默替换为占位名后逃过相对路径校验。
    if ".." in parts:
        raise MineruConversionError(f"unsafe zip entry: {name}")
    safe_parts = [safe_filename(part) for part in parts if part]
    return "/".join(safe_parts)


def _extract_zip_safely(archive_bytes: bytes, output_root: Path) -> None:
    try:
        with ZipFile(BytesIO(archive_bytes)) as archive:
            _validate_zip_limits(archive.infolist())
            root = output_root.resolve()
            extracted_total = 0
            for info in archive.infolist():
                safe_name = _safe_zip_entry_name(info.filename)
                target = (output_root / safe_name).resolve()
                if not target.is_relative_to(root):
                    raise MineruConversionError(f"unsafe zip entry: {info.filename}")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as destination:
                    extracted_total += _copy_limited_zip_member(
                        source,
                        destination,
                        info.filename,
                    )
                if extracted_total > MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES:
                    raise MineruConversionError("zip uncompressed size exceeds limit")
    except BadZipFile as exc:
        logger.exception("MinerU returned invalid zip")
        raise MineruConversionError("invalid zip returned by MinerU") from exc


def _validate_zip_limits(infos: list[ZipInfo]) -> None:
    if len(infos) > MAX_ZIP_ENTRIES:
        raise MineruConversionError(f"zip entry count exceeds limit: {len(infos)}")

    total_size = 0
    for info in infos:
        if info.is_dir():
            continue
        if info.file_size > MAX_ZIP_FILE_SIZE_BYTES:
            raise MineruConversionError(f"zip file too large: {info.filename}")
        total_size += info.file_size
        if total_size > MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES:
            raise MineruConversionError("zip uncompressed size exceeds limit")


def _copy_limited_zip_member(source, destination, filename: str) -> int:
    written = 0
    while True:
        chunk = source.read(_ZIP_COPY_CHUNK_SIZE)
        if not chunk:
            break
        written += len(chunk)
        if written > MAX_ZIP_FILE_SIZE_BYTES:
            raise MineruConversionError(f"zip file too large: {filename}")
        destination.write(chunk)
    return written


def _publish_staging_output(staging_root: Path, output_root: Path) -> None:
    backup_root = output_root.parent / f".{output_root.name}.{uuid.uuid4().hex}.backup"
    moved_existing = False
    if output_root.exists():
        output_root.rename(backup_root)
        moved_existing = True

    try:
        staging_root.rename(output_root)
    except BaseException:
        if moved_existing and not output_root.exists():
            backup_root.rename(output_root)
        raise
    else:
        if moved_existing:
            shutil.rmtree(backup_root, ignore_errors=True)


def _flatten_single_top_dir(staging_root: Path) -> None:
    """如果 staging_root 下只有一个子目录且包含 hybrid_auto，把其内容上移一层。

    MinerU 返回的 zip 通常会带一层基于文件名的顶级目录，与最终的 output_root
    同名，造成 ``<output_root>/<同名目录>/hybrid_auto/*.md`` 这种冗余结构。
    扁平化后变成 ``<output_root>/hybrid_auto/*.md``。
    """
    children = [p for p in staging_root.iterdir() if not p.name.startswith(".")]
    if len(children) != 1 or not children[0].is_dir():
        return
    top_dir = children[0]
    if not (top_dir / "hybrid_auto").is_dir():
        return
    for item in list(top_dir.iterdir()):
        shutil.move(str(item), str(staging_root / item.name))
    top_dir.rmdir()


def _find_markdown_path(output_root: Path) -> Path:
    # 扁平化后的结构: <output_root>/hybrid_auto/*.md
    direct = sorted(output_root.glob("hybrid_auto/*.md"))
    if direct:
        return direct[0]

    # 兼容未扁平化的结构: <output_root>/*/hybrid_auto/*.md
    nested = sorted(output_root.glob("*/hybrid_auto/*.md"))
    if nested:
        return nested[0]

    markdown_files = sorted(output_root.rglob("*.md"))
    if len(markdown_files) == 1:
        return markdown_files[0]
    raise MineruConversionError("MinerU zip did not contain a markdown file")


def _workspace_relative_path(path: Path) -> str:
    parts = path.parts
    if ".markdown" in parts:
        start = parts.index(".markdown")
        return Path(*parts[start:]).as_posix()

    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()
