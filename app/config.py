"""Runtime settings. SQLite is the default and only supported database."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = "sqlite:///data/document_converter.db"
DEFAULT_SECRET_KEY = "dev-change-me"


class ConfigError(RuntimeError):
    """Raised when the process cannot start because configuration is invalid."""


@dataclass(frozen=True)
class Settings:
    secret_key: str
    database_path: Path
    storage_dir: Path
    max_upload_bytes: int
    max_output_bytes: int
    testing: bool

    @classmethod
    def from_env(cls, overrides: dict) -> Settings:
        testing = bool(overrides.get("TESTING", False))
        if "DATABASE_PATH" in overrides:
            database_path = Path(overrides["DATABASE_PATH"]).expanduser()
            if not database_path.is_absolute():
                database_path = PROJECT_ROOT / database_path
        else:
            database_path = resolve_database_url(
                os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
            )

        if "STORAGE_DIR" in overrides:
            storage_dir = _resolve_dir(str(overrides["STORAGE_DIR"]))
        else:
            storage_dir = _resolve_dir(os.getenv("STORAGE_DIR", "data/storage"))

        max_upload = int(
            overrides.get("MAX_UPLOAD_BYTES", _positive_int_env("MAX_UPLOAD_BYTES", 20 * 1024 * 1024))
        )
        max_output = int(
            overrides.get(
                "MAX_OUTPUT_BYTES",
                _positive_int_env("MAX_OUTPUT_BYTES", 50 * 1024 * 1024),
            )
        )
        if max_upload <= 0 or max_output <= 0:
            raise ConfigError("Upload and output size limits must be greater than zero.")

        return cls(
            secret_key=str(overrides.get("SECRET_KEY", os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY))),
            database_path=database_path.resolve(),
            storage_dir=storage_dir,
            max_upload_bytes=max_upload,
            max_output_bytes=max_output,
            testing=testing,
        )


def resolve_database_url(url: str) -> Path:
    """Resolve a SQLAlchemy-style SQLite URL to a filesystem path.

    ``sqlite:///data/document_converter.db`` is relative to the project root.
    ``sqlite:////tmp/converter.db`` is absolute.
    """

    if not isinstance(url, str) or not url.startswith("sqlite:"):
        raise ConfigError(
            "DATABASE_URL must be a sqlite URL, for example "
            "sqlite:///data/document_converter.db"
        )
    rest = url[len("sqlite:") :]
    if not rest.startswith("///"):
        raise ConfigError(
            "DATABASE_URL must look like sqlite:///data/document_converter.db "
            "(three slashes for a relative path, four for an absolute path)."
        )
    path_part = rest[3:]
    if path_part == "":
        raise ConfigError("DATABASE_URL is missing a database file path.")
    path = Path(path_part)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _resolve_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero.")
    return value
