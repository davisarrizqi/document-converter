"""Document use cases: store, list, fetch, and delete."""

from __future__ import annotations

import logging
import uuid

from app.database import Database
from app.errors import ConflictError, NotFoundError
from app.models import Document
from app.storage import StoredFiles
from app.timeutil import utcnow
from app.validation import AcceptedUpload

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self, database: Database, files: StoredFiles) -> None:
        self._database = database
        self._files = files

    def create(self, upload: AcceptedUpload) -> Document:
        document_id = str(uuid.uuid4())
        storage_name = f"{document_id}.{upload.format}"
        document = Document(
            id=document_id,
            filename=upload.filename,
            format=upload.format,
            mime_type=upload.mime_type,
            size_bytes=len(upload.data),
            sha256=upload.sha256,
            storage_name=storage_name,
            role="source",
            created_at=utcnow(),
        )
        self._files.write(storage_name, upload.data)
        try:
            with self._database.unit_of_work() as uow:
                uow.documents.insert(document)
        except Exception:
            logger.exception("Rolling back stored upload %s", storage_name)
            self._files.remove(storage_name)
            raise
        return document

    def get(self, document_id: str) -> Document:
        with self._database.unit_of_work() as uow:
            document = uow.documents.get(document_id)
        if document is None:
            raise NotFoundError("Document not found.")
        return document

    def list(
        self,
        *,
        page: int,
        per_page: int,
        format: str | None,
        role: str | None,
    ) -> tuple[list[Document], int]:
        with self._database.unit_of_work() as uow:
            return uow.documents.list(page=page, per_page=per_page, format=format, role=role)

    def delete(self, document_id: str, *, cascade: bool) -> None:
        storage_names: list[str] = []
        with self._database.unit_of_work() as uow:
            document = uow.documents.get(document_id)
            if document is None:
                raise NotFoundError("Document not found.")
            related = uow.conversions.list_for_document(document_id)
            if related and not cascade:
                raise ConflictError(
                    "Document is referenced by one or more conversions.",
                    details=[
                        {
                            "field": "cascade",
                            "message": "Delete those conversions first, or retry with cascade=true.",
                        }
                    ],
                )
            output_ids: list[str] = []
            storage_names.append(document.storage_name)
            for conversion in related:
                output_id = conversion.output_document_id
                if output_id and output_id != document.id:
                    output = uow.documents.get(output_id)
                    if output is not None:
                        output_ids.append(output.id)
                        storage_names.append(output.storage_name)
            for conversion in related:
                uow.conversions.delete(conversion.id)
            for output_id in output_ids:
                uow.documents.delete(output_id)
            uow.documents.delete(document.id)
        for storage_name in storage_names:
            self._files.remove(storage_name)

    def open_path(self, document: Document):
        path = self._files.resolve(document.storage_name)
        if not path.is_file():
            from app.errors import AppError

            raise AppError(
                "The file for this document is missing from storage.",
                status_code=500,
                code="storage_missing",
            )
        return path
