"""Default authentication guard for API routes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select

from app.db.session import async_session
from app.models import User

_PUBLIC_API_PATHS = {
    "/api/health",
    "/api/auth/logout",
    "/api/auth/register",
    "/api/auth/login",
    # DEPRECATED: 企微认证路径，保留以备未来扩展
    "/api/auth/wechat-work/config",
    "/api/auth/wechat-work/authorize",
    "/api/auth/wechat-work/qrcode-config",
    "/api/auth/wechat-work/callback",
    "/api/auth/wechat-work/poll-code",
    "/api/auth/wechat-work/login-by-code",
    "/api/workspace/internal-preview-file",
    "/api/team-spaces/workspace/internal-preview-file",
}


def _is_public_api_request(request: Request) -> bool:
    if request.method == "OPTIONS":
        return True
    path = request.url.path.rstrip("/") or "/"
    return path in _PUBLIC_API_PATHS


def install_api_auth_guard(app: FastAPI) -> None:
    """Require a valid logged-in session for every non-public /api request."""

    @app.middleware("http")
    async def api_auth_guard(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if not path.startswith("/api/") or _is_public_api_request(request):
            return await call_next(request)

        user_id = request.session.get("user_id")
        if user_id is None:
            return JSONResponse(
                {"detail": "未登录"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()

        if user is None:
            request.session.clear()
            return JSONResponse(
                {"detail": "用户不存在"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        request.state.user = user
        return await call_next(request)
