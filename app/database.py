"""SQLite connection lifecycle. Repositories never open their own connections."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.repositories.conversions import ConversionRepository
from app.repositories.documents import DocumentRepository
from app.timeutil import utcnow

SCHEMA_PATH = Path(__file__).resolve().parent / "db" / "schema.sql"


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        script = SCHEMA_PATH.read_text(encoding="utf-8")
        connection = self.connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(script)
        finally:
            connection.close()

    def ping(self) -> None:
        connection = self.connect()
        try:
            connection.execute("SELECT 1")
        finally:
            connection.close()

    def fail_interrupted_conversions(self) -> None:
        """A processing row at startup means the previous process died mid-convert."""

        now = utcnow()
        connection = self.connect()
        try:
            connection.execute(
                """
                UPDATE conversions
                SET status = 'failed',
                    error_code = 'interrupted',
                    error_message = 'Conversion was interrupted before it finished.',
                    updated_at = ?,
                    finished_at = ?
                WHERE status = 'processing'
                """,
                (now, now),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def storage_names(self) -> set[str]:
        connection = self.connect()
        try:
            rows = connection.execute("SELECT storage_name FROM documents").fetchall()
        finally:
            connection.close()
        return {row["storage_name"] for row in rows}

    @contextmanager
    def unit_of_work(self):
        connection = self.connect()
        try:
            yield UnitOfWork(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class UnitOfWork:
    """One transaction shared by every repository call inside the block."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.documents = DocumentRepository(connection)
        self.conversions = ConversionRepository(connection)
