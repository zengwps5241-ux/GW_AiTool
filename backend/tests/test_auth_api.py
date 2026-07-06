from pathlib import Path
from unittest.mock import patch, AsyncMock


async def test_me_returns_extended_fields(logged_in_client):
    """/api/me 应返回扩展字段。"""
    res = await logged_in_client.get("/api/me")
    assert res.status_code == 200
    data = res.json()
    assert data["username"] == "alice"
    assert data["auth_source"] == "wechat_work"
    assert "display_name" in data


async def test_me_returns_role(logged_in_client):
    r = await logged_in_client.get("/api/me")
    assert r.status_code == 200
    data = r.json()
    assert "role" in data
    assert data["role"] == "user"


async def test_me_returns_admin_role_in_development(logged_in_client, monkeypatch):
    """开发环境下 /api/me 应把已登录用户展示为管理员。"""
    monkeypatch.setenv("APP_ENV", "development")

    from app.core.config import get_settings

    get_settings.cache_clear()

    r = await logged_in_client.get("/api/me")
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


async def test_login_endpoint_removed(client):
    """默认保护会先拦截匿名访问,避免暴露已删除 API 的路由状态。"""
    res = await client.post("/api/auth/login", json={"username": "alice", "password": "pass"})
    assert res.status_code == 401


async def test_config_endpoint_removed(client):
    """默认保护会先拦截匿名访问,避免暴露已删除 API 的路由状态。"""
    res = await client.get("/api/config")
    assert res.status_code == 401


async def test_wechat_work_qrcode_config(client, monkeypatch, app_env):
    """qrcode-config 端点应返回构造二维码所需的参数。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    res = await client.get("/api/auth/wechat-work/qrcode-config")
    assert res.status_code == 200
    data = res.json()
    assert data["appid"] == "test_corp"
    assert data["agentid"] == "test_agent"
    assert data["scope"] == "snsapi_privateinfo"
    assert "redirect_uri" in data
    assert "state" in data


async def test_wechat_work_callback_stores_code(client, monkeypatch, app_env):
    """企微回调应暂存 auth code,供前端轮询获取。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    # 获取二维码配置
    res = await client.get("/api/auth/wechat-work/qrcode-config")
    assert res.status_code == 200
    state = res.json()["state"]

    # 模拟企微回调
    res = await client.get(
        f"/api/auth/wechat-work/callback?code=test_code&state={state}",
        follow_redirects=False,
    )
    assert res.status_code == 200
    assert "扫码成功" in res.text

    # 前端轮询获取 code
    res = await client.get(f"/api/auth/wechat-work/poll-code?state={state}")
    assert res.status_code == 200
    assert res.json()["code"] == "test_code"

    # 再次轮询应 404(state 已被消费)
    res = await client.get(f"/api/auth/wechat-work/poll-code?state={state}")
    assert res.status_code == 404


async def test_wechat_work_callback_invalid_state(client, monkeypatch, app_env):
    """企微回调 state 不存在应 400。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    res = await client.get(
        "/api/auth/wechat-work/callback?code=test_code&state=wrong_state",
        follow_redirects=False,
    )
    assert res.status_code == 400


async def test_wechat_work_login_by_code_creates_user(client, monkeypatch, app_env):
    """用 auth code 登录应创建用户并设置 session。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    from app.modules.auth import wechat_work

    # 获取二维码配置并模拟回调
    res = await client.get("/api/auth/wechat-work/qrcode-config")
    state = res.json()["state"]
    await client.get(f"/api/auth/wechat-work/callback?code=login_code&state={state}")

    # 轮询获取 code
    res = await client.get(f"/api/auth/wechat-work/poll-code?state={state}")
    assert res.json()["code"] == "login_code"

    # 预置本地部门数据（登录流程不再实时调用企微 API）
    from app.db.session import async_session
    from app.models.department import Department
    async with async_session() as db:
        db.add(Department(id=1, name="研发部"))
        await db.commit()

    # 用 code 登录
    # auth/getuserdetail 返回敏感信息，user/get 补充 department/position
    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "auth_get_user_info", new=AsyncMock(return_value={
             "userid": "ZhangSan",
             "user_ticket": "ticket_zs",
         })), \
         patch.object(wechat_work, "auth_get_user_detail", new=AsyncMock(return_value={
             "userid": "ZhangSan",
             "name": "张三",
             "mobile": "13800138000",
             "email": "zhangsan@example.com",
             "avatar": "https://example.com/avatar.jpg",
         })), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": "ZhangSan",
             "department": [1],
             "position": "工程师",
         })):
        res = await client.post(
            "/api/auth/wechat-work/login-by-code",
            json={"code": "login_code"},
        )
        assert res.status_code == 200
        assert res.json()["success"] is True

    # 验证用户已创建并登录
    res = await client.get("/api/me")
    assert res.status_code == 200
    data = res.json()
    assert data["username"] == "ZhangSan"
    assert data["wechat_user_id"] == "ZhangSan"
    assert data["display_name"] == "张三"
    assert data["department"] == "研发部"
    assert data["position"] == "工程师"
    assert data["mobile"] == "13800138000"
    assert data["email"] == "zhangsan@example.com"
    assert data["auth_source"] == "wechat_work"


