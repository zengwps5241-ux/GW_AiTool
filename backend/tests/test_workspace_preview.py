"""GET /api/workspace/preview —— 文件预览测试。"""


async def test_preview_requires_auth(client):
    r = await client.get("/api/workspace/preview", params={"path": "x.txt"})
    assert r.status_code == 401


async def test_preview_missing_returns_404(logged_in_client):
    r = await logged_in_client.get(
        "/api/workspace/preview", params={"path": "nope.txt"}
    )
    assert r.status_code == 404


async def test_preview_blocks_path_traversal(logged_in_client):
    r = await logged_in_client.get(
        "/api/workspace/preview", params={"path": "../../etc/passwd"}
    )
    assert r.status_code == 400


async def test_preview_rejects_absolute_path(logged_in_client):
    r = await logged_in_client.get(
        "/api/workspace/preview", params={"path": "/etc/passwd"}
    )
    assert r.status_code == 400


async def test_preview_rejects_empty_path(logged_in_client):
    r = await logged_in_client.get("/api/workspace/preview", params={"path": ""})
    assert r.status_code == 400


async def test_preview_directory_returns_400(logged_in_client):
    """预览对象必须是文件,目录直接 400。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "d").mkdir()
    r = await logged_in_client.get("/api/workspace/preview", params={"path": "d"})
    assert r.status_code == 400


async def test_preview_text_file(logged_in_client):
    """utf-8 文本文件:200、inline、charset=utf-8、body 内容正确。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "a.txt").write_text("你好世界", encoding="utf-8")

    r = await logged_in_client.get(
        "/api/workspace/preview", params={"path": "a.txt"}
    )
    assert r.status_code == 200
    assert "inline" in r.headers.get("content-disposition", "")
    ct = r.headers.get("content-type", "")
    assert ct.startswith("text/plain")
    assert "charset=utf-8" in ct
    assert r.headers.get("x-resolved-preview-path") == "a.txt"
    assert r.content.decode("utf-8") == "你好世界"


async def test_preview_pdf_returns_raw_pdf_even_with_markdown_mapping(logged_in_client):
    """普通预览 PDF 时返回原 PDF，编辑 Markdown 另走 markdown-preview。"""
    from app.core.config import user_workspace
    from app.modules.workspace.markdown_index import add_markdown_mapping

    ws = user_workspace("alice")
    (ws / "uploads").mkdir()
    (ws / "uploads" / "a.pdf").write_bytes(b"%PDF")
    (ws / ".markdown" / "a" / "hybrid_auto").mkdir(parents=True)
    (ws / ".markdown" / "a" / "hybrid_auto" / "a.md").write_text("# Converted", encoding="utf-8")
    add_markdown_mapping(
        ws,
        source_path="uploads/a.pdf",
        source_name="a.pdf",
        markdown_path=".markdown/a/hybrid_auto/a.md",
        extract_dir=".markdown/a",
    )

    r = await logged_in_client.get("/api/workspace/preview", params={"path": "uploads/a.pdf"})

    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.headers.get("x-resolved-preview-path") == "uploads/a.pdf"
    assert r.content == b"%PDF"


async def test_markdown_preview_source_pdf_returns_mapped_markdown(logged_in_client):
    """编辑 Markdown 时，PDF 源文件仍返回转换后的 Markdown。"""
    from app.core.config import user_workspace
    from app.modules.workspace.markdown_index import add_markdown_mapping

    ws = user_workspace("alice")
    (ws / "uploads").mkdir()
    (ws / "uploads" / "a.pdf").write_bytes(b"%PDF")
    (ws / ".markdown" / "a" / "hybrid_auto").mkdir(parents=True)
    (ws / ".markdown" / "a" / "hybrid_auto" / "a.md").write_text("# Converted", encoding="utf-8")
    add_markdown_mapping(
        ws,
        source_path="uploads/a.pdf",
        source_name="a.pdf",
        markdown_path=".markdown/a/hybrid_auto/a.md",
        extract_dir=".markdown/a",
    )

    r = await logged_in_client.get("/api/workspace/markdown-preview", params={"path": "uploads/a.pdf"})

    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("text/plain")
    assert r.headers.get("x-resolved-preview-path") == ".markdown/a/hybrid_auto/a.md"
    assert r.text == "# Converted"


async def test_preview_resolved_path_header_encodes_unicode(logged_in_client):
    """响应头只能放 latin-1/ASCII,中文 Markdown 路径需百分号编码。"""
    from urllib.parse import quote

    from app.core.config import user_workspace
    from app.modules.workspace.markdown_index import add_markdown_mapping

    ws = user_workspace("alice")
    (ws / "uploads").mkdir()
    (ws / "uploads" / "中文.xlsx").write_bytes(b"PK")
    md_rel_path = ".markdown/中文/office/中文.md"
    (ws / ".markdown" / "中文" / "office").mkdir(parents=True)
    (ws / md_rel_path).write_text("# Converted", encoding="utf-8")
    add_markdown_mapping(
        ws,
        source_path="uploads/中文.xlsx",
        source_name="中文.xlsx",
        markdown_path=md_rel_path,
        extract_dir=".markdown/中文",
    )

    r = await logged_in_client.get(
        "/api/workspace/markdown-preview", params={"path": "uploads/中文.xlsx"}
    )

    assert r.status_code == 200
    assert r.headers.get("x-resolved-preview-path") == quote(md_rel_path, safe="/._-")
    assert r.text == "# Converted"


