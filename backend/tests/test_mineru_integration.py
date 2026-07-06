import asyncio
from io import BytesIO
from zipfile import ZipFile

import httpx
import pytest

from app.integrations import mineru


def _zip_bytes(entries: dict[str, bytes | str]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            archive.writestr(name, data)
    return buffer.getvalue()


def _transport(response: httpx.Response) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        for field, value in {
            "image_analysis": "true",
            "return_md": "true",
            "return_images": "true",
            "table_enable": "true",
            "response_format_zip": "true",
            "return_original_file": "false",
            "formula_enable": "true",
        }.items():
            assert f'name="{field}"'.encode() in body
            assert f"\r\n\r\n{value}\r\n".encode() in body
        assert b'name="files"' in body
        assert b'filename="source.pdf"' in body
        return response

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_convert_document_to_markdown_limits_concurrent_mineru_requests(tmp_path):
    source_paths = []
    for idx in range(3):
        source_path = tmp_path / f"source-{idx}.pdf"
        source_path.write_bytes(b"%PDF")
        source_paths.append(source_path)

    active_requests = 0
    max_active_requests = 0
    release_first_two = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active_requests, max_active_requests
        active_requests += 1
        max_active_requests = max(max_active_requests, active_requests)
        if max_active_requests == 2:
            release_first_two.set()
        await release_first_two.wait()
        await asyncio.sleep(0)
        active_requests -= 1
        return httpx.Response(
            200,
            content=_zip_bytes({"sample/hybrid_auto/sample.md": "# Converted\n"}),
        )

    await asyncio.gather(
        *[
            mineru.convert_document_to_markdown(
                source_path=source_path,
                output_root=tmp_path / ".markdown" / f"converted-{idx}",
                api_url="https://mineru.example/convert",
                timeout_seconds=12.5,
                transport=httpx.MockTransport(handler),
                max_concurrent_requests=2,
            )
            for idx, source_path in enumerate(source_paths)
        ]
    )

    assert max_active_requests == 2


@pytest.mark.asyncio
async def test_convert_document_to_markdown_extracts_hybrid_auto_markdown_and_images(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF")
    output_root = tmp_path / ".markdown" / "converted"
    archive = _zip_bytes(
        {
            "sample/hybrid_auto/sample.md": "# Converted\n",
            "sample/hybrid_auto/images/page-1.png": b"image",
        }
    )

    result = await mineru.convert_document_to_markdown(
        source_path=source_path,
        output_root=output_root,
        api_url="https://mineru.example/convert",
        timeout_seconds=12.5,
        transport=_transport(httpx.Response(200, content=archive)),
    )

    # 扁平化后冗余的顶层目录 ``sample/`` 被剥离，hybrid_auto 直接挂在 output_root 下。
    assert result.markdown_path == output_root / "hybrid_auto" / "sample.md"
    assert result.markdown_path.read_text() == "# Converted\n"
    assert result.markdown_rel_path == ".markdown/converted/hybrid_auto/sample.md"
    assert result.asset_dir == output_root / "hybrid_auto" / "images"
    assert (result.asset_dir / "page-1.png").read_bytes() == b"image"
    assert result.extract_dir == output_root


@pytest.mark.asyncio
async def test_convert_document_to_markdown_raises_on_non_2xx_status(tmp_path):
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF")
    output_root = tmp_path / ".markdown" / "converted"

    with pytest.raises(mineru.MineruConversionError, match="503"):
        await mineru.convert_document_to_markdown(
            source_path=source_path,
            output_root=output_root,
            api_url="https://mineru.example/convert",
            timeout_seconds=12.5,
            transport=_transport(httpx.Response(503, content=b"unavailable")),
        )

    assert not output_root.exists()


@pytest.mark.asyncio
async def test_convert_document_to_markdown_rejects_invalid_zip_and_cleans_output(tmp_path):
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF")
    output_root = tmp_path / ".markdown" / "converted"

    with pytest.raises(mineru.MineruConversionError, match="invalid zip"):
        await mineru.convert_document_to_markdown(
            source_path=source_path,
            output_root=output_root,
            api_url="https://mineru.example/convert",
            timeout_seconds=12.5,
            transport=_transport(httpx.Response(200, content=b"not a zip")),
        )

    assert not output_root.exists()


@pytest.mark.asyncio
async def test_convert_document_to_markdown_rejects_zip_slip_and_does_not_write_outside(tmp_path):
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF")
    output_root = tmp_path / ".markdown" / "converted"
    archive = _zip_bytes({"../evil.md": "owned"})

    with pytest.raises(mineru.MineruConversionError, match="unsafe zip entry"):
        await mineru.convert_document_to_markdown(
            source_path=source_path,
            output_root=output_root,
            api_url="https://mineru.example/convert",
            timeout_seconds=12.5,
            transport=_transport(httpx.Response(200, content=archive)),
        )

    assert not output_root.exists()
    assert not (tmp_path / ".markdown" / "evil.md").exists()


@pytest.mark.asyncio
async def test_convert_document_to_markdown_rejects_zip_without_markdown(tmp_path):
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF")
    output_root = tmp_path / ".markdown" / "converted"
    archive = _zip_bytes({"sample/hybrid_auto/images/page-1.png": b"image"})

    with pytest.raises(mineru.MineruConversionError, match="markdown file"):
        await mineru.convert_document_to_markdown(
            source_path=source_path,
            output_root=output_root,
            api_url="https://mineru.example/convert",
            timeout_seconds=12.5,
            transport=_transport(httpx.Response(200, content=archive)),
        )

    assert not output_root.exists()


@pytest.mark.asyncio
async def test_convert_document_to_markdown_preserves_existing_output_on_failure(tmp_path):
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF")
    output_root = tmp_path / ".markdown" / "converted"
    existing_file = output_root / "existing.md"
    existing_file.parent.mkdir(parents=True)
    existing_file.write_text("keep me")

    with pytest.raises(mineru.MineruConversionError, match="invalid zip"):
        await mineru.convert_document_to_markdown(
            source_path=source_path,
            output_root=output_root,
            api_url="https://mineru.example/convert",
            timeout_seconds=12.5,
            transport=_transport(httpx.Response(200, content=b"not a zip")),
        )

    assert existing_file.read_text() == "keep me"
    assert not list(output_root.parent.glob(".converted.*.tmp"))


@pytest.mark.asyncio
async def test_convert_document_to_markdown_rejects_zip_file_size_limit_and_cleans_staging(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(mineru, "MAX_ZIP_FILE_SIZE_BYTES", 4)
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF")
    output_root = tmp_path / ".markdown" / "converted"
    archive = _zip_bytes(
        {
            "sample/hybrid_auto/sample.md": "# Converted\n",
            "sample/hybrid_auto/too-large.bin": b"x" * 5,
        }
    )

    with pytest.raises(mineru.MineruConversionError, match="zip file too large"):
        await mineru.convert_document_to_markdown(
            source_path=source_path,
            output_root=output_root,
            api_url="https://mineru.example/convert",
            timeout_seconds=12.5,
            transport=_transport(httpx.Response(200, content=archive)),
        )

    assert not output_root.exists()
    assert not list(output_root.parent.glob(".converted.*.tmp"))


@pytest.mark.asyncio
async def test_convert_document_to_markdown_preserves_existing_output_on_cancellation(tmp_path):
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF")
    output_root = tmp_path / ".markdown" / "converted"
    existing_file = output_root / "existing.md"
    existing_file.parent.mkdir(parents=True)
    existing_file.write_text("keep me")

    async def handler(request: httpx.Request) -> httpx.Response:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await mineru.convert_document_to_markdown(
            source_path=source_path,
            output_root=output_root,
            api_url="https://mineru.example/convert",
            timeout_seconds=12.5,
            transport=httpx.MockTransport(handler),
        )

    assert existing_file.read_text() == "keep me"
    assert not list(output_root.parent.glob(".converted.*.tmp"))


@pytest.mark.asyncio
async def test_mineru_non_2xx_is_logged(tmp_path, caplog):
    import logging

    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF")

    with caplog.at_level(logging.ERROR, logger=mineru.__name__):
        with pytest.raises(mineru.MineruConversionError):
            await mineru.convert_document_to_markdown(
                source_path=source_path,
                output_root=tmp_path / ".markdown" / "converted",
                api_url="https://mineru.example/convert",
                timeout_seconds=12.5,
                transport=_transport(httpx.Response(503, content=b"unavailable")),
            )

    assert any(
        record.levelno == logging.ERROR
        and "MinerU request returned non-success status" in record.getMessage()
        for record in caplog.records
    )
    assert str(source_path) not in caplog.text


@pytest.mark.asyncio
async def test_mineru_invalid_zip_is_logged(tmp_path, caplog):
    import logging

    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF")

    with caplog.at_level(logging.ERROR, logger=mineru.__name__):
        with pytest.raises(mineru.MineruConversionError, match="invalid zip"):
            await mineru.convert_document_to_markdown(
                source_path=source_path,
                output_root=tmp_path / ".markdown" / "converted",
                api_url="https://mineru.example/convert",
                timeout_seconds=12.5,
                transport=_transport(httpx.Response(200, content=b"not a zip")),
            )

    assert any(
        record.levelno == logging.ERROR
        and record.exc_info
        and "MinerU returned invalid zip" in record.getMessage()
        for record in caplog.records
    )
    assert str(source_path) not in caplog.text
