"""SQLite URL parsing."""

from pathlib import Path

import pytest

from app.config import PROJECT_ROOT, ConfigError, resolve_database_url


def test_relative_sqlite_url_is_inside_the_project():
    path = resolve_database_url("sqlite:///data/document_converter.db")
    assert path == PROJECT_ROOT / "data" / "document_converter.db"


def test_absolute_sqlite_url():
    path = resolve_database_url("sqlite:////tmp/converter.db")
    assert path == Path("/tmp/converter.db")


def test_non_sqlite_url_is_rejected():
    with pytest.raises(ConfigError):
        resolve_database_url("postgresql://localhost/converter")
