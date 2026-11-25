"""Liveness of the process and the SQLite database."""

from __future__ import annotations

import logging

from flask import Blueprint, current_app, jsonify

from app.version import __version__

logger = logging.getLogger(__name__)
health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    container = current_app.extensions["container"]
    try:
        container.database.ping()
        database_status = "ok"
    except Exception:
        logger.exception("Database health check failed")
        database_status = "error"
    status = "ok" if database_status == "ok" else "degraded"
    body = {
        "data": {
            "status": status,
            "database": "sqlite",
            "database_status": database_status,
            "version": __version__,
        }
    }
    return jsonify(body), (200 if database_status == "ok" else 503)
