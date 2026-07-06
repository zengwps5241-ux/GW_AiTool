"""工作空间文件树 API 测试。"""


async def test_workspace_requires_auth(client):
    """未登录用户不能列出工作区。"""
    r = await client.get("/api/workspace/tree")
    assert r.status_code == 401


async def test_workspace_empty(logged_in_client):
    """新建用户工作区会展示可维护的 .claude/skills 目录。"""
    c = logged_in_client
    r = await c.get("/api/workspace/tree")
    assert r.status_code == 200
    body = r.json()
    assert [item["name"] for item in body] == [".claude"]
    assert body[0]["type"] == "dir"
    assert [item["name"] for item in body[0]["children"]] == ["skills"]


async def test_workspace_lists_uploaded_file(logged_in_client):
    """上传文件后,工作空间能在 uploads/ 子目录中看到该文件。"""
    c = logged_in_client
    # 先上传一个文件,触发 uploads 子目录创建
    files = {"files": ("note.txt", b"hi", "text/plain")}
    up = await c.post("/api/uploads", files=files)
    assert up.status_code == 200
    uploaded_path = up.json()["items"][0]["path"]

    r = await c.get("/api/workspace/tree")
    assert r.status_code == 200
    tree = r.json()
    # 无 target_dir 时文件落在工作区根目录
    root_paths = [n["path"] for n in tree]
    assert uploaded_path in root_paths


async def test_workspace_skips_hidden_and_junk(logged_in_client):
    """除 .claude 外的隐藏文件、node_modules、__pycache__ 等垃圾目录不出现在响应中。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / ".secret").write_text("nope")
    (ws / "visible.txt").write_text("ok")
    (ws / "node_modules").mkdir()
    (ws / "node_modules" / "junk").write_text("x")
    (ws / "__pycache__").mkdir()
    (ws / "__pycache__" / "x.pyc").write_text("y")

    c = logged_in_client
    r = await c.get("/api/workspace/tree")
    assert r.status_code == 200
    names = [n["name"] for n in r.json()]
    assert ".secret" not in names
    assert ".claude" in names
    assert "node_modules" not in names
    assert "__pycache__" not in names
    assert "visible.txt" in names


async def test_workspace_tree_hides_markdown_dir(logged_in_client):
    """.markdown 转换目录不出现在工作区树中。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / ".markdown" / "a").mkdir(parents=True)
    (ws / ".markdown" / "a" / "a.md").write_text("# hidden", encoding="utf-8")

    r = await logged_in_client.get("/api/workspace/tree")

    assert r.status_code == 200
    assert ".markdown" not in [node["name"] for node in r.json()]


async def test_workspace_tree_carries_agent_path_for_converted_files(logged_in_client):
    """被 MinerU 转换过的源文件在工作区树中携带 ``agent_path`` 指向 markdown。"""
    from app.core.config import user_workspace
    from app.modules.workspace.markdown_index import add_markdown_mapping

    ws = user_workspace("alice")
    (ws / "uploads").mkdir()
    (ws / "uploads" / "a.pdf").write_bytes(b"%PDF")
    (ws / "uploads" / "plain.txt").write_text("untouched")
    (ws / ".markdown" / "a" / "hybrid_auto").mkdir(parents=True)
    (ws / ".markdown" / "a" / "hybrid_auto" / "a.md").write_text(
        "# a", encoding="utf-8"
    )
    add_markdown_mapping(
        ws,
        source_path="uploads/a.pdf",
        source_name="a.pdf",
        markdown_path=".markdown/a/hybrid_auto/a.md",
        extract_dir=".markdown/a",
    )

    r = await logged_in_client.get("/api/workspace/tree")
    assert r.status_code == 200
    uploads = next(node for node in r.json() if node["name"] == "uploads")
    pdf_node = next(child for child in uploads["children"] if child["name"] == "a.pdf")
    plain_node = next(
        child for child in uploads["children"] if child["name"] == "plain.txt"
    )
    assert pdf_node["agent_path"] == ".markdown/a/hybrid_auto/a.md"
    assert pdf_node["markdown_path"] == ".markdown/a/hybrid_auto/a.md"
    # 未转换的文件 agent_path 留空,前端会回退到 path 自身。
    assert plain_node["agent_path"] is None
    assert plain_node["markdown_path"] is None


