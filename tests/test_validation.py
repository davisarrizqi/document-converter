"""Direct checks for the validators that do not need the HTTP stack."""

from __future__ import annotations

import io
import zipfile

import pytest
from werkzeug.datastructures import FileStorage

from app.errors import PayloadTooLargeError, UnsupportedMediaError, ValidationError
from app.validation import assert_output, read_upload
from tests.conftest import minimal_docx, minimal_pdf


def _file(name: str, data: bytes) -> FileStorage:
    return FileStorage(stream=io.BytesIO(data), filename=name)


def test_accepts_pdf_and_hashes_it():
    upload = read_upload(_file("A.PDF", minimal_pdf()), max_bytes=1000, extra_fields=[])
    assert upload.format == "pdf"
    assert upload.filename == "A.PDF"
    assert upload.sha256


def test_rejects_path_in_filename_and_keeps_basename():
    upload = read_upload(
        _file("../secrets/ok.pdf", minimal_pdf()),
        max_bytes=1000,
        extra_fields=[],
    )
    assert upload.filename == "ok.pdf"


def test_rejects_zip_bomb_like_docx():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"A" * 20000)
    with pytest.raises(ValidationError) as caught:
        read_upload(_file("bomb.docx", buffer.getvalue()), max_bytes=500, extra_fields=[])
    assert "expands beyond" in caught.value.details[0]["message"]


def test_output_must_match_target_format():
    with pytest.raises(ValidationError):
        assert_output(minimal_pdf(), "docx", 1000)
    assert_output(minimal_docx(), "docx", 1000)


def test_oversize_upload():
    with pytest.raises(PayloadTooLargeError):
        read_upload(_file("ok.pdf", minimal_pdf()), max_bytes=8, extra_fields=[])


def test_unsupported_extension():
    with pytest.raises(UnsupportedMediaError):
        read_upload(_file("notes.txt", b"hello"), max_bytes=100, extra_fields=[])
