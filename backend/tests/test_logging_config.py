import logging
from logging.handlers import RotatingFileHandler


def test_configure_logging_adds_console_and_rotating_file_handlers(tmp_path, monkeypatch):
    from app.core import logging as app_logging

    log_file = tmp_path / "logs" / "app.log"
    monkeypatch.setenv("LOG_FILE", str(log_file))
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_MAX_BYTES", raising=False)
    monkeypatch.delenv("LOG_BACKUP_COUNT", raising=False)

    app_logging.configure_logging(force=True)

    root = logging.getLogger()
    assert root.level == logging.ERROR
    assert any(isinstance(handler, logging.StreamHandler) for handler in root.handlers)
    file_handlers = [
        handler for handler in root.handlers
        if isinstance(handler, RotatingFileHandler)
    ]
    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == str(log_file)
    assert file_handlers[0].maxBytes == 10 * 1024 * 1024
    assert file_handlers[0].backupCount == 5
    assert log_file.parent.exists()


def test_configure_logging_uses_environment_overrides(tmp_path, monkeypatch):
    from app.core import logging as app_logging

    log_file = tmp_path / "custom.log"
    monkeypatch.setenv("LOG_FILE", str(log_file))
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("LOG_MAX_BYTES", "12345")
    monkeypatch.setenv("LOG_BACKUP_COUNT", "7")

    app_logging.configure_logging(force=True)

    root = logging.getLogger()
    file_handler = next(
        handler for handler in root.handlers
        if isinstance(handler, RotatingFileHandler)
    )
    assert root.level == logging.WARNING
    assert file_handler.baseFilename == str(log_file)
    assert file_handler.maxBytes == 12345
    assert file_handler.backupCount == 7


def test_lifespan_configures_logging_before_environment(monkeypatch):
    from app import main

    calls: list[str] = []

    def fake_configure_logging():
        calls.append("logging")

    def fake_apply_environment():
        calls.append("environment")
        raise RuntimeError("stop after ordering check")

    monkeypatch.setattr(main.app_logging, "configure_logging", fake_configure_logging)
    monkeypatch.setattr(main.config, "apply_environment", fake_apply_environment)

    import asyncio
    import pytest

    async def run_lifespan():
        async with main._lifespan(None):
            pass

    with pytest.raises(RuntimeError, match="stop after ordering check"):
        asyncio.run(run_lifespan())

    assert calls == ["logging", "environment"]
