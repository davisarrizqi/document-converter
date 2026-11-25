"""Shared fixtures. API tests use fake converters so they do not need real PDFs."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app import create_app
from app.converters.base import ConversionFailed


def minimal_pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def minimal_docx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?><w:document></w:document>',
        )
    return buffer.getvalue()


class FakePdfToDocx:
    source_format = "pdf"
    target_format = "docx"

    def convert(self, source: Path, target: Path) -> None:
        target.write_bytes(minimal_docx())


class FakeDocxToPdf:
    source_format = "docx"
    target_format = "pdf"

    def convert(self, source: Path, target: Path) -> None:
        target.write_bytes(minimal_pdf())


class ExplodingConverter:
    source_format = "pdf"
    target_format = "docx"

    def convert(self, source: Path, target: Path) -> None:
        raise ConversionFailed("library exploded")


@pytest.fixture
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(tmp_path / "test.db"),
            "STORAGE_DIR": str(tmp_path / "storage"),
            "MAX_UPLOAD_BYTES": 1024 * 1024,
            "MAX_OUTPUT_BYTES": 1024 * 1024,
            "converters": [FakePdfToDocx(), FakeDocxToPdf()],
        }
    )
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def upload(client, filename: str, data: bytes):
    return client.post(
        "/api/v1/documents",
        data={"file": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )
