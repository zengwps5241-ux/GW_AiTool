async def test_model_settings_returns_flat_models_and_thinking_levels(
    logged_in_client,
    monkeypatch,
):
    """前端只需要扁平模型名称列表和可选思考级别。"""
    monkeypatch.setenv("ANTHROPIC_PROVIDER_DEEPSEEK_AUTH_TOKEN", "deepseek-token")
    monkeypatch.setenv("ANTHROPIC_PROVIDER_DEEPSEEK_BASE_URL", "https://deepseek.example")
    monkeypatch.setenv(
        "ANTHROPIC_PROVIDER_DEEPSEEK_MODELS",
        '["deepseek-v4-pro", "deepseek-v4-flash"]',
    )
    monkeypatch.setenv("ANTHROPIC_PROVIDER_MINIMAX_AUTH_TOKEN", "minimax-token")
    monkeypatch.setenv("ANTHROPIC_PROVIDER_MINIMAX_BASE_URL", "https://minimax.example")
    monkeypatch.setenv("ANTHROPIC_PROVIDER_MINIMAX_MODELS", '["MiniMax-M2.7-highspeed"]')

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    res = await logged_in_client.get("/api/model-settings")

    assert res.status_code == 200
    assert res.json() == {
        "models": [
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "MiniMax-M2.7-highspeed",
        ],
        "thinking_levels": [
            {"value": "disabled", "label": "关闭"},
            {"value": "low", "label": "低"},
            {"value": "medium", "label": "中"},
            {"value": "high", "label": "高"},
        ],
        "default_model": "deepseek-v4-pro",
        "default_thinking_level": "low",
    }
