"""Persistence and API representations. These are not ORM models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Document:
    id: str
    filename: str
    format: str
    mime_type: str
    size_bytes: int
    sha256: str
    storage_name: str
    role: str
    created_at: str

    def to_api(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "format": self.format,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "role": self.role,
            "created_at": self.created_at,
            "links": {
                "self": f"/api/v1/documents/{self.id}",
                "content": f"/api/v1/documents/{self.id}/content",
            },
        }


@dataclass
class Conversion:
    id: str
    source_document_id: str
    output_document_id: str | None
    source_format: str
    target_format: str
    status: str
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str
    finished_at: str | None

    def to_api(self) -> dict:
        error = None
        if self.error_code or self.error_message:
            error = {"code": self.error_code, "message": self.error_message}
        links = {
            "self": f"/api/v1/conversions/{self.id}",
            "source_document": f"/api/v1/documents/{self.source_document_id}",
            "output_document": (
                f"/api/v1/documents/{self.output_document_id}" if self.output_document_id else None
            ),
            "result": f"/api/v1/conversions/{self.id}/result" if self.status == "completed" else None,
        }
        return {
            "id": self.id,
            "source_document_id": self.source_document_id,
            "output_document_id": self.output_document_id,
            "source_format": self.source_format,
            "target_format": self.target_format,
            "status": self.status,
            "error": error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
            "links": links,
        }
