from pathlib import Path

import pytest


async def test_temporary_pdf_for_doc_removes_intermediate_file(tmp_path, monkeypatch):
    from app.modules.conversions import office_pdf

    source = tmp_path / "legacy.doc"
    source.write_bytes(b"doc")
    created_pdf_parent: Path | None = None

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_create_subprocess_exec(*args, stdout=None, stderr=None):
        nonlocal created_pdf_parent
        outdir = Path(args[args.index("--outdir") + 1])
        created_pdf_parent = outdir
        (outdir / "legacy.pdf").write_bytes(b"%PDF")
        return FakeProcess()

    monkeypatch.setattr(office_pdf.shutil, "which", lambda name: "/usr/bin/libreoffice")
    monkeypatch.setattr(
        office_pdf.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    async with office_pdf.temporary_pdf_for_doc(source) as pdf:
        assert pdf.name == "legacy.pdf"
        assert pdf.exists()

    assert created_pdf_parent is not None
    assert not created_pdf_parent.exists()


async def test_temporary_pdf_for_doc_reports_missing_converter(tmp_path, monkeypatch):
    from app.modules.conversions import office_pdf

    source = tmp_path / "legacy.doc"
    source.write_bytes(b"doc")
    monkeypatch.setattr(office_pdf.shutil, "which", lambda name: None)

    with pytest.raises(office_pdf.OfficePdfConversionError, match="LibreOffice"):
        async with office_pdf.temporary_pdf_for_doc(source):
            raise AssertionError("should not enter context")


async def test_temporary_pdf_for_doc_missing_converter_is_logged(
    tmp_path, monkeypatch, caplog
):
    import logging

    from app.modules.conversions import office_pdf

    source = tmp_path / "legacy.doc"
    source.write_bytes(b"doc")
    monkeypatch.setattr(office_pdf.shutil, "which", lambda name: None)

    with caplog.at_level(logging.ERROR, logger=office_pdf.__name__):
        with pytest.raises(office_pdf.OfficePdfConversionError):
            async with office_pdf.temporary_pdf_for_doc(source):
                raise AssertionError("context should not be entered")

    assert any(
        record.levelno == logging.ERROR
        and "Office PDF converter is not available" in record.getMessage()
        for record in caplog.records
    )
    assert str(source) not in caplog.text


async def test_temporary_pdf_for_doc_process_failure_is_logged(
    tmp_path, monkeypatch, caplog
):
    import logging

    from app.modules.conversions import office_pdf

    source = tmp_path / "legacy.doc"
    source.write_bytes(b"doc")

    class FakeProcess:
        returncode = 1

        async def communicate(self):
            return b"", b"failed"

    async def fake_create_subprocess_exec(*args, stdout=None, stderr=None):
        return FakeProcess()

    monkeypatch.setattr(office_pdf.shutil, "which", lambda name: "/usr/bin/libreoffice")
    monkeypatch.setattr(
        office_pdf.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    with caplog.at_level(logging.ERROR, logger=office_pdf.__name__):
        with pytest.raises(office_pdf.OfficePdfConversionError):
            async with office_pdf.temporary_pdf_for_doc(source):
                raise AssertionError("context should not be entered")

    assert any(
        record.levelno == logging.ERROR
        and "Office PDF conversion process failed" in record.getMessage()
        for record in caplog.records
    )
    assert str(source) not in caplog.text
