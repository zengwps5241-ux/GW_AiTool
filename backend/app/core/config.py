"""配置与启动环境注入。"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover - pydantic-settings 通常会带入 python-dotenv
    dotenv_values = None


class Settings(BaseSettings):
    """从 .env 与环境变量读取配置。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "production"
    app_secret: str = ""
    anthropic_auth_token: str = ""
    anthropic_base_url: str = ""
    anthropic_model: str = ""
    zhipu_web_search_api_key: str = ""

    database_url: str
    workspaces_dir: Path = Path("user_workspaces")
    claude_data_dir: Path = Path("claude_data")
    agent_workdirs_dir: Path = Path("agent_workspaces")
    feedback_uploads_dir: Path = Path("feedback_uploads")
    mineru_api_url: str = "http://192.168.125.11:8000/file_parse"
    mineru_timeout_seconds: float = 180.0
    mineru_max_concurrent_requests: int = Field(default=2, ge=1)
    redis_url: str = "redis://localhost:6379/0"
    team_space_file_lock_ttl_seconds: int = Field(default=1800, ge=1)
    team_space_file_lock_cleanup_grace_seconds: int = Field(default=300, ge=0)

    # 企业微信配置(必填)
    wechat_work_corp_id: str = ""
    wechat_work_agent_id: str = ""
    wechat_work_secret: str = ""

    # 企微登录方式: qrcode(自建二维码,默认) 或 sso(企微 SSO 跳转)
    wechat_work_login_mode: str = "qrcode"

    # Office 预览: kkFileView 仅由后端内网访问,不要暴露给用户浏览器
    app_internal_base_url: str = ""
    kkfileview_base_url: str = ""


@dataclass(frozen=True)
class ModelProvider:
    """一组兼容 Anthropic 网关协议的模型供应商配置。"""

    key: str
    auth_token: str
    base_url: str
    models: tuple[str, ...]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def is_development_environment() -> bool:
    """判断是否处于开发环境,用于放宽本地调试权限。"""
    return get_settings().app_env.strip().lower() == "development"


def _merged_env() -> dict[str, str]:
    """合并 .env 与真实环境变量；真实环境变量优先。"""
    values: dict[str, str] = {}
    if dotenv_values is not None and Path(".env").exists():
        for key, value in dotenv_values(".env").items():
            if value is not None:
                values[key] = value
    values.update(os.environ)
    return values


def _parse_model_list(raw: str) -> tuple[str, ...]:
    """支持 JSON 数组、逗号分隔和单个模型名三种写法。"""
    text = raw.strip()
    if not text:
        return ()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            return tuple(str(item).strip() for item in parsed if str(item).strip())
    return tuple(part.strip() for part in text.split(",") if part.strip())


def get_model_providers() -> list[ModelProvider]:
    """读取所有模型供应商；新增供应商只需增加匹配前缀的环境变量。"""
    env = _merged_env()
    provider_keys = sorted(
        key.removeprefix("ANTHROPIC_PROVIDER_").removesuffix("_MODELS")
        for key in env
        if key.startswith("ANTHROPIC_PROVIDER_") and key.endswith("_MODELS")
    )

    providers: list[ModelProvider] = []
    for key in provider_keys:
        auth_token = env.get(f"ANTHROPIC_PROVIDER_{key}_AUTH_TOKEN", "").strip()
        base_url = env.get(f"ANTHROPIC_PROVIDER_{key}_BASE_URL", "").strip()
        models = _parse_model_list(env.get(f"ANTHROPIC_PROVIDER_{key}_MODELS", ""))
        if auth_token and base_url and models:
            providers.append(
                ModelProvider(
                    key=key,
                    auth_token=auth_token,
                    base_url=base_url,
                    models=models,
                )
            )

    settings = get_settings()
    legacy_models = _parse_model_list(settings.anthropic_model)
    if settings.anthropic_auth_token and settings.anthropic_base_url and legacy_models:
        providers.append(
            ModelProvider(
                key="DEFAULT",
                auth_token=settings.anthropic_auth_token,
                base_url=settings.anthropic_base_url,
                models=legacy_models,
            )
        )
    return providers


def get_available_models() -> list[str]:
    """返回前端展示用的扁平模型名称列表，不暴露供应商信息。"""
    models: list[str] = []
    seen: set[str] = set()
    for provider in get_model_providers():
        for model in provider.models:
            if model not in seen:
                models.append(model)
                seen.add(model)
    return models


def resolve_model_provider(model: str | None) -> ModelProvider | None:
    """按模型名找到供应商；未选择模型时使用第一组可用供应商。"""
    providers = get_model_providers()
    if not model:
        return providers[0] if providers else None
    for provider in providers:
        if model in provider.models:
            return provider
    return None


def apply_environment() -> None:
    """把必要变量注入 os.environ,必须在 import claude_agent_sdk 前调用。"""
    s = get_settings()
    default_provider = resolve_model_provider(None)
    default_auth_token = default_provider.auth_token if default_provider else s.anthropic_auth_token
    default_base_url = default_provider.base_url if default_provider else s.anthropic_base_url
    missing = [k for k, v in {
        "APP_SECRET": s.app_secret,
        "ANTHROPIC_AUTH_TOKEN": default_auth_token,
        "ANTHROPIC_BASE_URL": default_base_url,
    }.items() if not v]
    if missing:
        raise RuntimeError(f"缺少必需的环境变量: {', '.join(missing)}")

    # 企业微信配置校验(无条件必填)
    missing_wechat = [
        k for k, v in {
            "WECHAT_WORK_CORP_ID": s.wechat_work_corp_id,
            "WECHAT_WORK_AGENT_ID": s.wechat_work_agent_id,
            "WECHAT_WORK_SECRET": s.wechat_work_secret,
        }.items() if not v
    ]
    if missing_wechat:
        raise RuntimeError(
            f"缺少必需的企业微信环境变量: {', '.join(missing_wechat)}"
        )

    s.claude_data_dir.mkdir(parents=True, exist_ok=True)
    s.workspaces_dir.mkdir(parents=True, exist_ok=True)
    s.agent_workdirs_dir.mkdir(parents=True, exist_ok=True)
    s.feedback_uploads_dir.mkdir(parents=True, exist_ok=True)
    os.environ["CLAUDE_CONFIG_DIR"] = str(s.claude_data_dir.resolve())
    os.environ["ANTHROPIC_AUTH_TOKEN"] = default_auth_token
    os.environ["ANTHROPIC_BASE_URL"] = default_base_url


def user_workspace(username: str) -> Path:
    """返回该用户的 workspace 目录,不存在则创建。"""
    p = get_settings().workspaces_dir / username
    should_initialize = not p.exists()
    p.mkdir(parents=True, exist_ok=True)
    if should_initialize:
        _initialize_user_workspace(p)
    return p


def _initialize_user_workspace(workspace: Path) -> None:
    """初始化用户个人空间，预置可由用户自维护的内置技能。"""
    settings = get_settings()
    skills_dir = workspace / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    source = settings.claude_data_dir / "skills" / "skill-creator"
    if not source.is_dir():
        return

    target = skills_dir / "skill-creator"
    if target.exists():
        return
    shutil.copytree(source, target)
