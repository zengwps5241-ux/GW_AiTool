import pytest


@pytest.mark.asyncio
async def test_team_member_can_read_tree(logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "资料"})
    space_id = created.json()["id"]

    r = await logged_in_client.get(f"/api/team-spaces/{space_id}/workspace/tree")

    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_reader_cannot_create_file(logged_in_client, other_logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "资料"})
    space_id = created.json()["id"]
    me = (await other_logged_in_client.get("/api/me")).json()
    await logged_in_client.post(f"/api/team-spaces/{space_id}/members", json={"user_id": me["id"], "role": "reader"})

    r = await other_logged_in_client.post(
        f"/api/team-spaces/{space_id}/workspace/file",
        json={"path": "README.md", "kind": "file", "content": "hello"},
    )

    assert r.status_code == 403
    assert "只读成员" in r.json()["detail"]


@pytest.mark.asyncio
async def test_team_office_preview_builds_kkfileview_request(logged_in_client, monkeypatch):
    import httpx

    from app.core.config import get_settings
    from app.modules.team_spaces.service import team_workspace

    settings = get_settings()
    monkeypatch.setattr(settings, "app_internal_base_url", "http://backend:8000")
    monkeypatch.setattr(settings, "kkfileview_base_url", "http://kkfileview:8012")
    created = await logged_in_client.post("/api/team-spaces", json={"name": "资料"})
    space_id = created.json()["id"]
    root = team_workspace(space_id)
    (root / "a.docx").write_bytes(b"PK")
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            text="<html><script src=\"/js/app.js\"></script><link href='xlsx/css/luckysheet.css' /></html>",
            headers={"content-type": "text/html"},
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("app.modules.workspace.office_preview.create_proxy_client", lambda: httpx.AsyncClient(transport=transport))

    r = await logged_in_client.get(f"/api/team-spaces/{space_id}/workspace/office-preview", params={"path": "a.docx"})

    assert r.status_code == 200
    assert seen["url"].startswith("http://kkfileview:8012/onlinePreview?url=")
    assert f"/api/team-spaces/{space_id}/workspace/kkfileview/js/app.js" in r.text
    assert f"/api/team-spaces/{space_id}/workspace/kkfileview/xlsx/css/luckysheet.css" in r.text


@pytest.mark.asyncio
async def test_team_internal_preview_file_uses_signed_token_without_login(client):
    from app.core.config import get_settings
    from app.modules.team_spaces.service import team_workspace
    from app.modules.workspace.office_preview import create_file_token

    settings = get_settings()
    space_id = 42
    rel_path = "docs/a.docx"
    root = team_workspace(space_id)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / rel_path).write_bytes(b"PK")
    token = create_file_token(f"team:{space_id}", rel_path, secret=settings.app_secret, ttl_seconds=300)

    r = await client.get("/api/team-spaces/workspace/internal-preview-file", params={"token": token})

    assert r.status_code == 200
    assert r.content == b"PK"
