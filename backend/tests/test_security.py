from app.core.security import hash_password, verify_password
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient


def test_hash_and_verify():
    pw = "hunter2"
    h = hash_password(pw)
    assert h != pw
    assert verify_password(pw, h) is True
    assert verify_password("wrong", h) is False


async def test_api_routes_require_login_by_default(app_env):
    from app.api.router import router as api_router
    from app.main import build_app

    router = APIRouter()

    @router.get("/api/security-test/default-protected")
    async def default_protected() -> dict:
        return {"ok": True}

    api_router.include_router(router)
    app = build_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/security-test/default-protected")
    assert response.status_code == 401


async def test_api_health_remains_public(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
