"""对话「标记为有价值」→ 个人空间知识片段测试。

规格 §2.6 line157 / Phase 4 line1334：
POST /api/sessions/{id}/knowledge-fragments 将 assistant 回复正文落盘为
个人空间 ``{项目名}/知识片段/*.md``（无项目则落根 ``知识片段/``）。
"""

from pathlib import Path


async def _patch_workspace(monkeypatch, tmp_path, username="alice"):
    """把 user_workspace 重定向到 tmp_path，保证落盘隔离、自动清理。

    服务函数在调用时 ``from app.core.config import user_workspace``，
    故 monkeypatch 模块属性即可生效。
    """
    ws = tmp_path / username
    ws.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.config.user_workspace", lambda _u: ws)
    return ws


async def test_knowledge_fragment_no_project(logged_in_client, monkeypatch, tmp_path):
    """未绑项目的个人会话 → 知识片段落根 知识片段/。"""
    ws = await _patch_workspace(monkeypatch, tmp_path)
    sess = (await logged_in_client.post("/api/sessions", json={"title": "自由对话"})).json()

    res = await logged_in_client.post(
        f"/api/sessions/{sess['id']}/knowledge-fragments",
        json={"content": "这是一段有价值的洞察。\n\n数字意识是企业转型的前提。"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["project_name"] is None
    assert body["path"].startswith("知识片段/")
    assert body["filename"].endswith(".md")

    target = ws / body["path"]
    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert "数字意识是企业转型的前提" in text  # 正文
    assert "知识片段来源" in text  # 元数据 HTML 注释
    assert "自由对话" in text  # 来源会话标题


async def test_knowledge_fragment_with_project(logged_in_client, monkeypatch, tmp_path):
    """项目级会话 → 知识片段落 {项目名}/知识片段/（§6.2 资产矩阵）。"""
    ws = await _patch_workspace(monkeypatch, tmp_path)
    cid = (
        await logged_in_client.post("/api/customers", json={"name": "测试客户"})
    ).json()["id"]
    proj = (
        await logged_in_client.post(
            "/api/projects", json={"customer_id": cid, "name": "信创迁移项目"}
        )
    ).json()
    sess = (
        await logged_in_client.post("/api/sessions", json={"project_id": proj["id"]})
    ).json()

    res = await logged_in_client.post(
        f"/api/sessions/{sess['id']}/knowledge-fragments",
        json={"content": "客户决策链的关键节点是 CIO。"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["project_name"] == "信创迁移项目"
    assert body["path"].startswith("信创迁移项目/知识片段/")
    assert (ws / body["path"]).is_file()


async def test_knowledge_fragment_whitespace_content_400(
    logged_in_client, monkeypatch, tmp_path
):
    """纯空白内容 → 400（路由层 strip 后判空）。"""
    await _patch_workspace(monkeypatch, tmp_path)
    sess = (await logged_in_client.post("/api/sessions", json={})).json()
    res = await logged_in_client.post(
        f"/api/sessions/{sess['id']}/knowledge-fragments",
        json={"content": "   "},
    )
    assert res.status_code == 400
    assert "空" in res.json()["detail"]


async def test_knowledge_fragment_unknown_session_404(
    logged_in_client, monkeypatch, tmp_path
):
    await _patch_workspace(monkeypatch, tmp_path)
    res = await logged_in_client.post(
        "/api/sessions/nonexistent-session/knowledge-fragments",
        json={"content": "x"},
    )
    assert res.status_code == 404


async def test_knowledge_fragment_requires_login(client):
    res = await client.post(
        "/api/sessions/whatever/knowledge-fragments",
        json={"content": "x"},
    )
    assert res.status_code in (401, 403)


async def test_knowledge_fragment_sanitizes_title(
    logged_in_client, monkeypatch, tmp_path
):
    """标题含路径穿越/Windows 非法符 → 净化为安全文件名，不逃出工作区。"""
    ws = await _patch_workspace(monkeypatch, tmp_path)
    sess = (await logged_in_client.post("/api/sessions", json={})).json()
    res = await logged_in_client.post(
        f"/api/sessions/{sess['id']}/knowledge-fragments",
        json={"content": "正文内容", "title": "../../etc/passwd:bad*name?"},
    )
    assert res.status_code == 201
    body = res.json()
    assert "/" not in body["filename"]
    assert body["path"].startswith("知识片段/")
    assert ".." not in body["path"]
    target = ws / body["path"]
    assert target.is_file()
    assert target.resolve().is_relative_to(ws.resolve())


async def test_knowledge_fragment_unique_on_collision(
    logged_in_client, monkeypatch, tmp_path
):
    """同标题重复标记 → 唯一化，两文件并存且文件名不同。"""
    ws = await _patch_workspace(monkeypatch, tmp_path)
    sess = (await logged_in_client.post("/api/sessions", json={})).json()
    url = f"/api/sessions/{sess['id']}/knowledge-fragments"
    r1 = (
        await logged_in_client.post(
            url, json={"content": "同标题内容", "title": "同标题"}
        )
    ).json()
    r2 = (
        await logged_in_client.post(
            url, json={"content": "同标题内容", "title": "同标题"}
        )
    ).json()
    assert r1["filename"] != r2["filename"]
    assert (ws / r1["path"]).is_file()
    assert (ws / r2["path"]).is_file()
