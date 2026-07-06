async def test_health(client):
    """冒烟测试：验证健康检查接口返回正常"""
    res = await client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


async def test_lifespan_initializes_agent_workdirs(app_env, monkeypatch, tmp_path):
    """应用启动期应为已有 Agent 创建工作目录。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    from app import main
    from app.db import session as db_session

    app = main.build_app()
    # 显式触发 lifespan(ASGITransport 不会自动调用)
    async with app.router.lifespan_context(app):
        # 默认 Agent (id=1) 工作目录应已创建
        assert (tmp_path / "agent_workspaces" / "default-agent").is_dir()
    await db_session.engine.dispose()
