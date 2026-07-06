"""GET /api/workspace/download —— 文件分支测试。"""

import io
import sys
import zipfile
from urllib.parse import quote

import pytest
from httpx import AsyncClient

from app.core.config import user_workspace


async def test_download_requires_auth(client):
    """未登录返回 401。"""
    r = await client.get("/api/workspace/download", params={"path": "x.txt"})
    assert r.status_code == 401


async def test_download_missing_returns_404(logged_in_client):
    """文件不存在返回 404。"""
    r = await logged_in_client.get(
        "/api/workspace/download", params={"path": "nope.txt"}
    )
    assert r.status_code == 404


async def test_download_blocks_path_traversal(logged_in_client):
    """`..` 试图越出工作区时返回 400。"""
    r = await logged_in_client.get(
        "/api/workspace/download", params={"path": "../../etc/passwd"}
    )
    assert r.status_code == 400


async def test_download_rejects_absolute_path(logged_in_client):
    """绝对路径返回 400。"""
    r = await logged_in_client.get(
        "/api/workspace/download", params={"path": "/etc/passwd"}
    )
    assert r.status_code == 400


async def test_download_rejects_empty_path(logged_in_client):
    """空路径返回 400。"""
    r = await logged_in_client.get("/api/workspace/download", params={"path": ""})
    assert r.status_code == 400


async def test_download_file_returns_attachment_with_content(logged_in_client):
    """单文件下载:200、attachment、Content 与原文件一致。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "hello.txt").write_text("hi there", encoding="utf-8")

    r = await logged_in_client.get(
        "/api/workspace/download", params={"path": "hello.txt"}
    )
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "filename*=UTF-8''hello.txt" in cd
    assert r.content == b"hi there"


async def test_download_file_chinese_name(logged_in_client):
    """中文文件名应使用 RFC 5987 编码,可解码回原名。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    name = "笔记.md"
    (ws / name).write_text("内容", encoding="utf-8")

    r = await logged_in_client.get(
        "/api/workspace/download", params={"path": name}
    )
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert f"filename*=UTF-8''{quote(name, safe='')}" in cd


async def test_download_file_uses_octet_stream(logged_in_client):
    """单文件下载强制 octet-stream,避免浏览器原地预览。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "a.txt").write_text("x", encoding="utf-8")

    r = await logged_in_client.get(
        "/api/workspace/download", params={"path": "a.txt"}
    )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/octet-stream")
    assert r.headers.get("cache-control") == "no-store"


async def test_download_directory_as_zip(logged_in_client):
    """目录下载返回 zip,内部结构与工作区相对路径一致。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "proj").mkdir()
    (ws / "proj" / "a.txt").write_text("aaa", encoding="utf-8")
    (ws / "proj" / "sub").mkdir()
    (ws / "proj" / "sub" / "b.txt").write_text("bbb", encoding="utf-8")

    r = await logged_in_client.get(
        "/api/workspace/download", params={"path": "proj"}
    )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/zip")
    cd = r.headers.get("content-disposition", "")
    assert f"filename*=UTF-8''{quote('proj.zip', safe='')}" in cd

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = sorted(zf.namelist())
        assert names == ["proj/a.txt", "proj/sub/b.txt"]
        assert zf.read("proj/a.txt") == b"aaa"
        assert zf.read("proj/sub/b.txt") == b"bbb"


async def test_download_markdown_zip_for_converted_document(logged_in_client):
    """已转换的 Office/PDF 源文件可下载 Markdown 提取目录 zip。"""
    from app.modules.workspace.markdown_index import add_markdown_mapping

    ws = user_workspace("alice")
    (ws / "report.pdf").write_bytes(b"%PDF")
    extract_dir = ws / ".markdown" / "report"
    (extract_dir / "images").mkdir(parents=True)
    (extract_dir / "report.md").write_text("# 报告", encoding="utf-8")
    (extract_dir / "images" / "p1.png").write_bytes(b"png")
    add_markdown_mapping(
        ws,
        source_path="report.pdf",
        source_name="report.pdf",
        markdown_path=".markdown/report/report.md",
        extract_dir=".markdown/report",
    )

    r = await logged_in_client.get(
        "/api/workspace/download-markdown", params={"path": "report.pdf"}
    )

    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/zip")
    cd = r.headers.get("content-disposition", "")
    assert f"filename*=UTF-8''{quote('report-markdown.zip', safe='')}" in cd
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = sorted(zf.namelist())
        assert names == ["report/images/p1.png", "report/report.md"]
        assert zf.read("report/report.md") == "# 报告".encode()
        assert zf.read("report/images/p1.png") == b"png"


async def test_download_markdown_returns_409_when_not_converted(logged_in_client):
    """源文件尚未生成 Markdown 映射时返回 409。"""
    ws = user_workspace("alice")
    (ws / "report.pdf").write_bytes(b"%PDF")

    r = await logged_in_client.get(
        "/api/workspace/download-markdown", params={"path": "report.pdf"}
    )

    assert r.status_code == 409
    assert "尚未生成" in r.json()["detail"]


