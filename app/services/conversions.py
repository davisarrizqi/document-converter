"""Conversion use cases.

A conversion is synchronous: the row is persisted as ``processing`` before the
converter runs, then settled as ``completed`` or ``failed``. Client mistakes
(unknown document, wrong target format) do not create a row. Converter
failures do, so the attempt stays auditable.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
import uuid
from pathlib import Path

from app.config import Settings
from app.converters.base import ConversionFailed, ConverterRegistry
from app.database import Database
from app.errors import AppError, ConversionRejected, NotFoundError, ValidationError
from app.models import Conversion, Document
from app.storage import StoredFiles
from app.timeutil import utcnow
from app.validation import OPPOSITE_FORMAT, assert_output

logger = logging.getLogger(__name__)


class ConversionService:
    def __init__(
        self,
        database: Database,
        files: StoredFiles,
        converters: ConverterRegistry,
        settings: Settings,
    ) -> None:
        self._database = database
        self._files = files
        self._converters = converters
        self._settings = settings

    def create(self, document_id: str, target_format: str) -> Conversion:
        with self._database.unit_of_work() as uow:
            source = uow.documents.get(document_id)
            if source is None:
                raise NotFoundError("Document not found.")
            expected = OPPOSITE_FORMAT[source.format]
            if target_format != expected:
                raise ValidationError(
                    [
                        {
                            "field": "target_format",
                            "message": (
                                f"A {source.format.upper()} document can only be converted to "
                                f"{expected.upper()}."
                            ),
                        }
                    ]
                )
            now = utcnow()
            conversion = Conversion(
                id=str(uuid.uuid4()),
                source_document_id=source.id,
                output_document_id=None,
                source_format=source.format,
                target_format=target_format,
                status="processing",
                error_code=None,
                error_message=None,
                created_at=now,
                updated_at=now,
                finished_at=None,
            )
            uow.conversions.insert(conversion)
            source_storage = source.storage_name
            source_filename = source.filename

        try:
            data = self._convert(source_storage, source.format, target_format)
        except ConversionRejected as exc:
            self._fail(conversion.id, exc.message)
            exc.conversion_id = conversion.id
            raise
        except AppError as exc:
            self._fail(conversion.id, exc.message, exc.code)
            exc.conversion_id = conversion.id
            raise

        output_id = str(uuid.uuid4())
        storage_name = f"{output_id}.{target_format}"
        self._files.write(storage_name, data)
        try:
            finished = utcnow()
            output = Document(
                id=output_id,
                filename=_output_filename(source_filename, target_format),
                format=target_format,
                mime_type=_mime(target_format),
                size_bytes=len(data),
                sha256=_sha256(data),
                storage_name=storage_name,
                role="output",
                created_at=finished,
            )
            with self._database.unit_of_work() as uow:
                uow.documents.insert(output)
                uow.conversions.mark_completed(conversion.id, output_id, finished)
                saved = uow.conversions.get(conversion.id)
        except Exception as exc:
            logger.exception("Could not persist conversion output %s", conversion.id)
            self._files.remove(storage_name)
            message = _client_message(target_format)
            self._fail(conversion.id, message)
            raise ConversionRejected(
                message,
                details=[{"field": "file", "message": message}],
                conversion_id=conversion.id,
            ) from exc
        if saved is None:
            raise AppError("Conversion disappeared while it was being saved.", status_code=500, code="internal_error")
        return saved

    def get(self, conversion_id: str) -> Conversion:
        with self._database.unit_of_work() as uow:
            conversion = uow.conversions.get(conversion_id)
        if conversion is None:
            raise NotFoundError("Conversion not found.")
        return conversion

    def list(
        self,
        *,
        page: int,
        per_page: int,
        status: str | None,
        document_id: str | None,
        target_format: str | None,
    ) -> tuple[list[Conversion], int]:
        with self._database.unit_of_work() as uow:
            return uow.conversions.list(
                page=page,
                per_page=per_page,
                status=status,
                document_id=document_id,
                target_format=target_format,
            )

    def delete(self, conversion_id: str) -> None:
        storage_name = None
        with self._database.unit_of_work() as uow:
            conversion = uow.conversions.get(conversion_id)
            if conversion is None:
                raise NotFoundError("Conversion not found.")
            output = None
            if conversion.output_document_id:
                output = uow.documents.get(conversion.output_document_id)
            uow.conversions.delete(conversion.id)
            if output is not None:
                storage_name = output.storage_name
                uow.documents.delete(output.id)
        if storage_name:
            self._files.remove(storage_name)

    def _convert(self, storage_name: str, source_format: str, target_format: str) -> bytes:
        source_path = self._files.resolve(storage_name)
        if not source_path.is_file():
            raise AppError(
                "The file for this document is missing from storage.",
                status_code=500,
                code="storage_missing",
            )
        converter = self._converters.get(source_format, target_format)
        if converter is None:
            raise ValidationError(
                [
                    {
                        "field": "target_format",
                        "message": "This conversion is not supported.",
                    }
                ]
            )
        message = _client_message(target_format)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / f"output.{target_format}"
            try:
                converter.convert(source_path, target)
                data = target.read_bytes() if target.is_file() else b""
            except ConversionFailed as exc:
                logger.warning("Converter failed: %s", exc)
                raise ConversionRejected(
                    message,
                    details=[{"field": "file", "message": message}],
                ) from exc
            except Exception as exc:
                logger.exception("Unexpected converter error")
                raise ConversionRejected(
                    message,
                    details=[{"field": "file", "message": message}],
                ) from exc
        try:
            assert_output(data, target_format, self._settings.max_output_bytes)
        except AppError as exc:
            detail = exc.details[0]["message"] if exc.details else exc.message
            raise ConversionRejected(
                detail,
                details=exc.details or [{"field": "file", "message": detail}],
            ) from exc
        return data

    def _fail(self, conversion_id: str, message: str, code: str = "conversion_failed") -> None:
        try:
            with self._database.unit_of_work() as uow:
                uow.conversions.mark_failed(conversion_id, code, message, utcnow())
        except Exception:
            logger.exception("Could not record conversion failure for %s", conversion_id)


def _output_filename(source_filename: str, target_format: str) -> str:
    stem = Path(source_filename).stem or "document"
    stem = stem.replace("/", "_").replace("\\", "_")
    if len(stem) > 180:
        stem = stem[:180]
    return f"{stem}.{target_format}"


def _mime(target_format: str) -> str:
    if target_format == "pdf":
        return "application/pdf"
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _client_message(target_format: str) -> str:
    if target_format == "docx":
        return "The PDF could not be converted to DOCX."
    return "The DOCX could not be converted to PDF."
