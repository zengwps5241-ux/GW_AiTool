"""文件预览: MIME 推断、类型分类、大小限制、响应头。"""

import mimetypes
from pathlib import Path

from fastapi import HTTPException, status

_OFFICE_SUFFIXES = {
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
}

_CONVERTIBLE_SUFFIXES = _OFFICE_SUFFIXES | {".pdf"}

# 显式覆盖 mimetypes 的代码/配置后缀
_TEXT_PLAIN_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".md", ".markdown", ".rst",
    ".yaml", ".yml", ".toml", ".ini", ".conf", ".cfg",
    ".log", ".env", ".sh", ".bash", ".zsh", ".fish",
    ".sql", ".css", ".scss", ".less", ".vue",
    ".go", ".rs", ".java", ".kt", ".swift",
    ".c", ".cc", ".cpp", ".h", ".hh", ".hpp",
    ".txt",
}

_MB = 1024 * 1024
_PREVIEW_LIMITS = {
    "text": 2 * _MB,
    "image": 10 * _MB,
    "pdf": 20 * _MB,
}


def guess_mime(path: str | Path) -> str:
    """推断 MIME。代码/配置后缀强制 text/plain;charset=utf-8。"""
    suffix = Path(path).suffix.lower()
    if suffix in _TEXT_PLAIN_SUFFIXES:
        return "text/plain; charset=utf-8"
    guess, _ = mimetypes.guess_type(str(path))
    if not guess:
        return "application/octet-stream"
    if guess in ("application/json", "application/xml", "text/xml"):
        return f"{guess}; charset=utf-8"
    if guess.startswith("text/") and "charset" not in guess:
        return f"{guess}; charset=utf-8"
    return guess


def is_convertible_document(path: str | Path) -> bool:
    """判断源文件是否需要转换成 Markdown 后才能预览/编辑。"""
    return Path(path).suffix.lower() in _CONVERTIBLE_SUFFIXES


def is_text_preview_path(path: str | Path) -> bool:
    """判断路径是否属于可直接作为文本预览/编辑的文件。"""
    suffix = Path(path).suffix.lower()
    mime = guess_mime(path)
    base = mime.split(";", 1)[0].strip().lower()
    return (
        suffix in _TEXT_PLAIN_SUFFIXES
        or base.startswith("text/")
        or base in ("application/json", "application/xml", "text/xml")
    )


def preview_kind(mime: str) -> str | None:
    """把 MIME 归到预览分类。返回 None 表示不支持预览。"""
    base = mime.split(";", 1)[0].strip().lower()
    if base.startswith("text/") or base in ("application/json", "application/xml"):
        return "text"
    if base.startswith("image/"):
        return "image"
    if base == "application/pdf":
        return "pdf"
    if base.startswith("audio/") or base.startswith("video/"):
        return "media"
    return None


def inline_headers(mime: str) -> dict[str, str]:
    """预览响应头。"""
    return {
        "Content-Disposition": "inline",
        # 工作空间文件可在线编辑，预览必须每次反映磁盘最新内容。
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox; frame-ancestors 'self'",
    }
