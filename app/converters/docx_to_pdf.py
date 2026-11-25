"""DOCX to PDF.

LibreOffice is preferred when ``soffice`` is on PATH because it keeps more of
the original layout. Otherwise mammoth turns the DOCX into HTML and xhtml2pdf
renders that HTML. Neither path requires Microsoft Word.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.converters.base import ConversionFailed, DocumentConverter
from app.converters.libreoffice import libreoffice_convert

logger = logging.getLogger(__name__)


class DocxToPdfConverter(DocumentConverter):
    source_format = "docx"
    target_format = "pdf"

    def convert(self, source: Path, target: Path) -> None:
        if libreoffice_convert(source, target, "pdf"):
            return
        try:
            self._convert_with_libraries(source, target)
        except ConversionFailed:
            raise
        except Exception as exc:
            logger.exception("DOCX to PDF conversion failed for %s", source.name)
            raise ConversionFailed("DOCX could not be converted to PDF.") from exc

    @staticmethod
    def _convert_with_libraries(source: Path, target: Path) -> None:
        import mammoth
        from xhtml2pdf import pisa

        with source.open("rb") as handle:
            result = mammoth.convert_to_html(handle)
        for message in result.messages:
            logger.info("mammoth: %s", message)
        body = result.value.strip() or "<p>&nbsp;</p>"
        html = (
            "<!DOCTYPE html><html><head><meta charset=\"utf-8\"/>"
            "<style>"
            "body{font-family:Helvetica,Arial,sans-serif;font-size:12pt;color:#111;}"
            "img{max-width:100%;height:auto;}"
            "table{border-collapse:collapse;width:100%;}"
            "td,th{border:1px solid #ccc;padding:4px;vertical-align:top;}"
            "</style></head><body>"
            f"{body}</body></html>"
        )
        with target.open("wb") as output:
            status = pisa.CreatePDF(src=html, dest=output, encoding="utf-8")
        if getattr(status, "err", 0):
            raise ConversionFailed("xhtml2pdf reported errors while writing the PDF.")
        if not target.exists() or target.stat().st_size == 0:
            raise ConversionFailed("DOCX to PDF produced an empty file.")
