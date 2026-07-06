async def test_feedback_models_are_registered():
    from app.models import Base

    assert "feedback_issues" in Base.metadata.tables
    assert "feedback_attachments" in Base.metadata.tables

    issue_table = Base.metadata.tables["feedback_issues"]
    attachment_table = Base.metadata.tables["feedback_attachments"]

    issue_indexes = {index.name for index in issue_table.indexes}
    attachment_indexes = {index.name for index in attachment_table.indexes}

    assert "idx_feedback_issues_created" in issue_indexes
    assert "idx_feedback_issues_reporter" in issue_indexes
    assert "idx_feedback_attachments_issue" in attachment_indexes

    issue_indexes_by_name = {index.name: index for index in issue_table.indexes}
    attachment_indexes_by_name = {index.name: index for index in attachment_table.indexes}

    assert issue_table.c.description.server_default is not None
    assert str(issue_table.c.description.server_default.arg) == ""

    reporter_index = issue_indexes_by_name["idx_feedback_issues_reporter"]
    assert [column.name for column in reporter_index.expressions] == ["reporter_username"]

    attachment_issue_index = attachment_indexes_by_name["idx_feedback_attachments_issue"]
    assert [column.name for column in attachment_issue_index.expressions] == ["issue_id"]

    created_index = issue_indexes_by_name["idx_feedback_issues_created"]
    created_expression = str(created_index.expressions[0]).upper()
    assert "CREATED_AT" in created_expression
    assert "DESC" in created_expression