async def test_workspace_nested_tree(logged_in_client):
    """嵌套目录正确递归,返回 children 结构。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "docs").mkdir()
    (ws / "docs" / "readme.md").write_text("# hi")
    (ws / "docs" / "subdir").mkdir()
    (ws / "docs" / "subdir" / "a.txt").write_text("a")

    c = logged_in_client
    r = await c.get("/api/workspace/tree")
    assert r.status_code == 200
    docs = next(n for n in r.json() if n["name"] == "docs")
    assert docs["type"] == "dir"
    child_names = [c["name"] for c in docs["children"]]
    # 目录排在文件前面
    assert child_names == ["subdir", "readme.md"]
    subdir = next(c for c in docs["children"] if c["name"] == "subdir")
    assert subdir["children"][0]["name"] == "a.txt"
    assert subdir["children"][0]["type"] == "file"
    assert subdir["children"][0]["size"] == 1


async def test_workspace_tree_carries_conversion_status(logged_in_client):
    """工作区树中为存在 ConversionTask 的文件携带转换状态元数据。"""
    from app.core.config import user_workspace
    from app.db.session import async_session
    from app.models.conversion_task import ConversionTask

    ws = user_workspace("alice")
    (ws / "uploads").mkdir()
    (ws / "uploads" / "report.pdf").write_bytes(b"%PDF")

    async with async_session() as session:
        task = ConversionTask(
            username="alice",
            source_path="uploads/report.pdf",
            source_name="report.pdf",
            status="failed",
            error_message="mineru timeout",
        )
        session.add(task)
        await session.commit()
        task_id = task.id

    r = await logged_in_client.get("/api/workspace/tree")
    assert r.status_code == 200
    uploads = next(node for node in r.json() if node["name"] == "uploads")
    pdf_node = next(
        child for child in uploads["children"] if child["name"] == "report.pdf"
    )
    assert pdf_node["conversion_status"] == "failed"
    assert pdf_node["conversion_task_id"] == task_id
    assert pdf_node["conversion_error"] == "mineru timeout"


# ============ DELETE /api/workspace/file ============


async def test_delete_requires_auth(client):
    """未登录不能删除工作区内容。"""
    r = await client.request("DELETE", "/api/workspace/file", params={"path": "x.txt"})
    assert r.status_code == 401


async def test_delete_file(logged_in_client):
    """删除文件后工作区内不再存在。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "tmp.txt").write_text("data")
    c = logged_in_client
    r = await c.request("DELETE", "/api/workspace/file", params={"path": "tmp.txt"})
    assert r.status_code == 204
    assert not (ws / "tmp.txt").exists()


