"""Resource lifecycle: upload, convert, download, and delete."""

from __future__ import annotations

import io
import sqlite3

from app import create_app
from tests.conftest import ExplodingConverter, FakeDocxToPdf, FakePdfToDocx, minimal_docx, minimal_pdf, upload


def test_health_and_index(client):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json["data"]["database"] == "sqlite"
    assert health.json["data"]["status"] == "ok"

    index = client.get("/")
    assert index.status_code == 200
    assert index.json["data"]["resources"]["documents"] == "/api/v1/documents"


def test_upload_convert_download_and_delete(client):
    created = upload(client, "Quarterly Report.pdf", minimal_pdf())
    assert created.status_code == 201
    assert created.headers["Location"].endswith(created.json["data"]["id"])
    document = created.json["data"]
    assert document["format"] == "pdf"
    assert document["role"] == "source"
    assert document["filename"] == "Quarterly Report.pdf"
    assert len(document["sha256"]) == 64

    listed = client.get("/api/v1/documents?format=pdf&role=source")
    assert listed.status_code == 200
    assert listed.json["meta"]["total"] == 1

    fetched = client.get(f"/api/v1/documents/{document['id']}")
    assert fetched.status_code == 200
    assert fetched.json["data"]["id"] == document["id"]

    content = client.get(f"/api/v1/documents/{document['id']}/content")
    assert content.status_code == 200
    assert content.data.startswith(b"%PDF-")
    assert "Quarterly Report.pdf" in content.headers["Content-Disposition"]

    converted = client.post(
        "/api/v1/conversions",
        json={"document_id": document["id"], "target_format": "docx"},
    )
    assert converted.status_code == 201, converted.json
    conversion = converted.json["data"]
    assert conversion["status"] == "completed"
    assert conversion["source_format"] == "pdf"
    assert conversion["target_format"] == "docx"
    assert conversion["error"] is None
    assert conversion["links"]["result"].endswith("/result")

    result = client.get(conversion["links"]["result"])
    assert result.status_code == 200
    assert result.data.startswith(b"PK")
    assert result.headers["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    output = client.get(conversion["links"]["output_document"])
    assert output.status_code == 200
    assert output.json["data"]["role"] == "output"
    assert output.json["data"]["filename"] == "Quarterly Report.docx"

    blocked = client.delete(f"/api/v1/documents/{document['id']}")
    assert blocked.status_code == 409

    removed = client.delete(f"/api/v1/conversions/{conversion['id']}")
    assert removed.status_code == 204
    assert client.get(f"/api/v1/conversions/{conversion['id']}").status_code == 404
    assert client.get(conversion["links"]["output_document"]).status_code == 404
    assert client.get(f"/api/v1/documents/{document['id']}").status_code == 200

    cascaded = client.delete(f"/api/v1/documents/{document['id']}?cascade=true")
    assert cascaded.status_code == 204
    assert client.get(f"/api/v1/documents/{document['id']}").status_code == 404


def test_docx_round_trip_metadata(client):
    created = upload(client, "notes.docx", minimal_docx())
    assert created.status_code == 201
    document_id = created.json["data"]["id"]
    converted = client.post(
        "/api/v1/conversions",
        json={"document_id": document_id, "target_format": "PDF"},
    )
    assert converted.status_code == 201
    assert converted.json["data"]["target_format"] == "pdf"
    assert client.get(converted.json["data"]["links"]["result"]).data.startswith(b"%PDF-")


def test_rejects_same_format_without_creating_a_job(client):
    created = upload(client, "notes.pdf", minimal_pdf())
    document_id = created.json["data"]["id"]
    response = client.post(
        "/api/v1/conversions",
        json={"document_id": document_id, "target_format": "pdf"},
    )
    assert response.status_code == 422
    assert response.json["error"]["details"][0]["field"] == "target_format"
    listed = client.get("/api/v1/conversions")
    assert listed.json["meta"]["total"] == 0


def test_failed_conversion_is_stored(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(tmp_path / "test.db"),
            "STORAGE_DIR": str(tmp_path / "storage"),
            "converters": [ExplodingConverter(), FakeDocxToPdf()],
        }
    )
    client = application.test_client()
    created = upload(client, "notes.pdf", minimal_pdf())
    document_id = created.json["data"]["id"]
    response = client.post(
        "/api/v1/conversions",
        json={"document_id": document_id, "target_format": "docx"},
    )
    assert response.status_code == 422
    assert response.json["error"]["code"] == "conversion_failed"
    conversion_id = response.json["error"]["conversion_id"]
    stored = client.get(f"/api/v1/conversions/{conversion_id}")
    assert stored.status_code == 200
    assert stored.json["data"]["status"] == "failed"
    assert stored.json["data"]["output_document_id"] is None
    result = client.get(f"/api/v1/conversions/{conversion_id}/result")
    assert result.status_code == 409