async def test_first_login_initializes_user_skill_creator(client, monkeypatch, app_env):
    """首次登录应初始化用户 skills 目录并复制内置 skill-creator。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")
    monkeypatch.setenv("CLAUDE_DATA_DIR", "claude_data")

    source = Path("claude_data/skills/skill-creator")
    (source / "nested").mkdir(parents=True)
    (source / "SKILL.md").write_text("# Skill Creator\n", encoding="utf-8")
    (source / "nested" / "template.txt").write_text("template", encoding="utf-8")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    from app.modules.auth import wechat_work

    res = await client.get("/api/auth/wechat-work/qrcode-config")
    state = res.json()["state"]
    await client.get(f"/api/auth/wechat-work/callback?code=skill_code&state={state}")
    res = await client.get(f"/api/auth/wechat-work/poll-code?state={state}")
    assert res.json()["code"] == "skill_code"

    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "auth_get_user_info", new=AsyncMock(return_value={
             "userid": "SkillUser",
             "user_ticket": "ticket_skill",
         })), \
         patch.object(wechat_work, "auth_get_user_detail", new=AsyncMock(return_value={
             "userid": "SkillUser",
             "name": "技能用户",
         })), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": "SkillUser",
             "department": [],
             "position": None,
         })):
        res = await client.post(
            "/api/auth/wechat-work/login-by-code",
            json={"code": "skill_code"},
        )

    assert res.status_code == 200
    target = Path("user_workspaces/SkillUser/.claude/skills/skill-creator")
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "# Skill Creator\n"
    assert (target / "nested" / "template.txt").read_text(encoding="utf-8") == "template"


async def test_wechat_work_login_by_code_denied_by_whitelist(client, monkeypatch, app_env):
    """未命中白名单时二维码登录应返回 403 且不创建用户。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    from sqlalchemy import select
    from app.db.session import async_session
    from app.models import LoginWhitelistUser, User
    from app.modules.auth import wechat_work

    async with async_session() as db:
        db.add(LoginWhitelistUser(name="允许用户"))
        await db.commit()

    res = await client.get("/api/auth/wechat-work/qrcode-config")
    state = res.json()["state"]
    await client.get(f"/api/auth/wechat-work/callback?code=deny_code&state={state}")
    res = await client.get(f"/api/auth/wechat-work/poll-code?state={state}")
    assert res.json()["code"] == "deny_code"

    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "auth_get_user_info", new=AsyncMock(return_value={
             "userid": "DeniedUser",
             "user_ticket": "ticket_denied",
         })), \
         patch.object(wechat_work, "auth_get_user_detail", new=AsyncMock(return_value={
             "userid": "DeniedUser",
             "name": "拒绝用户",
         })), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": "DeniedUser",
             "name": "拒绝用户",
             "department": [],
             "position": None,
         })):
        res = await client.post(
            "/api/auth/wechat-work/login-by-code",
            json={"code": "deny_code"},
        )

    assert res.status_code == 403
    assert res.json()["detail"] == "当前账号未在登录白名单中，请联系管理员"
    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "DeniedUser"))
        assert result.scalar_one_or_none() is None


async def test_development_environment_bypasses_wechat_login_whitelist(monkeypatch):
    """开发环境应在查询登录白名单前直接允许企微登录。"""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    from app.modules.auth.login_whitelist import LoginWhitelistCheckResult

    reload(core_config)
    reload(auth_routes)

    check = AsyncMock(return_value=LoginWhitelistCheckResult(False, "not_matched"))
    monkeypatch.setattr(auth_routes, "check_wechat_login_allowed", check)

    await auth_routes._ensure_wechat_login_allowed(
        None,
        "DevUser",
        {"name": "开发用户", "department": []},
    )

    check.assert_not_awaited()


