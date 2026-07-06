"""统一错误日志配置。"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_LEVEL = "ERROR"
DEFAULT_LOG_FILE = "logs/app.log"
DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 5

_CONFIGURED = False


def _int_from_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _level_from_env() -> int:
    raw = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
    level = logging.getLevelName(raw)
    return level if isinstance(level, int) else logging.ERROR


def configure_logging(*, force: bool = False) -> None:
    """配置控制台和 rotating file 错误日志。"""
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    level = _level_from_env()
    log_file = Path(os.getenv("LOG_FILE", DEFAULT_LOG_FILE))
    max_bytes = _int_from_env("LOG_MAX_BYTES", DEFAULT_LOG_MAX_BYTES)
    backup_count = _int_from_env("LOG_BACKUP_COUNT", DEFAULT_LOG_BACKUP_COUNT)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    _CONFIGURED = True
