"""PDF to DOCX via pdf2docx, with LibreOffice as a fallback when it is installed."""

from __future__ import annotations

import logging
from pathlib import Path

from app.converters.base import ConversionFailed, DocumentConverter
from app.converters.libreoffice import libreoffice_convert

logger = logging.getLogger(__name__)


class PdfToDocxConverter(DocumentConverter):
    source_format = "pdf"
    target_format = "docx"

    def convert(self, source: Path, target: Path) -> None:
        try:
            self._convert_with_pdf2docx(source, target)
            return
        except Exception:
            logger.exception("pdf2docx failed for %s", source.name)
            if target.exists():
                target.unlink()
        if libreoffice_convert(source, target, "docx"):
            return
        raise ConversionFailed("PDF could not be converted to DOCX.")

    @staticmethod
    def _convert_with_pdf2docx(source: Path, target: Path) -> None:
        from pdf2docx import Converter

        converter = Converter(str(source))
        try:
            converter.convert(str(target))
        finally:
            converter.close()