async def test_wechat_work_login_by_code_skips_whitelist_in_development(
    client, monkeypatch, app_env
):
    """开发环境下二维码登录不受登录白名单限制。"""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    from sqlalchemy import select
    from app.db.session import async_session
    from app.models import LoginWhitelistUser, User
    from app.modules.auth import wechat_work

    async with async_session() as db:
        db.add(LoginWhitelistUser(name="允许用户"))
        await db.commit()

    res = await client.get("/api/auth/wechat-work/qrcode-config")
    state = res.json()["state"]
    await client.get(f"/api/auth/wechat-work/callback?code=dev_code&state={state}")
    res = await client.get(f"/api/auth/wechat-work/poll-code?state={state}")
    assert res.json()["code"] == "dev_code"

    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "auth_get_user_info", new=AsyncMock(return_value={
             "userid": "DevUser",
             "user_ticket": "ticket_dev",
         })), \
         patch.object(wechat_work, "auth_get_user_detail", new=AsyncMock(return_value={
             "userid": "DevUser",
             "name": "开发用户",
         })), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": "DevUser",
             "name": "开发用户",
             "department": [],
             "position": None,
         })):
        res = await client.post(
            "/api/auth/wechat-work/login-by-code",
            json={"code": "dev_code"},
        )

    assert res.status_code == 200
    assert res.json()["success"] is True
    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "DevUser"))
        assert result.scalar_one_or_none() is not None


async def test_wechat_work_login_by_code_allows_department_descendant(client, monkeypatch, app_env):
    """命中白名单部门的后代部门时应允许二维码登录。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    from app.db.session import async_session
    from app.models import Department, LoginWhitelistDepartment
    from app.modules.auth import wechat_work

    async with async_session() as db:
        db.add_all([
            Department(id=1, name="集团", parent_id=0),
            Department(id=2, name="研发部", parent_id=1),
            Department(id=3, name="平台组", parent_id=2),
            LoginWhitelistDepartment(department_id=2),
        ])
        await db.commit()

    res = await client.get("/api/auth/wechat-work/qrcode-config")
    state = res.json()["state"]
    await client.get(f"/api/auth/wechat-work/callback?code=allow_code&state={state}")
    res = await client.get(f"/api/auth/wechat-work/poll-code?state={state}")
    assert res.json()["code"] == "allow_code"

    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "auth_get_user_info", new=AsyncMock(return_value={
             "userid": "DeptUser",
             "user_ticket": "ticket_dept",
         })), \
         patch.object(wechat_work, "auth_get_user_detail", new=AsyncMock(return_value={
             "userid": "DeptUser",
             "name": "部门用户",
         })), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": "DeptUser",
             "name": "部门用户",
             "department": [3],
             "position": "工程师",
         })):
        res = await client.post(
            "/api/auth/wechat-work/login-by-code",
            json={"code": "allow_code"},
        )

    assert res.status_code == 200
    assert res.json()["success"] is True


async def test_wechat_work_login_by_code_fallback_name(client, monkeypatch, app_env):
    """auth_get_user_detail 缺少 name 时，应从 user/get 补充。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    from app.modules.auth import wechat_work

    res = await client.get("/api/auth/wechat-work/qrcode-config")
    state = res.json()["state"]
    await client.get(f"/api/auth/wechat-work/callback?code=fallback_code&state={state}")

    res = await client.get(f"/api/auth/wechat-work/poll-code?state={state}")
    assert res.json()["code"] == "fallback_code"

    # 预置本地部门数据
    from app.db.session import async_session
    from app.models.department import Department
    async with async_session() as db:
        db.add(Department(id=1, name="测试部"))
        await db.commit()

    # auth_get_user_detail 不返回 name，由 get_user_detail 补充
    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "auth_get_user_info", new=AsyncMock(return_value={
             "userid": "NoNameUser",
             "user_ticket": "ticket_nn",
         })), \
         patch.object(wechat_work, "auth_get_user_detail", new=AsyncMock(return_value={
             "userid": "NoNameUser",
             "mobile": "13800138000",
             # 注意:没有 name
         })), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": "NoNameUser",
             "name": "补全姓名",
             "department": [1],
             "position": "测试工程师",
         })):
        res = await client.post(
            "/api/auth/wechat-work/login-by-code",
            json={"code": "fallback_code"},
        )
        assert res.status_code == 200

    res = await client.get("/api/me")
    assert res.status_code == 200
    data = res.json()
    assert data["username"] == "NoNameUser"
    assert data["display_name"] == "补全姓名"
    assert data["department"] == "测试部"


