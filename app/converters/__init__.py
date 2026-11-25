"""Format conversion. Converters do not know about HTTP or the database."""

from app.converters.base import ConversionFailed, ConverterRegistry, DocumentConverter
from app.converters.docx_to_pdf import DocxToPdfConverter
from app.converters.pdf_to_docx import PdfToDocxConverter

__all__ = [
    "ConversionFailed",
    "ConverterRegistry",
    "DocumentConverter",
    "DocxToPdfConverter",
    "PdfToDocxConverter",
    "default_converters",
]


def default_converters() -> list[DocumentConverter]:
    return [PdfToDocxConverter(), DocxToPdfConverter()]
