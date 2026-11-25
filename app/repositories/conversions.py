"""Conversion persistence. No business rules and no Flask imports."""

from __future__ import annotations

import sqlite3

from app.models import Conversion


class ConversionRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert(self, conversion: Conversion) -> Conversion:
        self._connection.execute(
            """
            INSERT INTO conversions (
                id, source_document_id, output_document_id, source_format,
                target_format, status, error_code, error_message, created_at,
                updated_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversion.id,
                conversion.source_document_id,
                conversion.output_document_id,
                conversion.source_format,
                conversion.target_format,
                conversion.status,
                conversion.error_code,
                conversion.error_message,
                conversion.created_at,
                conversion.updated_at,
                conversion.finished_at,
            ),
        )
        return conversion

    def get(self, conversion_id: str) -> Conversion | None:
        row = self._connection.execute(
            "SELECT * FROM conversions WHERE id = ?",
            (conversion_id,),
        ).fetchone()
        return _map_conversion(row) if row else None

    def list(
        self,
        *,
        page: int,
        per_page: int,
        status: str | None = None,
        document_id: str | None = None,
        target_format: str | None = None,
    ) -> tuple[list[Conversion], int]:
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if document_id is not None:
            clauses.append("source_document_id = ?")
            params.append(document_id)
        if target_format is not None:
            clauses.append("target_format = ?")
            params.append(target_format)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        total = self._connection.execute(
            f"SELECT COUNT(*) AS count FROM conversions {where}",
            params,
        ).fetchone()["count"]
        rows = self._connection.execute(
            f"""
            SELECT * FROM conversions
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, (page - 1) * per_page],
        ).fetchall()
        return [_map_conversion(row) for row in rows], int(total)

    def list_for_document(self, document_id: str) -> list[Conversion]:
        rows = self._connection.execute(
            """
            SELECT * FROM conversions
            WHERE source_document_id = ? OR output_document_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (document_id, document_id),
        ).fetchall()
        return [_map_conversion(row) for row in rows]

    def mark_completed(
        self,
        conversion_id: str,
        output_document_id: str,
        updated_at: str,
    ) -> None:
        self._connection.execute(
            """
            UPDATE conversions
            SET status = 'completed',
                output_document_id = ?,
                error_code = NULL,
                error_message = NULL,
                updated_at = ?,
                finished_at = ?
            WHERE id = ?
            """,
            (output_document_id, updated_at, updated_at, conversion_id),
        )

    def mark_failed(
        self,
        conversion_id: str,
        error_code: str,
        error_message: str,
        updated_at: str,
    ) -> None:
        self._connection.execute(
            """
            UPDATE conversions
            SET status = 'failed',
                output_document_id = NULL,
                error_code = ?,
                error_message = ?,
                updated_at = ?,
                finished_at = ?
            WHERE id = ?
            """,
            (error_code, error_message, updated_at, updated_at, conversion_id),
        )

    def delete(self, conversion_id: str) -> None:
        self._connection.execute("DELETE FROM conversions WHERE id = ?", (conversion_id,))


def _map_conversion(row: sqlite3.Row) -> Conversion:
    return Conversion(
        id=row["id"],
        source_document_id=row["source_document_id"],
        output_document_id=row["output_document_id"],
        source_format=row["source_format"],
        target_format=row["target_format"],
        status=row["status"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        finished_at=row["finished_at"],
    )
