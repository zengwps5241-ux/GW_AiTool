import os
from pathlib import Path

import pytest


def test_settings_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "corp123")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "agent456")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "secret789")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    s = core_config.get_settings()
    assert s.app_env == "production"
    assert s.app_secret == "s"
    assert s.anthropic_auth_token == "t"
    assert s.anthropic_base_url == "https://example.com"
    assert s.anthropic_model == ""
    # 从环境变量读取
    assert s.database_url == "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent"
    assert s.workspaces_dir == Path("user_workspaces")
    assert s.claude_data_dir == Path("claude_data")
    assert s.feedback_uploads_dir == Path("feedback_uploads")


def test_redis_settings_defaults(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
    settings = get_settings()

    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.team_space_file_lock_ttl_seconds == 1800
    assert settings.team_space_file_lock_cleanup_grace_seconds == 300


def test_settings_reads_anthropic_model(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "corp123")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "agent456")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "secret789")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    assert core_config.get_settings().anthropic_model == "claude-sonnet-4-5"


def test_model_providers_are_discovered_from_env(monkeypatch, tmp_path):
    """多供应商配置应从 ANTHROPIC_PROVIDER_<KEY>_* 自动发现。"""
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "corp123")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "agent456")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "secret789")
    monkeypatch.setenv("ANTHROPIC_PROVIDER_DEEPSEEK_AUTH_TOKEN", "deepseek-token")
    monkeypatch.setenv("ANTHROPIC_PROVIDER_DEEPSEEK_BASE_URL", "https://deepseek.example")
    monkeypatch.setenv(
        "ANTHROPIC_PROVIDER_DEEPSEEK_MODELS",
        '["deepseek-v4-pro", "deepseek-v4-flash"]',
    )
    monkeypatch.setenv("ANTHROPIC_PROVIDER_MINIMAX_AUTH_TOKEN", "minimax-token")
    monkeypatch.setenv("ANTHROPIC_PROVIDER_MINIMAX_BASE_URL", "https://minimax.example")
    monkeypatch.setenv("ANTHROPIC_PROVIDER_MINIMAX_MODELS", "MiniMax-M2.7-highspeed")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    providers = core_config.get_model_providers()
    assert [p.key for p in providers] == ["DEEPSEEK", "MINIMAX"]
    assert core_config.get_available_models() == [
        "deepseek-v4-pro",
        "deepseek-v4-flash",
        "MiniMax-M2.7-highspeed",
    ]
    selected = core_config.resolve_model_provider("MiniMax-M2.7-highspeed")
    assert selected is not None
    assert selected.auth_token == "minimax-token"
    assert selected.base_url == "https://minimax.example"


def test_legacy_anthropic_settings_are_used_as_default_provider(monkeypatch, tmp_path):
    """旧单组 ANTHROPIC_* 配置应继续可用，降低部署升级成本。"""
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "legacy-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://legacy.example")
    monkeypatch.setenv("ANTHROPIC_MODEL", '["claude-sonnet-4-5", "claude-haiku-4-5"]')
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "corp123")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "agent456")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "secret789")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    assert core_config.get_available_models() == ["claude-sonnet-4-5", "claude-haiku-4-5"]
    selected = core_config.resolve_model_provider("claude-sonnet-4-5")
    assert selected is not None
    assert selected.key == "DEFAULT"
    assert selected.auth_token == "legacy-token"


def test_apply_environment_sets_claude_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "corp123")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "agent456")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "secret789")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    core_config.apply_environment()
    assert Path(os.environ["CLAUDE_CONFIG_DIR"]).name == "claude_data"
    assert os.environ["ANTHROPIC_AUTH_TOKEN"] == "t"
    assert os.environ["ANTHROPIC_BASE_URL"] == "https://example.com"
    assert (tmp_path / "feedback_uploads").is_dir()


async def test_agent_workdirs_dir_defaults_and_created(monkeypatch, tmp_path):
    """启动期 apply_environment 应创建 agent_workdirs_dir。"""
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "corp123")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "agent456")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "secret789")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    s = core_config.get_settings()
    assert s.agent_workdirs_dir == Path("agent_workspaces")  # 默认相对路径

    core_config.apply_environment()
    assert (tmp_path / "agent_workspaces").is_dir()


def test_mineru_settings_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "corp123")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "agent456")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "secret789")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    s = core_config.get_settings()
    assert s.mineru_api_url == "http://192.168.125.11:8000/file_parse"
    assert s.mineru_timeout_seconds == 180.0
    assert s.mineru_max_concurrent_requests == 2


def test_mineru_max_concurrent_requests_can_be_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "corp123")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "agent456")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "secret789")
    monkeypatch.setenv("MINERU_MAX_CONCURRENT_REQUESTS", "5")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    assert core_config.get_settings().mineru_max_concurrent_requests == 5


def test_user_workspace_creates_claude_skills_dir_when_skill_creator_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "corp123")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "agent456")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "secret789")
    monkeypatch.setenv("CLAUDE_DATA_DIR", "claude_data")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    workspace = core_config.user_workspace("alice")

    assert (workspace / ".claude" / "skills").is_dir()
    assert not (workspace / ".claude" / "skills" / "skill-creator").exists()


def test_office_preview_settings_default_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "corp123")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "agent456")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "secret789")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    s = core_config.get_settings()
    assert s.app_internal_base_url == ""
    assert s.kkfileview_base_url == ""


def test_office_preview_settings_can_be_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "corp123")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "agent456")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "secret789")
    monkeypatch.setenv("APP_INTERNAL_BASE_URL", "http://backend:8000/")
    monkeypatch.setenv("KKFILEVIEW_BASE_URL", "http://kkfileview:8012/")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    s = core_config.get_settings()
    assert s.app_internal_base_url == "http://backend:8000/"
    assert s.kkfileview_base_url == "http://kkfileview:8012/"


def test_wechat_work_requires_all_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "corp123")
    # 故意缺少 AGENT_ID 和 SECRET
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    with pytest.raises(RuntimeError) as exc_info:
        core_config.apply_environment()
    assert "WECHAT_WORK_AGENT_ID" in str(exc_info.value)
    assert "WECHAT_WORK_SECRET" in str(exc_info.value)