def test_validation_errors(client):
    missing = client.post("/api/v1/documents", data={}, content_type="multipart/form-data")
    assert missing.status_code == 422
    assert missing.json["error"]["details"][0]["field"] == "file"

    empty = upload(client, "empty.pdf", b"")
    assert empty.status_code == 422

    text = upload(client, "notes.txt", b"hello")
    assert text.status_code == 415

    mismatch = upload(client, "notes.pdf", minimal_docx())
    assert mismatch.status_code == 422
    assert "does not match" in mismatch.json["error"]["details"][0]["message"]

    truncated = upload(client, "notes.pdf", b"%PDF-1.4\nno end")
    assert truncated.status_code == 422

    extra = client.post(
        "/api/v1/documents",
        data={"file": (io.BytesIO(minimal_pdf()), "ok.pdf"), "note": "nope"},
        content_type="multipart/form-data",
    )
    assert extra.status_code == 422
    assert any(item["field"] == "note" for item in extra.json["error"]["details"])

    bad_json = client.post("/api/v1/conversions", data="[]", content_type="application/json")
    assert bad_json.status_code == 422

    bad_fields = client.post(
        "/api/v1/conversions",
        json={"document_id": "nope", "extra": True},
    )
    assert bad_fields.status_code == 422
    fields = {item["field"] for item in bad_fields.json["error"]["details"]}
    assert fields == {"document_id", "target_format", "extra"}

    bad_filter = client.get("/api/v1/conversions?status=done&per_page=500")
    assert bad_filter.status_code == 422
    filter_fields = {item["field"] for item in bad_filter.json["error"]["details"]}
    assert filter_fields == {"status", "per_page"}

    unknown = client.get("/api/v1/documents?page=0&sort=name")
    assert unknown.status_code == 422
    unknown_fields = {item["field"] for item in unknown.json["error"]["details"]}
    assert unknown_fields == {"page", "sort"}

    assert client.get("/api/v1/documents/not-a-uuid").status_code == 422
    assert client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.post("/api/v1/documents").status_code in {400, 415, 422}
    assert client.put("/api/v1/documents").status_code == 405
    assert client.get("/api/v1/missing").status_code == 404


def test_upload_limit(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(tmp_path / "test.db"),
            "STORAGE_DIR": str(tmp_path / "storage"),
            "MAX_UPLOAD_BYTES": 32,
        }
    )
    client = application.test_client()
    response = upload(client, "big.pdf", minimal_pdf() + (b"0" * 64))
    assert response.status_code == 413
    assert response.json["error"]["code"] == "payload_too_large"


def test_cascade_deletes_outputs(client):
    created = upload(client, "notes.pdf", minimal_pdf())
    document_id = created.json["data"]["id"]
    converted = client.post(
        "/api/v1/conversions",
        json={"document_id": document_id, "target_format": "docx"},
    )
    output_id = converted.json["data"]["output_document_id"]
    response = client.delete(f"/api/v1/documents/{document_id}?cascade=true")
    assert response.status_code == 204
    assert client.get(f"/api/v1/documents/{output_id}").status_code == 404
    assert client.get(f"/api/v1/conversions/{converted.json['data']['id']}").status_code == 404


def test_list_filters_misses_are_empty(client):
    upload(client, "notes.pdf", minimal_pdf())
    response = client.get(
        "/api/v1/conversions?document_id=00000000-0000-0000-0000-000000000000&target_format=docx"
    )
    assert response.status_code == 200
    assert response.json["data"] == []
    assert response.json["meta"]["total"] == 0


def test_interrupted_conversion_is_failed_on_startup(tmp_path):
    db_path = tmp_path / "test.db"
    storage = tmp_path / "storage"
    overrides = {
        "TESTING": True,
        "DATABASE_PATH": str(db_path),
        "STORAGE_DIR": str(storage),
        "converters": [FakePdfToDocx(), FakeDocxToPdf()],
    }
    client = create_app(overrides).test_client()
    created = upload(client, "notes.pdf", minimal_pdf())
    document_id = created.json["data"]["id"]
    orphan = storage / "22222222-2222-2222-2222-222222222222.pdf"
    orphan.write_bytes(minimal_pdf())

    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        INSERT INTO conversions (
            id, source_document_id, output_document_id, source_format,
            target_format, status, error_code, error_message, created_at,
            updated_at, finished_at
        ) VALUES (?, ?, NULL, 'pdf', 'docx', 'processing', NULL, NULL, ?, ?, NULL)
        """,
        (
            "11111111-1111-1111-1111-111111111111",
            document_id,
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()

    restarted = create_app(overrides).test_client()
    response = restarted.get("/api/v1/conversions/11111111-1111-1111-1111-111111111111")
    assert response.status_code == 200
    assert response.json["data"]["status"] == "failed"
    assert response.json["data"]["error"]["code"] == "interrupted"
    assert not orphan.exists()
