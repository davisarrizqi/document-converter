"""API error types and JSON error handlers."""

from __future__ import annotations

import logging

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        details: list[dict] | None = None,
        status_code: int | None = None,
        code: str | None = None,
        conversion_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or []
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.conversion_id = conversion_id

    def to_body(self) -> dict:
        error = {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
        if self.conversion_id:
            error["conversion_id"] = self.conversion_id
        return {"error": error}


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"

    def __init__(self, details: list[dict], message: str = "Request validation failed.") -> None:
        super().__init__(message, details=details)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class UnsupportedMediaError(AppError):
    status_code = 415
    code = "unsupported_media_type"


class ConversionRejected(AppError):
    status_code = 422
    code = "conversion_failed"


def json_error(
    code: str,
    message: str,
    status: int,
    details: list[dict] | None = None,
):
    return jsonify({"error": {"code": code, "message": message, "details": details or []}}), status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        return jsonify(error.to_body()), error.status_code

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(_error: RequestEntityTooLarge):
        container = app.extensions.get("container")
        limit = container.settings.max_upload_bytes if container else None
        message = "The request body is too large."
        if limit is not None:
            message = f"The request body exceeds the upload limit of {limit} bytes."
        return json_error("payload_too_large", message, 413, [{"field": "file", "message": message}])

    @app.errorhandler(404)
    def handle_not_found(_error: HTTPException):
        return json_error("not_found", "Resource not found.", 404)

    @app.errorhandler(405)
    def handle_method_not_allowed(_error: HTTPException):
        return json_error("method_not_allowed", "Method not allowed.", 405)

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):
        if isinstance(error, HTTPException):
            return json_error(
                "bad_request" if error.code and error.code < 500 else "internal_error",
                error.description or "Request failed.",
                error.code or 500,
            )
        logger.exception("Unhandled error")
        return json_error("internal_error", "An unexpected error occurred.", 500)