async def test_download_markdown_rejects_non_convertible_file(logged_in_client):
    """普通文本文件不能走 Markdown 下载接口。"""
    ws = user_workspace("alice")
    (ws / "note.txt").write_text("hello", encoding="utf-8")

    r = await logged_in_client.get(
        "/api/workspace/download-markdown", params={"path": "note.txt"}
    )

    assert r.status_code == 400
    assert "Office/PDF" in r.json()["detail"]


async def test_download_directory_filters_hidden_and_junk(logged_in_client):
    """目录打包跟随文件树过滤规则:.hidden / node_modules / __pycache__ 都不进 zip。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "proj").mkdir()
    (ws / "proj" / "keep.txt").write_text("ok", encoding="utf-8")
    (ws / "proj" / ".secret").write_text("nope", encoding="utf-8")
    (ws / "proj" / "node_modules").mkdir()
    (ws / "proj" / "node_modules" / "junk.js").write_text("x", encoding="utf-8")
    (ws / "proj" / "__pycache__").mkdir()
    (ws / "proj" / "__pycache__" / "x.pyc").write_text("y", encoding="utf-8")

    r = await logged_in_client.get(
        "/api/workspace/download", params={"path": "proj"}
    )
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        assert names == ["proj/keep.txt"]


async def test_download_directory_chinese_name(logged_in_client):
    """中文目录名 zip filename 编码正确。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    name = "我的项目"
    (ws / name).mkdir()
    (ws / name / "a.txt").write_text("a", encoding="utf-8")

    r = await logged_in_client.get(
        "/api/workspace/download", params={"path": name}
    )
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert f"filename*=UTF-8''{quote(f'{name}.zip', safe='')}" in cd


async def test_download_directory_skips_missing_files_midway(
    logged_in_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """打包过程中文件被并发删除时,跳过该条而不中断整体响应。"""
    import app.modules.workspace.archive as archive_mod

    ws = user_workspace("alice")
    (ws / "p").mkdir()
    (ws / "p" / "keep.txt").write_text("ok", encoding="utf-8")
    # 构造一个不存在的子路径,通过 monkeypatch 让 walk_filtered 返回它
    fake = ws / "p" / "ghost.txt"
    orig_walk = archive_mod.walk_filtered

    def patched_walk(root, ws_root):
        yield from orig_walk(root, ws_root)
        yield fake  # 不存在的文件

    monkeypatch.setattr(archive_mod, "walk_filtered", patched_walk)
    r = await logged_in_client.get("/api/workspace/download", params={"path": "p"})
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert zf.namelist() == ["p/keep.txt"]


async def test_download_rejects_workspace_root(
    logged_in_client: AsyncClient,
) -> None:
    """禁止把整个工作区打包下载。"""
    resp = await logged_in_client.get(
        "/api/workspace/download", params={"path": "."}
    )
    assert resp.status_code == 400
    assert "工作区" in resp.json()["detail"]


@pytest.mark.skipif(sys.platform == "win32", reason="符号链接环只在 POSIX 验证")
async def test_download_directory_symlink_cycle_terminates(
    logged_in_client: AsyncClient,
) -> None:
    """工作区内的符号链接环不应导致 _walk_filtered 无限递归。"""
    ws = user_workspace("alice")
    base = ws / "cycle"
    base.mkdir(parents=True, exist_ok=True)
    (base / "real.txt").write_text("real", encoding="utf-8")
    sub = base / "sub"
    sub.mkdir(exist_ok=True)
    # sub/back -> base,形成环
    link = sub / "back"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(base, target_is_directory=True)
    try:
        resp = await logged_in_client.get(
            "/api/workspace/download", params={"path": "cycle"}
        )
        assert resp.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        # 至少包含 real.txt;不应因为环卡死
        assert any(name.endswith("real.txt") for name in zf.namelist())
    finally:
        if link.is_symlink():
            link.unlink()


async def test_download_directory_propagates_permission_error(
    logged_in_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """文件不可读时不应被静默忽略——必须暴露错误。"""
    ws = user_workspace("alice")
    base = ws / "perm"
    base.mkdir(parents=True, exist_ok=True)
    (base / "ok.txt").write_text("ok", encoding="utf-8")

    import app.modules.workspace.service as service_mod

    def boom(*args, **kwargs):
        # 用生成器形式抛错,确保异常发生在 StreamingResponse 迭代阶段,
        # 而不是 endpoint 同步调用阶段(后者会绕过 FastAPI 的异常处理)
        raise PermissionError("拒绝访问")
        yield b""  # noqa: 让其成为生成器函数

    monkeypatch.setattr(service_mod, "iter_zip", boom)

    try:
        resp = await logged_in_client.get(
            "/api/workspace/download", params={"path": "perm"}
        )
        # 若 FastAPI 在迭代阶段捕获并转 500,则断言其状态码
        assert resp.status_code >= 500
    except PermissionError:
        # 若 ASGI 传输直接把异常抛出来,也算"未被静默吞掉",符合修复目标
        pass
