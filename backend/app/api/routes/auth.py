"""认证路由。"""

import logging
import secrets
import time
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings, is_development_environment, user_workspace
from app.core import security
from app.db.session import get_db
from app.api.deps import current_user
from app.models import User
from app.modules.auth import wechat_work
from app.modules.auth.departments import get_department_names
from app.modules.auth.login_whitelist import (
    WHITELIST_DENIED_MESSAGE,
    check_wechat_login_allowed,
)
from app.schemas import UserOut

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

# 企微扫码登录临时存储: state -> (code, expire_at)
# code 为 None 表示已注册 state 但尚未收到回调
_auth_code_store: dict[str, tuple[str | None, float]] = {}


def _cleanup_expired_codes() -> None:
    """清理已过期的临时授权码。"""
    now = time.time()
    expired = [k for k, (_, exp) in _auth_code_store.items() if exp < now]
    for k in expired:
        del _auth_code_store[k]


async def _sync_user_from_detail(
    db: AsyncSession,
    user_id: str,
    user_detail: dict,
) -> User:
    """根据企微用户详情查找或创建/更新本地用户。"""
    # 从本地部门表获取部门名称
    dept_ids: list[int] = []
    dept_names: list[str] = []
    if user_detail.get("department"):
        dept_ids = [int(did) for did in user_detail["department"]]
        dept_names = await get_department_names(db, user_detail["department"])

    # 查找或创建用户
    result = await db.execute(
        select(User).where(User.wechat_user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            username=user_id,
            wechat_user_id=user_id,
            password_hash=security.hash_password(secrets.token_urlsafe(32)),
            display_name=user_detail.get("name") or user_id,
            avatar_url=user_detail.get("avatar") or None,
            department="/".join(dept_names) if dept_names else None,
            department_ids=dept_ids if dept_ids else None,
            position=user_detail.get("position") or None,
            mobile=user_detail.get("mobile") or None,
            email=user_detail.get("email") or None,
            auth_source="wechat_work",
        )
        db.add(user)
    else:
        user.display_name = user_detail.get("name") or user_id
        user.avatar_url = user_detail.get("avatar") or None
        user.department = "/".join(dept_names) if dept_names else None
        user.department_ids = dept_ids if dept_ids else None
        user.position = user_detail.get("position") or None
        user.mobile = user_detail.get("mobile") or None
        user.email = user_detail.get("email") or None

    return user


async def _ensure_wechat_login_allowed(
    db: AsyncSession,
    user_id: str,
    user_detail: dict,
) -> None:
    """在写入本地用户前执行企微登录白名单校验。"""
    department_ids = [int(did) for did in user_detail.get("department") or []]
    result = await check_wechat_login_allowed(
        db,
        name=user_detail.get("name"),
        department_ids=department_ids,
    )
    if result.allowed:
        return
    logger.warning(
        "企微用户未命中登录白名单: userid=%s name=%s department_ids=%s",
        user_id,
        user_detail.get("name"),
        department_ids,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=WHITELIST_DENIED_MESSAGE,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> UserOut:
    # 开发环境默认普通用户拥有管理员权限,便于本地调试管理功能;super 角色保留。
    role = user.role
    if is_development_environment() and role == "user":
        role = "admin"
    return UserOut(
        id=user.id,
        username=user.username,
        wechat_user_id=user.wechat_user_id,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        department=user.department,
        department_ids=user.department_ids,
        position=user.position,
        mobile=user.mobile,
        email=user.email,
        auth_source=user.auth_source,
        role=role,
    )


@router.get("/auth/wechat-work/config")
async def wechat_work_config() -> dict:
    """返回当前企微登录模式配置,供前端适配。"""
    settings = get_settings()
    return {"mode": settings.wechat_work_login_mode}


@router.get("/auth/wechat-work/authorize")
async def wechat_work_authorize(request: Request) -> RedirectResponse:
    """企微 SSO 登录入口。仅在 sso 模式下有效。"""
    settings = get_settings()
    if settings.wechat_work_login_mode != "sso":
        raise HTTPException(status_code=404, detail="SSO 登录未启用")

    state = secrets.token_urlsafe(32)
    request.session["wechat_work_state"] = state

    redirect_uri = str(request.base_url).rstrip("/") + "/api/auth/wechat-work/callback"
    url = (
        "https://login.work.weixin.qq.com/wwlogin/sso/login"
        f"?login_type=CorpApp"
        f"&appid={urllib.parse.quote(settings.wechat_work_corp_id)}"
        f"&agentid={urllib.parse.quote(settings.wechat_work_agent_id)}"
        f"&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
        f"&state={state}"
    )
    return RedirectResponse(url)


@router.get("/auth/wechat-work/qrcode-config")
async def wechat_work_qrcode_config(request: Request) -> dict:
    """返回前端构造自建二维码所需的参数。仅在 qrcode 模式下有效。"""
    settings = get_settings()
    if settings.wechat_work_login_mode != "qrcode":
        raise HTTPException(status_code=404, detail="二维码登录未启用")

    state = secrets.token_urlsafe(32)
    expire = time.time() + 300  # 5 分钟有效
    _cleanup_expired_codes()
    _auth_code_store[state] = (None, expire)

    redirect_uri = str(request.base_url).rstrip("/") + "/api/auth/wechat-work/callback"
    return {
        "appid": settings.wechat_work_corp_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "agentid": settings.wechat_work_agent_id,
        "scope": "snsapi_privateinfo",
    }


@router.get("/auth/wechat-work/callback")
async def wechat_work_callback(
    request: Request,
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """处理企微 OAuth 回调。根据登录模式分发到不同处理逻辑。"""
    settings = get_settings()

    if settings.wechat_work_login_mode == "sso":
        return await _sso_callback(request, code, state, db)
    return await _qrcode_callback(code, state)


async def _sso_callback(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession,
) -> RedirectResponse:
    """SSO 模式:校验 session state,直接登录并重定向到首页。"""
    expected_state = request.session.get("wechat_work_state")
    if not expected_state or expected_state != state:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid state"
        )
    del request.session["wechat_work_state"]

    try:
        access_token = await wechat_work.get_access_token(
            get_settings().wechat_work_corp_id,
            get_settings().wechat_work_secret,
        )
        user_id = await wechat_work.get_user_id_by_code(code, access_token)
        user_detail = await wechat_work.get_user_detail(user_id, access_token)

        try:
            await _ensure_wechat_login_allowed(db, user_id, user_detail)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                return RedirectResponse(url="/?error=login_whitelist_denied")
            raise
        user = await _sync_user_from_detail(db, user_id, user_detail)
        await db.commit()
        await db.refresh(user)
        user_workspace(user.username)
        request.session["user_id"] = user.id
        return RedirectResponse(url="/")

    except Exception:
        logger.exception("企微 SSO 登录失败")
        return RedirectResponse(url="/?error=wechat_auth_failed")


async def _qrcode_callback(code: str, state: str) -> HTMLResponse:
    """二维码模式:暂存 auth code,返回提示页面。"""
    _cleanup_expired_codes()

    if state not in _auth_code_store:
        return HTMLResponse(
            content="<h2>无效的请求</h2><p>请返回浏览器重新扫码。</p>",
            status_code=400,
        )

    stored_code, expire = _auth_code_store[state]
    if time.time() > expire:
        del _auth_code_store[state]
        return HTMLResponse(
            content="<h2>请求已过期</h2><p>请返回浏览器重新扫码。</p>",
            status_code=400,
        )

    # 暂存 code,供前端轮询获取
    _auth_code_store[state] = (code, expire)

    return HTMLResponse(
        content=(
            "<!DOCTYPE html>"
            '<html><head><meta charset="utf-8"><title>扫码成功</title></head>'
            '<body style="text-align:center;padding-top:80px;font-family:sans-serif;">'
            "<h2>扫码成功</h2>"
            "<p>请回到浏览器页面继续操作</p>"
            "</body></html>"
        )
    )


@router.get("/auth/wechat-work/poll-code")
async def wechat_work_poll_code(state: str) -> dict:
    """前端轮询接口:等待用户扫码后获取 auth code。仅在 qrcode 模式下有效。"""
    settings = get_settings()
    if settings.wechat_work_login_mode != "qrcode":
        raise HTTPException(status_code=404, detail="二维码登录未启用")

    _cleanup_expired_codes()

    if state not in _auth_code_store:
        raise HTTPException(status_code=404, detail="state not found")

    code, expire = _auth_code_store[state]
    if time.time() > expire:
        del _auth_code_store[state]
        raise HTTPException(status_code=410, detail="expired")

    if code is None:
        raise HTTPException(status_code=204, detail="no code yet")

    del _auth_code_store[state]
    return {"code": code}


@router.post("/auth/wechat-work/login-by-code")
async def wechat_work_login_by_code(
    request: Request,
    payload: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """用 auth code 完成登录,通过 auth/getuserdetail 获取敏感信息。仅在 qrcode 模式下有效。"""
    settings = get_settings()
    if settings.wechat_work_login_mode != "qrcode":
        raise HTTPException(status_code=404, detail="二维码登录未启用")

    code = payload.get("code")
    if not code or not isinstance(code, str):
        raise HTTPException(status_code=400, detail="缺少 code")

    try:
        access_token = await wechat_work.get_access_token(
            settings.wechat_work_corp_id,
            settings.wechat_work_secret,
        )

        # 获取 user_id 和 user_ticket
        auth_info = await wechat_work.auth_get_user_info(code, access_token)
        user_id = auth_info.get("userid")
        user_ticket = auth_info.get("user_ticket")

        if not user_id:
            raise RuntimeError(f"企微返回数据中缺少 userid: {auth_info}")

        # 用 user_ticket 获取敏感信息（手机、邮箱、头像等）
        user_detail: dict = {}
        if user_ticket:
            user_detail = await wechat_work.auth_get_user_detail(
                user_ticket, access_token
            )

        # auth/getuserdetail 不返回 department/position，复用 user/get 补充
        full_detail = await wechat_work.get_user_detail(user_id, access_token)
        user_detail["department"] = full_detail.get("department")
        user_detail["position"] = full_detail.get("position")
        # 如果 auth_get_user_detail 没有返回 name，用 user/get 补充
        if not user_detail.get("name"):
            user_detail["name"] = full_detail.get("name")

        await _ensure_wechat_login_allowed(db, user_id, user_detail)
        user = await _sync_user_from_detail(db, user_id, user_detail)
        await db.commit()
        await db.refresh(user)
        user_workspace(user.username)
        request.session["user_id"] = user.id
        return {"success": True}

    except HTTPException:
        raise
    except Exception:
        logger.exception("企微登录失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录失败",
        )
