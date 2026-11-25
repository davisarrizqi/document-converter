"""Application factory for the document converter API."""

from __future__ import annotations

import logging
import os

from flask import Flask

from app.config import Settings
from app.container import Container
from app.converters import ConverterRegistry, default_converters
from app.database import Database
from app.errors import register_error_handlers
from app.routes import register_blueprints
from app.storage import StoredFiles
from app.version import __version__

__all__ = ["__version__", "create_app"]


def create_app(overrides: dict | None = None) -> Flask:
    """Build a Flask app.

    ``overrides`` is for tests and embeds. Recognized keys: TESTING,
    DATABASE_PATH, STORAGE_DIR, MAX_UPLOAD_BYTES, MAX_OUTPUT_BYTES,
    SECRET_KEY, and ``converters`` (a list of converter instances).
    """

    overrides = dict(overrides or {})
    settings = Settings.from_env(overrides)
    _configure_logging()

    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    database = Database(settings.database_path)
    database.initialize()
    database.fail_interrupted_conversions()

    files = StoredFiles(settings.storage_dir)
    files.sweep_orphans(database.storage_names())

    converters = overrides.get("converters") or default_converters()
    container = Container(
        settings=settings,
        database=database,
        files=files,
        converters=ConverterRegistry(converters),
    )

    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.secret_key
    # Multipart bodies are slightly larger than the file itself.
    app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_bytes + (1024 * 1024)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.config["JSON_SORT_KEYS"] = False
    app.extensions["container"] = container

    register_error_handlers(app)
    register_blueprints(app)

    if settings.secret_key == "dev-change-me" and not settings.testing:
        app.logger.warning("SECRET_KEY is the development default. Set a real value in .env.")

    return app


def _configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
