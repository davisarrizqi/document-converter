"""Filesystem storage for document bytes. Names never come from the client."""

from __future__ import annotations

import os
import re
from pathlib import Path

from app.errors import AppError

STORAGE_NAME_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(pdf|docx)$"
)


class StoredFiles:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, storage_name: str) -> Path:
        if not STORAGE_NAME_RE.fullmatch(storage_name):
            raise AppError(
                "Stored file name is invalid.",
                status_code=500,
                code="internal_error",
            )
        path = (self.root / storage_name).resolve()
        if path.parent != self.root:
            raise AppError(
                "Stored file path escaped the storage directory.",
                status_code=500,
                code="internal_error",
            )
        return path

    def write(self, storage_name: str, data: bytes) -> None:
        path = self.resolve(storage_name)
        partial = path.with_name(path.name + ".part")
        partial.write_bytes(data)
        os.replace(partial, path)

    def read(self, storage_name: str) -> bytes:
        path = self.resolve(storage_name)
        if not path.is_file():
            raise AppError(
                "The file for this document is missing from storage.",
                status_code=500,
                code="storage_missing",
            )
        return path.read_bytes()

    def remove(self, storage_name: str) -> None:
        path = self.resolve(storage_name)
        try:
            path.unlink()
        except FileNotFoundError:
            return

    def sweep_orphans(self, referenced: set[str]) -> None:
        """Drop leftover files that are not referenced by the database."""

        for path in self.root.iterdir():
            if not path.is_file():
                continue
            if path.name.endswith(".part"):
                path.unlink(missing_ok=True)
                continue
            if STORAGE_NAME_RE.fullmatch(path.name) and path.name not in referenced:
                path.unlink(missing_ok=True)
