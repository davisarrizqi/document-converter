"""The real converter libraries, not the fakes used by the API tests."""

from __future__ import annotations

from pathlib import Path

from docx import Document

from app.converters.docx_to_pdf import DocxToPdfConverter
from app.converters.pdf_to_docx import PdfToDocxConverter


def test_docx_to_pdf_with_libraries(tmp_path: Path):
    source = tmp_path / "hello.docx"
    document = Document()
    document.add_paragraph("Hello from the document converter.")
    document.save(source)
    target = tmp_path / "hello.pdf"
    DocxToPdfConverter().convert(source, target)
    data = target.read_bytes()
    assert data.startswith(b"%PDF-")
    assert b"%%EOF" in data[-2048:]


def test_pdf_to_docx_with_pdf2docx(tmp_path: Path):
    from reportlab.pdfgen import canvas

    source = tmp_path / "hello.pdf"
    sheet = canvas.Canvas(str(source))
    sheet.drawString(72, 720, "Hello from the document converter.")
    sheet.save()
    target = tmp_path / "hello.docx"
    PdfToDocxConverter().convert(source, target)
    assert target.stat().st_size > 0
    converted = Document(str(target))
    text = "\n".join(paragraph.text for paragraph in converted.paragraphs)
    assert "Hello" in text
