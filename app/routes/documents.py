"""``/api/v1/documents`` resource."""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from app.validation import parse_cascade, parse_document_filters, parse_uuid_path, read_upload

documents_bp = Blueprint("documents", __name__)


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


@documents_bp.post("/documents")
def create_document():
    container = _container()
    extra = [name for name in request.files if name != "file"]
    extra.extend(request.form.keys())
    upload = read_upload(
        request.files.get("file"),
        max_bytes=container.settings.max_upload_bytes,
        extra_fields=extra,
    )
    document = container.documents.create(upload)
    response = jsonify({"data": document.to_api()})
    response.status_code = 201
    response.headers["Location"] = f"/api/v1/documents/{document.id}"
    return response


@documents_bp.get("/documents")
def list_documents():
    page, per_page, format_name, role = parse_document_filters(request.args)
    documents, total = _container().documents.list(
        page=page,
        per_page=per_page,
        format=format_name,
        role=role,
    )
    return jsonify(
        {
            "data": [document.to_api() for document in documents],
            "meta": _page_meta(page, per_page, total),
        }
    )


@documents_bp.get("/documents/<document_id>")
def get_document(document_id: str):
    document_id = parse_uuid_path(document_id, "document_id")
    document = _container().documents.get(document_id)
    return jsonify({"data": document.to_api()})


@documents_bp.get("/documents/<document_id>/content")
def download_document(document_id: str):
    document_id = parse_uuid_path(document_id, "document_id")
    service = _container().documents
    document = service.get(document_id)
    path = service.open_path(document)
    return send_file(
        path,
        mimetype=document.mime_type,
        as_attachment=True,
        download_name=document.filename,
        max_age=0,
    )


@documents_bp.delete("/documents/<document_id>")
def delete_document(document_id: str):
    document_id = parse_uuid_path(document_id, "document_id")
    cascade = parse_cascade(request.args)
    _container().documents.delete(document_id, cascade=cascade)
    return Response(status=204)
