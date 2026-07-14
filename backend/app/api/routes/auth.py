"""认证路由。

自建注册登录体系（手机号/用户名+密码），企微认证代码已注释保留。
"""

import logging
import secrets
import time
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings, is_development_environment, user_workspace
from app.core import security
from app.db.session import get_db
from app.api.deps import current_user, require_admin
from app.models import User
from app.schemas.auth import (
    UserOut,
    RegisterRequest,
    LoginRequest,
    PendingUserOut,
    ApproveRequest,
)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

# DEPRECATED: 企微扫码登录临时存储，保留以备未来扩展
# _auth_code_store: dict[str, tuple[str | None, float]] = {}


# ─── 自建认证 API ───────────────────────────────────────────


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """用户自助注册。默认 status=pending_approval，需管理员审批。"""
    # 校验：手机号和用户名至少提供一个
    if not payload.username and not payload.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名和手机号至少提供一个",
        )

    # 校验用户名唯一
    if payload.username:
        existing = await db.execute(
            select(User).where(User.username == payload.username)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="用户名已存在",
            )

    # 校验手机号唯一
    if payload.phone:
        existing = await db.execute(
            select(User).where(User.phone == payload.phone)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="手机号已注册",
            )

    # 创建用户
    user = User(
        username=payload.username or f"user_{payload.phone}",
        password_hash=security.hash_password(payload.password),
        phone=payload.phone,
        display_name=payload.display_name or payload.username or payload.phone,
        status="pending_approval",
        registration_source="self_register",
        auth_source="local",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("用户注册: username=%s phone=%s", user.username, user.phone)
    return {
        "success": True,
        "message": "注册成功，请等待管理员审批",
        "user_id": user.id,
    }


@router.post("/auth/login")
async def login(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """用户登录。支持手机号或用户名 + 密码。"""
    # 按手机号或用户名查找用户
    result = await db.execute(
        select(User).where(
            or_(User.phone == payload.login, User.username == payload.login)
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # 校验密码
    if not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # 校验用户状态
    if user.status == "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号待审批，请联系管理员",
        )
    if user.status == "disabled":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用，请联系管理员",
        )

    # 设置 session
    request.session["user_id"] = user.id
    user_workspace(user.username)

    # 更新最后登录时间（M6.4 用户管理，随下方审计日志一并 commit）
    from datetime import datetime, timezone

    user.last_login = datetime.now(timezone.utc)

    logger.info("用户登录: username=%s", user.username)
    # 审计埋点（决策 #64）
    from app.modules.audit.service import log_audit

    await log_audit(
        db,
        user.id,
        "login",
        "user",
        str(user.id),
        detail={"username": user.username},
        ip_address=request.client.host if request.client else None,
    )
    return {"success": True}


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> Response:
    """用户登出，清除 session。"""
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> UserOut:
    """获取当前登录用户信息。"""
    # 开发环境默认普通用户拥有管理员权限,便于本地调试管理功能;super 角色保留。
    role = user.role
    if is_development_environment() and role == "user":
        role = "admin"
    return UserOut(
        id=user.id,
        username=user.username,
        phone=user.phone,
        status=user.status,
        registration_source=user.registration_source,
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


# ─── 管理员审批 API ─────────────────────────────────────────


@router.get("/admin/pending-users", response_model=list[PendingUserOut])
async def list_pending_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[PendingUserOut]:
    """管理员获取待审批用户列表。"""
    result = await db.execute(
        select(User)
        .where(User.status == "pending_approval")
        .order_by(User.created_at.asc())
    )
    users = result.scalars().all()
    return [
        PendingUserOut(
            id=u.id,
            username=u.username,
            phone=u.phone,
            display_name=u.display_name,
            status=u.status,
            registration_source=u.registration_source,
            created_at=u.created_at.isoformat() if u.created_at else None,
        )
        for u in users
    ]


@router.post("/admin/approve-user/{user_id}")
async def approve_user(
    user_id: int,
    payload: ApproveRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """管理员审批用户：通过或驳回。"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在"
        )

    if user.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"用户当前状态为 {user.status}，无法审批",
        )

    if payload.action == "approve":
        user.status = "active"
        logger.info("管理员 %s 审批通过用户 %s", admin.username, user.username)
    else:
        user.status = "disabled"
        logger.info("管理员 %s 驳回用户 %s", admin.username, user.username)

    await db.commit()
    # 审计埋点（决策 #64）
    from app.modules.audit.service import log_audit

    action = "approve" if payload.action == "approve" else "reject"
    await log_audit(
        db,
        admin.id,
        action,
        "user",
        str(user.id),
        detail={"before": {"status": "pending_approval"},
                "after": {"status": user.status}},
    )
    return {
        "success": True,
        "user_id": user.id,
        "status": user.status,
    }


# ─── DEPRECATED: 企微认证路由，保留以备未来扩展 ──────────────
# 以下代码为原企业微信认证路由，已切换为自建注册登录体系。
# 如需恢复企微认证，取消注释即可。

# _auth_code_store: dict[str, tuple[str | None, float]] = {}
#
# def _cleanup_expired_codes() -> None:
#     """清理已过期的临时授权码。"""
#     now = time.time()
#     expired = [k for k, (_, exp) in _auth_code_store.items() if exp < now]
#     for k in expired:
#         del _auth_code_store[k]
#
#
# async def _sync_user_from_detail(
#     db: AsyncSession,
#     user_id: str,
#     user_detail: dict,
# ) -> User:
#     """根据企微用户详情查找或创建/更新本地用户。"""
#     from app.modules.auth.departments import get_department_names
#     dept_ids: list[int] = []
#     dept_names: list[str] = []
#     if user_detail.get("department"):
#         dept_ids = [int(did) for did in user_detail["department"]]
#         dept_names = await get_department_names(db, user_detail["department"])
#     result = await db.execute(
#         select(User).where(User.wechat_user_id == user_id)
#     )
#     user = result.scalar_one_or_none()
#     if user is None:
#         user = User(
#             username=user_id,
#             wechat_user_id=user_id,
#             password_hash=security.hash_password(secrets.token_urlsafe(32)),
#             display_name=user_detail.get("name") or user_id,
#             avatar_url=user_detail.get("avatar") or None,
#             department="/".join(dept_names) if dept_names else None,
#             department_ids=dept_ids if dept_ids else None,
#             position=user_detail.get("position") or None,
#             mobile=user_detail.get("mobile") or None,
#             email=user_detail.get("email") or None,
#             auth_source="wechat_work",
#         )
#         db.add(user)
#     else:
#         user.display_name = user_detail.get("name") or user_id
#         user.avatar_url = user_detail.get("avatar") or None
#         user.department = "/".join(dept_names) if dept_names else None
#         user.department_ids = dept_ids if dept_ids else None
#         user.position = user_detail.get("position") or None
#         user.mobile = user_detail.get("mobile") or None
#         user.email = user_detail.get("email") or None
#     return user
#
#
# async def _ensure_wechat_login_allowed(
#     db: AsyncSession,
#     user_id: str,
#     user_detail: dict,
# ) -> None:
#     """在写入本地用户前执行企微登录白名单校验。"""
#     from app.modules.auth.login_whitelist import (
#         WHITELIST_DENIED_MESSAGE,
#         check_wechat_login_allowed,
#     )
#     department_ids = [int(did) for did in user_detail.get("department") or []]
#     result = await check_wechat_login_allowed(
#         db,
#         name=user_detail.get("name"),
#         department_ids=department_ids,
#     )
#     if result.allowed:
#         return
#     logger.warning(
#         "企微用户未命中登录白名单: userid=%s name=%s department_ids=%s",
#         user_id,
#         user_detail.get("name"),
#         department_ids,
#     )
#     raise HTTPException(
#         status_code=status.HTTP_403_FORBIDDEN,
#         detail=WHITELIST_DENIED_MESSAGE,
#     )
#
#
# @router.get("/auth/wechat-work/config")
# async def wechat_work_config() -> dict:
#     """返回当前企微登录模式配置,供前端适配。"""
#     settings = get_settings()
#     return {"mode": settings.wechat_work_login_mode}
#
#
# @router.get("/auth/wechat-work/authorize")
# async def wechat_work_authorize(request: Request) -> RedirectResponse:
#     """企微 SSO 登录入口。仅在 sso 模式下有效。"""
#     settings = get_settings()
#     if settings.wechat_work_login_mode != "sso":
#         raise HTTPException(status_code=404, detail="SSO 登录未启用")
#     state = secrets.token_urlsafe(32)
#     request.session["wechat_work_state"] = state
#     redirect_uri = str(request.base_url).rstrip("/") + "/api/auth/wechat-work/callback"
#     url = (
#         "https://login.work.weixin.qq.com/wwlogin/sso/login"
#         f"?login_type=CorpApp"
#         f"&appid={urllib.parse.quote(settings.wechat_work_corp_id)}"
#         f"&agentid={urllib.parse.quote(settings.wechat_work_agent_id)}"
#         f"&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
#         f"&state={state}"
#     )
#     return RedirectResponse(url)
#
#
# @router.get("/auth/wechat-work/qrcode-config")
# async def wechat_work_qrcode_config(request: Request) -> dict:
#     """返回前端构造自建二维码所需的参数。仅在 qrcode 模式下有效。"""
#     settings = get_settings()
#     if settings.wechat_work_login_mode != "qrcode":
#         raise HTTPException(status_code=404, detail="二维码登录未启用")
#     state = secrets.token_urlsafe(32)
#     expire = time.time() + 300
#     _cleanup_expired_codes()
#     _auth_code_store[state] = (None, expire)
#     redirect_uri = str(request.base_url).rstrip("/") + "/api/auth/wechat-work/callback"
#     return {
#         "appid": settings.wechat_work_corp_id,
#         "redirect_uri": redirect_uri,
#         "state": state,
#         "agentid": settings.wechat_work_agent_id,
#         "scope": "snsapi_privateinfo",
#     }
#
#
# @router.get("/auth/wechat-work/callback")
# async def wechat_work_callback(
#     request: Request,
#     code: str = "",
#     state: str = "",
#     db: AsyncSession = Depends(get_db),
# ) -> Response:
#     """处理企微 OAuth 回调。根据登录模式分发到不同处理逻辑。"""
#     settings = get_settings()
#     if settings.wechat_work_login_mode == "sso":
#         return await _sso_callback(request, code, state, db)
#     return await _qrcode_callback(code, state)
#
#
# async def _sso_callback(
#     request: Request, code: str, state: str, db: AsyncSession) -> RedirectResponse:
#     expected_state = request.session.get("wechat_work_state")
#     if not expected_state or expected_state != state:
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid state")
#     del request.session["wechat_work_state"]
#     try:
#         from app.modules.auth import wechat_work
#         access_token = await wechat_work.get_access_token(
#             get_settings().wechat_work_corp_id, get_settings().wechat_work_secret,
#         )
#         user_id = await wechat_work.get_user_id_by_code(code, access_token)
#         user_detail = await wechat_work.get_user_detail(user_id, access_token)
#         try:
#             await _ensure_wechat_login_allowed(db, user_id, user_detail)
#         except HTTPException as exc:
#             if exc.status_code == status.HTTP_403_FORBIDDEN:
#                 return RedirectResponse(url="/?error=login_whitelist_denied")
#             raise
#         user = await _sync_user_from_detail(db, user_id, user_detail)
#         await db.commit()
#         await db.refresh(user)
#         user_workspace(user.username)
#         request.session["user_id"] = user.id
#         return RedirectResponse(url="/")
#     except Exception:
#         logger.exception("企微 SSO 登录失败")
#         return RedirectResponse(url="/?error=wechat_auth_failed")
#
#
# async def _qrcode_callback(code: str, state: str) -> HTMLResponse:
#     _cleanup_expired_codes()
#     if state not in _auth_code_store:
#         return HTMLResponse(content="<h2>无效的请求</h2>", status_code=400)
#     stored_code, expire = _auth_code_store[state]
#     if time.time() > expire:
#         del _auth_code_store[state]
#         return HTMLResponse(content="<h2>请求已过期</h2>", status_code=400)
#     _auth_code_store[state] = (code, expire)
#     return HTMLResponse(content="<!DOCTYPE html><html><body><h2>扫码成功</h2><p>请回到浏览器页面继续操作</p></body></html>")
#
#
# @router.get("/auth/wechat-work/poll-code")
# async def wechat_work_poll_code(state: str) -> dict:
#     settings = get_settings()
#     if settings.wechat_work_login_mode != "qrcode":
#         raise HTTPException(status_code=404, detail="二维码登录未启用")
#     _cleanup_expired_codes()
#     if state not in _auth_code_store:
#         raise HTTPException(status_code=404, detail="state not found")
#     code, expire = _auth_code_store[state]
#     if time.time() > expire:
#         del _auth_code_store[state]
#         raise HTTPException(status_code=410, detail="expired")
#     if code is None:
#         raise HTTPException(status_code=204, detail="no code yet")
#     del _auth_code_store[state]
#     return {"code": code}
#
#
# @router.post("/auth/wechat-work/login-by-code")
# async def wechat_work_login_by_code(
#     request: Request, payload: dict, db: AsyncSession = Depends(get_db),
# ) -> dict:
#     settings = get_settings()
#     if settings.wechat_work_login_mode != "qrcode":
#         raise HTTPException(status_code=404, detail="二维码登录未启用")
#     code = payload.get("code")
#     if not code or not isinstance(code, str):
#         raise HTTPException(status_code=400, detail="缺少 code")
#     try:
#         from app.modules.auth import wechat_work
#         access_token = await wechat_work.get_access_token(
#             settings.wechat_work_corp_id, settings.wechat_work_secret,
#         )
#         auth_info = await wechat_work.auth_get_user_info(code, access_token)
#         user_id = auth_info.get("userid")
#         user_ticket = auth_info.get("user_ticket")
#         if not user_id:
#             raise RuntimeError(f"企微返回数据中缺少 userid: {auth_info}")
#         user_detail: dict = {}
#         if user_ticket:
#             user_detail = await wechat_work.auth_get_user_detail(user_ticket, access_token)
#         full_detail = await wechat_work.get_user_detail(user_id, access_token)
#         user_detail["department"] = full_detail.get("department")
#         user_detail["position"] = full_detail.get("position")
#         if not user_detail.get("name"):
#             user_detail["name"] = full_detail.get("name")
#         await _ensure_wechat_login_allowed(db, user_id, user_detail)
#         user = await _sync_user_from_detail(db, user_id, user_detail)
#         await db.commit()
#         await db.refresh(user)
#         user_workspace(user.username)
#         request.session["user_id"] = user.id
#         return {"success": True}
#     except HTTPException:
#         raise
#     except Exception:
#         logger.exception("企微登录失败")
#         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="登录失败")