async def test_delete_directory_recursive(logged_in_client):
    """删除目录会递归清掉子项。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "junk").mkdir()
    (ws / "junk" / "a.txt").write_text("x")
    (ws / "junk" / "sub").mkdir()
    (ws / "junk" / "sub" / "b.txt").write_text("y")
    c = logged_in_client
    r = await c.request("DELETE", "/api/workspace/file", params={"path": "junk"})
    assert r.status_code == 204
    assert not (ws / "junk").exists()


async def test_delete_blocks_path_traversal(logged_in_client):
    """``..`` 试图越出工作区时被拒绝。"""
    c = logged_in_client
    r = await c.request(
        "DELETE", "/api/workspace/file", params={"path": "../../etc/passwd"}
    )
    # 解析后越出工作区,返回 400
    assert r.status_code == 400


async def test_delete_rejects_absolute_path(logged_in_client):
    """绝对路径直接被拒绝。"""
    c = logged_in_client
    r = await c.request(
        "DELETE", "/api/workspace/file", params={"path": "/etc/passwd"}
    )
    assert r.status_code == 400


async def test_delete_missing_returns_404(logged_in_client):
    """不存在的路径返回 404。"""
    c = logged_in_client
    r = await c.request("DELETE", "/api/workspace/file", params={"path": "nope.txt"})
    assert r.status_code == 404


async def test_delete_blocks_root(logged_in_client):
    """无法删除工作区根目录。"""
    c = logged_in_client
    r = await c.request("DELETE", "/api/workspace/file", params={"path": "."})
    assert r.status_code == 400


async def test_delete_source_file_removes_markdown_artifacts(logged_in_client):
    """删除有映射的源文件时,同步删除转换目录并清理索引。"""
    from app.core.config import user_workspace
    from app.modules.workspace.markdown_index import (
        add_markdown_mapping,
        resolve_preview_path,
    )

    ws = user_workspace("alice")
    (ws / "uploads").mkdir()
    (ws / "uploads" / "a.pdf").write_bytes(b"%PDF")
    (ws / ".markdown" / "a" / "hybrid_auto").mkdir(parents=True)
    (ws / ".markdown" / "a" / "hybrid_auto" / "a.md").write_text(
        "# a", encoding="utf-8"
    )
    add_markdown_mapping(
        ws,
        source_path="uploads/a.pdf",
        source_name="a.pdf",
        markdown_path=".markdown/a/hybrid_auto/a.md",
        extract_dir=".markdown/a",
    )

    r = await logged_in_client.request(
        "DELETE", "/api/workspace/file", params={"path": "uploads/a.pdf"}
    )

    assert r.status_code == 204
    assert not (ws / "uploads" / "a.pdf").exists()
    assert not (ws / ".markdown" / "a").exists()
    assert resolve_preview_path(ws, "uploads/a.pdf") == "uploads/a.pdf"


async def test_delete_directory_removes_nested_markdown_artifacts(logged_in_client):
    """删除目录时,仅清理该目录下源文档对应的转换产物。"""
    from app.core.config import user_workspace
    from app.modules.workspace.markdown_index import (
        add_markdown_mapping,
        resolve_preview_path,
    )

    ws = user_workspace("alice")
    (ws / "uploads" / "folder").mkdir(parents=True)
    (ws / "uploads" / "folder" / "a.pdf").write_bytes(b"a")
    (ws / "uploads" / "other.pdf").write_bytes(b"b")
    (ws / ".markdown" / "a").mkdir(parents=True)
    (ws / ".markdown" / "other").mkdir(parents=True)
    add_markdown_mapping(
        ws,
        source_path="uploads/folder/a.pdf",
        source_name="a.pdf",
        markdown_path=".markdown/a/a.md",
        extract_dir=".markdown/a",
    )
    add_markdown_mapping(
        ws,
        source_path="uploads/other.pdf",
        source_name="other.pdf",
        markdown_path=".markdown/other/other.md",
        extract_dir=".markdown/other",
    )

    r = await logged_in_client.request(
        "DELETE", "/api/workspace/file", params={"path": "uploads/folder"}
    )

    assert r.status_code == 204
    assert not (ws / "uploads" / "folder").exists()
    assert not (ws / ".markdown" / "a").exists()
    assert (ws / ".markdown" / "other").exists()
    assert resolve_preview_path(ws, "uploads/folder/a.pdf") == "uploads/folder/a.pdf"
    assert resolve_preview_path(ws, "uploads/other.pdf") == ".markdown/other/other.md"


async def test_delete_source_file_with_missing_markdown_dir_still_cleans_index(
    logged_in_client,
):
    """转换目录已不存在时,仍允许删除源文件并清理索引。"""
    from app.core.config import user_workspace
    from app.modules.workspace.markdown_index import (
        add_markdown_mapping,
        resolve_preview_path,
    )

    ws = user_workspace("alice")
    (ws / "uploads").mkdir()
    (ws / "uploads" / "a.pdf").write_bytes(b"%PDF")
    add_markdown_mapping(
        ws,
        source_path="uploads/a.pdf",
        source_name="a.pdf",
        markdown_path=".markdown/a/a.md",
        extract_dir=".markdown/a",
    )

    r = await logged_in_client.request(
        "DELETE", "/api/workspace/file", params={"path": "uploads/a.pdf"}
    )

    assert r.status_code == 204
    assert not (ws / "uploads" / "a.pdf").exists()
    assert resolve_preview_path(ws, "uploads/a.pdf") == "uploads/a.pdf"


# ============ 内部工具:_should_skip / _guess_mime ============


def test_should_skip_hidden_and_junk():
    """隐藏文件与 _SKIP_DIRS 内的目录名都应被跳过。"""
    from pathlib import Path
    from app.modules.workspace.paths import should_skip

    assert should_skip(Path("/ws/.secret")) is True
    assert should_skip(Path("/ws/node_modules")) is True
    assert should_skip(Path("/ws/__pycache__")) is True
    assert should_skip(Path("/ws/visible.txt")) is False
    assert should_skip(Path("/ws/src")) is False


def test_guess_mime_text_overrides():
    """常见代码/配置后缀强制为 text/plain;charset=utf-8。"""
    from app.modules.workspace.preview import guess_mime

    for name in ("a.py", "a.ts", "a.tsx", "a.js", "a.json", "a.md",
                 "a.yaml", "a.yml", "a.toml", "a.ini", "a.log", "a.env",
                 "a.sh", "a.sql", "a.txt"):
        mime = guess_mime(name)
        assert mime.startswith("text/") or mime.startswith("application/json"), name
        assert "charset=utf-8" in mime, name


def test_guess_mime_image_and_video():
    """图片、视频按 mimetypes 推断,无 charset。"""
    from app.modules.workspace.preview import guess_mime

    assert guess_mime("a.png") == "image/png"
    assert guess_mime("a.jpg") == "image/jpeg"
    assert guess_mime("a.mp4") == "video/mp4"
    assert guess_mime("a.pdf") == "application/pdf"


def test_guess_mime_unknown_falls_back_to_octet():
    """识别不出的扩展名返回 application/octet-stream。"""
    from app.modules.workspace.preview import guess_mime

    assert guess_mime("a.unknownext") == "application/octet-stream"
    assert guess_mime("a") == "application/octet-stream"
