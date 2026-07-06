"""Office 旧格式文档转临时 PDF。"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

_OFFICE_TO_PDF_TIMEOUT_SECONDS = 180.0

logger = logging.getLogger(__name__)


class OfficePdfConversionError(RuntimeError):
    """本地 Office 转 PDF 失败。"""


def needs_pdf_intermediate(path: str | Path) -> bool:
    """MinerU 不直接支持旧版 .doc 时,先在本地转成临时 PDF。"""
    return Path(path).suffix.lower() == ".doc"


def _office_converter_binary() -> str:
    binary = shutil.which("libreoffice") or shutil.which("soffice")
    if not binary:
        logger.error("Office PDF converter is not available")
        raise OfficePdfConversionError("DOC 转 PDF 失败，请确认 LibreOffice 已安装")
    return binary


@asynccontextmanager
async def temporary_pdf_for_doc(source_path: Path) -> AsyncIterator[Path]:
    """把 .doc 转成临时 PDF,上下文退出后删除所有中间文件。"""
    source = source_path.resolve()
    if not source.exists() or not source.is_file():
        raise OfficePdfConversionError("DOC 转 PDF 失败，源文件不存在")

    converter = _office_converter_binary()
    with tempfile.TemporaryDirectory(prefix="doc-to-pdf-") as tmp_dir:
        output_dir = Path(tmp_dir)
        profile_dir = output_dir / "lo-profile"
        profile_dir.mkdir()
        proc = await asyncio.create_subprocess_exec(
            converter,
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            "--norestore",
            f"-env:UserInstallation={profile_dir.as_uri()}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(source),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=_OFFICE_TO_PDF_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.communicate()
            logger.exception("Office PDF conversion timed out")
            raise OfficePdfConversionError("DOC 转 PDF 失败，LibreOffice 执行超时") from exc
        if proc.returncode != 0:
            detail = (stderr or stdout).decode("utf-8", errors="ignore").strip()
            logger.error("Office PDF conversion process failed")
            raise OfficePdfConversionError(
                f"DOC 转 PDF 失败：{detail or 'LibreOffice 执行失败'}"
            )

        pdf_path = output_dir / f"{source.stem}.pdf"
        if not pdf_path.exists():
            candidates = sorted(output_dir.glob("*.pdf"))
            if not candidates:
                logger.error("Office PDF conversion produced no PDF")
                raise OfficePdfConversionError("DOC 转 PDF 失败，未生成 PDF 文件")
            pdf_path = candidates[0]

        yield pdf_path
