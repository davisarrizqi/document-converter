"""Document persistence. No business rules and no Flask imports."""

from __future__ import annotations

import sqlite3

from app.models import Document


class DocumentRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert(self, document: Document) -> Document:
        self._connection.execute(
            """
            INSERT INTO documents (
                id, filename, format, mime_type, size_bytes, sha256,
                storage_name, role, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document.id,
                document.filename,
                document.format,
                document.mime_type,
                document.size_bytes,
                document.sha256,
                document.storage_name,
                document.role,
                document.created_at,
            ),
        )
        return document

    def get(self, document_id: str) -> Document | None:
        row = self._connection.execute(
            "SELECT * FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        return _map_document(row) if row else None

    def list(
        self,
        *,
        page: int,
        per_page: int,
        format: str | None = None,
        role: str | None = None,
    ) -> tuple[list[Document], int]:
        clauses: list[str] = []
        params: list[object] = []
        if format is not None:
            clauses.append("format = ?")
            params.append(format)
        if role is not None:
            clauses.append("role = ?")
            params.append(role)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        total = self._connection.execute(
            f"SELECT COUNT(*) AS count FROM documents {where}",
            params,
        ).fetchone()["count"]
        rows = self._connection.execute(
            f"""
            SELECT * FROM documents
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, (page - 1) * per_page],
        ).fetchall()
        return [_map_document(row) for row in rows], int(total)

    def delete(self, document_id: str) -> None:
        self._connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))


def _map_document(row: sqlite3.Row) -> Document:
    return Document(
        id=row["id"],
        filename=row["filename"],
        format=row["format"],
        mime_type=row["mime_type"],
        size_bytes=row["size_bytes"],
        sha256=row["sha256"],
        storage_name=row["storage_name"],
        role=row["role"],
        created_at=row["created_at"],
    )