async def test_wechat_work_config_returns_mode(client, monkeypatch, app_env):
    """config 端点应返回当前登录模式。"""
    monkeypatch.setenv("WECHAT_WORK_LOGIN_MODE", "sso")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    res = await client.get("/api/auth/wechat-work/config")
    assert res.status_code == 200
    assert res.json()["mode"] == "sso"


async def test_wechat_work_authorize_sso_mode(client, monkeypatch, app_env):
    """sso 模式下 authorize 端点应重定向到企微 SSO 页面。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")
    monkeypatch.setenv("WECHAT_WORK_LOGIN_MODE", "sso")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    res = await client.get("/api/auth/wechat-work/authorize", follow_redirects=False)
    assert res.status_code == 307
    location = res.headers["location"]
    assert "login.work.weixin.qq.com" in location
    assert "login_type=CorpApp" in location


async def test_wechat_work_authorize_404_in_qrcode_mode(client, monkeypatch, app_env):
    """qrcode 模式下访问 authorize 端点应 404。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")
    monkeypatch.setenv("WECHAT_WORK_LOGIN_MODE", "qrcode")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    res = await client.get("/api/auth/wechat-work/authorize", follow_redirects=False)
    assert res.status_code == 404


async def test_wechat_work_callback_sso_creates_user(client, monkeypatch, app_env):
    """sso 模式下 callback 应直接创建用户并重定向到首页。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")
    monkeypatch.setenv("WECHAT_WORK_LOGIN_MODE", "sso")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    from app.modules.auth import wechat_work

    # 获取 SSO state
    with patch("app.api.routes.auth.secrets.token_urlsafe", return_value="sso_state"):
        res = await client.get("/api/auth/wechat-work/authorize", follow_redirects=False)
        assert res.status_code == 307

    # 预置本地部门数据
    from app.db.session import async_session
    from app.models.department import Department
    async with async_session() as db:
        db.add(Department(id=2, name="产品部"))
        await db.commit()

    # 模拟企微回调
    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "get_user_id_by_code", new=AsyncMock(return_value="SSOUser")), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": "SSOUser",
             "name": "SSO 用户",
             "department": [2],
             "position": "产品经理",
             "mobile": "13900139000",
             "email": "sso@example.com",
             "avatar": None,
         })):
        res = await client.get(
            "/api/auth/wechat-work/callback?code=sso_code&state=sso_state",
            follow_redirects=False,
        )
        assert res.status_code == 307
        assert res.headers["location"] == "/"

    # 验证用户已创建并登录
    res = await client.get("/api/me")
    assert res.status_code == 200
    data = res.json()
    assert data["username"] == "SSOUser"
    assert data["display_name"] == "SSO 用户"
    assert data["department"] == "产品部"
    assert data["auth_source"] == "wechat_work"


async def test_wechat_work_callback_sso_whitelist_denied_redirects_to_spa(
    client, monkeypatch, app_env
):
    """SSO 白名单拒绝应回到 SPA 根路径，由前端展示友好提示。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_AGENT_ID", "test_agent")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")
    monkeypatch.setenv("WECHAT_WORK_LOGIN_MODE", "sso")

    from importlib import reload
    from app.core import config as core_config
    from app.api.routes import auth as auth_routes
    reload(core_config)
    reload(auth_routes)

    from app.db.session import async_session
    from app.models import LoginWhitelistUser
    from app.modules.auth import wechat_work

    async with async_session() as db:
        db.add(LoginWhitelistUser(name="允许用户"))
        await db.commit()

    with patch("app.api.routes.auth.secrets.token_urlsafe", return_value="sso_state"):
        res = await client.get("/api/auth/wechat-work/authorize", follow_redirects=False)
        assert res.status_code == 307

    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "get_user_id_by_code", new=AsyncMock(return_value="DeniedSSOUser")), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": "DeniedSSOUser",
             "name": "拒绝用户",
             "department": [],
             "position": None,
         })):
        res = await client.get(
            "/api/auth/wechat-work/callback?code=sso_code&state=sso_state",
            follow_redirects=False,
        )

    assert res.status_code == 307
    assert res.headers["location"] == "/?error=login_whitelist_denied"