async def test_create_feedback_issue_with_image(logged_in_client, tmp_path, monkeypatch):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(
        feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads"
    )

    res = await logged_in_client.post(
        "/api/feedback/issues",
        data={"title": "按钮无响应", "description": "点击后没有任何反馈"},
        files={"images": ("screen.png", b"\x89PNG\r\n", "image/png")},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "按钮无响应"
    assert body["description"] == "点击后没有任何反馈"
    assert body["reporter_username"] == "Alice"
    assert body["attachment_count"] == 1
    assert list((tmp_path / "feedback_uploads" / str(body["id"])).iterdir())


async def test_create_feedback_rejects_non_image(
    logged_in_client, tmp_path, monkeypatch
):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(
        feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads"
    )

    res = await logged_in_client.post(
        "/api/feedback/issues",
        data={"title": "错误附件", "description": ""},
        files={"images": ("note.txt", b"hello", "text/plain")},
    )

    assert res.status_code == 400
    assert "图片" in res.text


async def test_create_feedback_dedupes_duplicate_image_names(
    logged_in_client, tmp_path, monkeypatch
):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(
        feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads"
    )

    res = await logged_in_client.post(
        "/api/feedback/issues",
        data={"title": "重复文件名", "description": ""},
        files=[
            ("images", ("screen.png", b"first", "image/png")),
            ("images", ("screen.png", b"second", "image/png")),
        ],
    )

    assert res.status_code == 200
    body = res.json()
    saved = sorted((tmp_path / "feedback_uploads" / str(body["id"])).iterdir())
    assert [path.name for path in saved] == ["screen-1.png", "screen.png"]


async def test_create_feedback_sanitizes_dangerous_image_name(
    logged_in_client, tmp_path, monkeypatch
):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(
        feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads"
    )

    res = await logged_in_client.post(
        "/api/feedback/issues",
        data={"title": "危险文件名", "description": ""},
        files={"images": ("../../evil.png", b"image", "image/png")},
    )

    assert res.status_code == 200
    body = res.json()
    issue_dir = tmp_path / "feedback_uploads" / str(body["id"])
    assert (issue_dir / "evil.png").exists()
    assert not (tmp_path / "evil.png").exists()


async def test_create_feedback_rejects_oversized_single_image_and_cleans_files(
    logged_in_client, tmp_path, monkeypatch
):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(
        feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads"
    )
    monkeypatch.setattr(feedback_service, "MAX_IMAGE_SIZE", 3)

    res = await logged_in_client.post(
        "/api/feedback/issues",
        data={"title": "单图过大", "description": ""},
        files={"images": ("large.png", b"abcd", "image/png")},
    )

    assert res.status_code == 400
    assert "单张图片" in res.text
    assert not any((tmp_path / "feedback_uploads").glob("*"))


async def test_create_feedback_rejects_oversized_total_images_and_cleans_files(
    logged_in_client, tmp_path, monkeypatch
):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(
        feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads"
    )
    monkeypatch.setattr(feedback_service, "MAX_TOTAL_IMAGE_SIZE", 5)

    res = await logged_in_client.post(
        "/api/feedback/issues",
        data={"title": "总量过大", "description": ""},
        files=[
            ("images", ("a.png", b"aaa", "image/png")),
            ("images", ("b.png", b"bbb", "image/png")),
        ],
    )

    assert res.status_code == 400
    assert "总大小" in res.text
    assert not any((tmp_path / "feedback_uploads").glob("*"))


async def test_create_feedback_rejects_too_long_image_name(
    logged_in_client, tmp_path, monkeypatch
):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(
        feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads"
    )
    monkeypatch.setattr(feedback_service, "MAX_FILENAME_LENGTH", 10)

    res = await logged_in_client.post(
        "/api/feedback/issues",
        data={"title": "文件名过长", "description": ""},
        files={"images": ("very-long-name.png", b"image", "image/png")},
    )

    assert res.status_code == 400
    assert "文件名过长" in res.text
    assert not any((tmp_path / "feedback_uploads").glob("*"))


async def test_create_feedback_rejects_multibyte_too_long_image_name(
    logged_in_client, tmp_path, monkeypatch
):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(
        feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads"
    )
    monkeypatch.setattr(feedback_service, "MAX_FILENAME_BYTES", 12)

    res = await logged_in_client.post(
        "/api/feedback/issues",
        data={"title": "多字节文件名过长", "description": ""},
        files={"images": ("截图截图截图.png", b"image", "image/png")},
    )

    assert res.status_code == 400
    assert "文件名过长" in res.text
    assert not any((tmp_path / "feedback_uploads").glob("*"))


async def test_create_feedback_trims_duplicate_multibyte_image_name_to_byte_limit(
    logged_in_client, tmp_path, monkeypatch
):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(
        feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads"
    )
    monkeypatch.setattr(feedback_service, "MAX_FILENAME_BYTES", 17)

    res = await logged_in_client.post(
        "/api/feedback/issues",
        data={"title": "重复多字节文件名", "description": ""},
        files=[
            ("images", ("截图截图.png", b"first", "image/png")),
            ("images", ("截图截图.png", b"second", "image/png")),
        ],
    )

    assert res.status_code == 200
    body = res.json()
    saved_names = sorted(
        path.name for path in (tmp_path / "feedback_uploads" / str(body["id"])).iterdir()
    )
    assert saved_names == ["截图截-1.png", "截图截图.png"]
    assert all(len(name.encode("utf-8")) <= 17 for name in saved_names)


async def test_admin_can_list_and_view_feedback(admin_client, tmp_path, monkeypatch):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(
        feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads"
    )

    create = await admin_client.post(
        "/api/feedback/issues",
        data={"title": "列表问题", "description": "详情描述"},
        files={"images": ("screen.png", b"\x89PNG\r\n", "image/png")},
    )
    assert create.status_code == 200
    issue_id = create.json()["id"]

    listing = await admin_client.get("/api/admin/feedback/issues?page=1&page_size=20")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] >= 1
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["items"][0]["title"] == "列表问题"
    assert body["items"][0]["reporter_username"] == "Admin"

    detail = await admin_client.get(f"/api/admin/feedback/issues/{issue_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["title"] == "列表问题"
    assert detail_body["description"] == "详情描述"
    assert detail_body["reporter_username"] == "Admin"
    assert len(detail_body["attachments"]) == 1
    assert detail_body["attachments"][0]["filename"] == "screen.png"
    assert detail_body["attachments"][0]["url"].startswith(
        "/api/admin/feedback/attachments/"
    )


async def test_admin_can_fetch_feedback_attachment(admin_client, tmp_path, monkeypatch):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(
        feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads"
    )

    create = await admin_client.post(
        "/api/feedback/issues",
        data={"title": "截图", "description": ""},
        files={"images": ("screen.png", b"\x89PNG\r\n", "image/png")},
    )
    assert create.status_code == 200
    issue_id = create.json()["id"]
    detail = await admin_client.get(f"/api/admin/feedback/issues/{issue_id}")
    assert detail.status_code == 200
    attachment_url = detail.json()["attachments"][0]["url"]

    image = await admin_client.get(attachment_url)

    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")
    assert image.headers["content-disposition"].startswith("inline")
    assert image.content == b"\x89PNG\r\n"


async def test_admin_can_delete_feedback_issue(admin_client, tmp_path, monkeypatch):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(
        feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads"
    )

    create = await admin_client.post(
        "/api/feedback/issues",
        data={"title": "待删除", "description": ""},
        files={"images": ("screen.png", b"\x89PNG\r\n", "image/png")},
    )
    assert create.status_code == 200
    issue_id = create.json()["id"]
    issue_dir = tmp_path / "feedback_uploads" / str(issue_id)
    assert issue_dir.exists()

    deleted = await admin_client.delete(f"/api/admin/feedback/issues/{issue_id}")
    assert deleted.status_code == 204
    assert not issue_dir.exists()

    detail = await admin_client.get(f"/api/admin/feedback/issues/{issue_id}")
    assert detail.status_code == 404


async def test_non_admin_cannot_manage_feedback(
    logged_in_client, tmp_path, monkeypatch
):
    from app.modules.feedback import service as feedback_service

    monkeypatch.setattr(
        feedback_service, "FEEDBACK_UPLOAD_ROOT", tmp_path / "feedback_uploads"
    )

    create = await logged_in_client.post(
        "/api/feedback/issues",
        data={"title": "普通用户反馈", "description": ""},
        files={"images": ("screen.png", b"\x89PNG\r\n", "image/png")},
    )
    assert create.status_code == 200
    issue_id = create.json()["id"]

    listing = await logged_in_client.get("/api/admin/feedback/issues")
    detail = await logged_in_client.get(f"/api/admin/feedback/issues/{issue_id}")
    attachment = await logged_in_client.get("/api/admin/feedback/attachments/1")
    deleted = await logged_in_client.delete(f"/api/admin/feedback/issues/{issue_id}")

    assert listing.status_code == 403
    assert detail.status_code == 403
    assert attachment.status_code == 403
    assert deleted.status_code == 403
