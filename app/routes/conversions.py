"""``/api/v1/conversions`` resource."""

from __future__ import annotations

from io import BytesIO

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from app.errors import ConflictError, ValidationError
from app.validation import (
    OPPOSITE_FORMAT,
    parse_conversion_body,
    parse_conversion_filters,
    parse_direct_conversion_output,
    parse_uuid_path,
    read_upload,
)

conversions_bp = Blueprint("conversions", __name__)


def _container():
    return current_app.extensions["container"]


def _page_meta(page: int, per_page: int, total: int) -> dict:
    total_pages = (total + per_page - 1) // per_page if total else 0
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    }


@conversions_bp.post("/conversions")
def create_conversion():
    if not request.is_json:
        raise ValidationError(
            [{"field": "body", "message": "Content-Type must be application/json."}]
        )
    payload = request.get_json(silent=True)
    document_id, target_format = parse_conversion_body(payload)
    conversion = _container().conversions.create(document_id, target_format)
    response = jsonify({"data": conversion.to_api()})
    response.status_code = 201
    response.headers["Location"] = f"/api/v1/conversions/{conversion.id}"
    return response


@conversions_bp.post("/convert")
def convert_upload():
    container = _container()
    extra = [name for name in request.files if name != "file"]
    extra.extend(name for name in request.form if name != "output")
    validation_errors: list[dict] = []
    upload = None
    output_type = None
    try:
        upload = read_upload(
            request.files.get("file"),
            max_bytes=container.settings.max_upload_bytes,
            extra_fields=extra,
        )
    except ValidationError as exc:
        validation_errors.extend(exc.details)
    try:
        output_type = parse_direct_conversion_output(request.form)
    except ValidationError as exc:
        validation_errors.extend(exc.details)
    if validation_errors:
        raise ValidationError(validation_errors)
    assert upload is not None and output_type is not None

    document = container.documents.create(upload)
    conversion = container.conversions.create(
        document.id,
        OPPOSITE_FORMAT[document.format],
    )
    if not conversion.output_document_id:
        raise ConflictError("The conversion did not produce an output document.")

    result_link = f"/api/v1/conversions/{conversion.id}/result"
    if output_type == "link":
        body = conversion.to_api()
        response = jsonify({"data": body, "link": result_link, "output": "link"})
        response.status_code = 201
        response.headers["Location"] = f"/api/v1/conversions/{conversion.id}"
        return response

    output_document = container.documents.get(conversion.output_document_id)
    path = container.documents.open_path(output_document)
    response = send_file(
        BytesIO(path.read_bytes()),
        mimetype=output_document.mime_type,
        as_attachment=True,
        download_name=output_document.filename,
        max_age=0,
    )
    response.status_code = 201
    response.headers["Location"] = f"/api/v1/conversions/{conversion.id}"
    response.headers["X-Conversion-Id"] = conversion.id
    response.headers["X-Output-Document-Id"] = output_document.id
    return response


@conversions_bp.get("/conversions")
def list_conversions():
    page, per_page, status, document_id, target_format = parse_conversion_filters(request.args)
    conversions, total = _container().conversions.list(
        page=page,
        per_page=per_page,
        status=status,
        document_id=document_id,
        target_format=target_format,
    )
    return jsonify(
        {
            "data": [conversion.to_api() for conversion in conversions],
            "meta": _page_meta(page, per_page, total),
        }
    )


@conversions_bp.get("/conversions/<conversion_id>")
def get_conversion(conversion_id: str):
    conversion_id = parse_uuid_path(conversion_id, "conversion_id")
    conversion = _container().conversions.get(conversion_id)
    return jsonify({"data": conversion.to_api()})


@conversions_bp.get("/conversions/<conversion_id>/result")
def download_result(conversion_id: str):
    conversion_id = parse_uuid_path(conversion_id, "conversion_id")
    container = _container()
    conversion = container.conversions.get(conversion_id)
    if conversion.status != "completed" or not conversion.output_document_id:
        raise ConflictError(
            "This conversion has no result to download.",
            details=[{"field": "status", "message": f"Conversion status is {conversion.status}."}],
        )
    document = container.documents.get(conversion.output_document_id)
    path = container.documents.open_path(document)
    return send_file(
        BytesIO(path.read_bytes()),
        mimetype=document.mime_type,
        as_attachment=True,
        download_name=document.filename,
        max_age=0,
    )


@conversions_bp.delete("/conversions/<conversion_id>")
def delete_conversion(conversion_id: str):
    conversion_id = parse_uuid_path(conversion_id, "conversion_id")
    _container().conversions.delete(conversion_id)
    return Response(status=204)