async def test_preview_code_files_use_text_plain(logged_in_client):
    """.py / .ts / .md / .json 应都返回 text/plain;charset=utf-8。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    for name, body in [
        ("a.py", "print('hi')"),
        ("a.ts", "const x = 1"),
        ("a.md", "# 标题"),
    ]:
        (ws / name).write_text(body, encoding="utf-8")
        r = await logged_in_client.get(
            "/api/workspace/preview", params={"path": name}
        )
        assert r.status_code == 200, name
        ct = r.headers.get("content-type", "")
        assert ct.startswith("text/plain"), (name, ct)
        assert "charset=utf-8" in ct, (name, ct)
    # JSON 文件:走 application/json 但仍带 charset
    (ws / "a.json").write_text('{"x":1}', encoding="utf-8")
    r = await logged_in_client.get(
        "/api/workspace/preview", params={"path": "a.json"}
    )
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert ct.startswith("application/json")
    assert "charset=utf-8" in ct


async def test_preview_image_png(logged_in_client):
    """PNG:200、Content-Type image/png。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    # 最小合法 PNG 头(8 字节签名)足够走通响应,无需真实图像
    (ws / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    r = await logged_in_client.get(
        "/api/workspace/preview", params={"path": "a.png"}
    )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/png")


async def test_preview_text_oversize_returns_413(logged_in_client):
    """文本类超过 2 MB 返回 413。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    big = "a" * (2 * 1024 * 1024 + 1)
    (ws / "big.txt").write_text(big, encoding="utf-8")
    r = await logged_in_client.get(
        "/api/workspace/preview", params={"path": "big.txt"}
    )
    assert r.status_code == 413


async def test_preview_image_oversize_returns_413(logged_in_client):
    """图片超过 10 MB 返回 413。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "huge.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * (10 * 1024 * 1024))
    r = await logged_in_client.get(
        "/api/workspace/preview", params={"path": "huge.png"}
    )
    assert r.status_code == 413


async def test_preview_unsupported_binary_returns_415(logged_in_client):
    """二进制(octet-stream)类型返回 415。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "x.bin").write_bytes(b"\x00\x01\x02")
    r = await logged_in_client.get(
        "/api/workspace/preview", params={"path": "x.bin"}
    )
    assert r.status_code == 415


async def test_preview_inline_cache_control(logged_in_client):
    """预览内容会被编辑更新，响应必须禁止浏览器缓存旧内容。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "a.txt").write_text("x", encoding="utf-8")
    r = await logged_in_client.get(
        "/api/workspace/preview", params={"path": "a.txt"}
    )
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"


async def test_preview_video_range_returns_206(logged_in_client):
    """音视频请求带 Range 头时,后端应返回 206 + Content-Range。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    body = b"\x00" * 1024
    (ws / "v.mp4").write_bytes(body)
    r = await logged_in_client.get(
        "/api/workspace/preview",
        params={"path": "v.mp4"},
        headers={"Range": "bytes=0-99"},
    )
    # Starlette FileResponse 在 0.45+ 原生处理 Range;若实现未支持需补
    assert r.status_code == 206, r.status_code
    assert "Content-Range" in r.headers or "content-range" in r.headers
    assert len(r.content) == 100


async def test_preview_text_response_has_nosniff_and_csp(logged_in_client):
    """预览响应必须带 X-Content-Type-Options 与 CSP,防止 HTML/SVG 执行脚本。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "a.txt").write_text("hello", encoding="utf-8")
    r = await logged_in_client.get(
        "/api/workspace/preview", params={"path": "a.txt"}
    )
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff"
    csp = r.headers.get("content-security-policy", "")
    assert "default-src 'none'" in csp
    assert "sandbox" in csp


async def test_preview_html_is_served_as_text_with_nosniff(logged_in_client):
    """text/html 在 inline 预览时 nosniff + CSP 必须存在,浏览器不会执行 <script>。

    我们不在后端禁止 .html 预览(用户合理需求是看源码),但必须靠
    nosniff + CSP 让其无法越权。
    """
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "x.html").write_text(
        "<script>alert(1)</script><p>hi</p>", encoding="utf-8"
    )
    r = await logged_in_client.get(
        "/api/workspace/preview", params={"path": "x.html"}
    )
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert "sandbox" in r.headers.get("content-security-policy", "")


async def test_preview_413_message_has_one_decimal(logged_in_client):
    """413 detail 中文件大小保留一位小数,避免 '2 MB 超过 2 MB' 的反直觉文案。"""
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    # 2 MB + 半 MB,期望显示 "2.5 MB"
    size = int(2.5 * 1024 * 1024)
    (ws / "big.txt").write_text("a" * size, encoding="utf-8")
    r = await logged_in_client.get(
        "/api/workspace/preview", params={"path": "big.txt"}
    )
    assert r.status_code == 413
    detail = r.json().get("detail", "")
    assert "2.5 MB" in detail
    assert "2 MB" in detail  # 上限部分仍是整数
