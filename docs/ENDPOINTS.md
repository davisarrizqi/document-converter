# Endpoint reference

Base URL for a local process started with `python run.py`:

```text
http://127.0.0.1:5000
```

All resource routes live under `/api/v1`. The API is not authenticated.

## Contents

- [Conventions](#conventions)
- [Errors](#errors)
- [Service index](#get-)
- [Health](#get-apiv1health)
- [Direct conversion](#post-apiv1convert)
- [Documents](#documents)
- [Conversions](#conversions)
- [Web API tester](#get-webdebug)
- [Validation rules](#validation-rules)

## Conventions

### Success body

A single resource:

```json
{ "data": {} }
```

A list also includes pagination:

```json
{
  "data": [],
  "meta": { "page": 1, "per_page": 20, "total": 0, "total_pages": 0 }
}
```

`DELETE` returns `204` with an empty body.

`POST` returns `201` and a `Location` header pointing at the new resource.

### Identifiers

Document and conversion ids are UUIDs. The server stores and returns them in lowercase. Clients may send uppercase; it is normalized. A path or field that is not a UUID is `422`, not `404`. An unknown but well-formed UUID is `404`.

### Timestamps

UTC, ISO-8601, with a `Z` suffix. Example: `2026-11-25T07:00:00.123456Z`.

### Formats

| Format | Extension | MIME type |
| --- | --- | --- |
| `pdf` | `.pdf` | `application/pdf` |
| `docx` | `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |

Enum values in JSON and query strings are case-insensitive (`PDF` and `pdf` are the same). Unknown values are rejected. They are not coerced into a default.

### Pagination

List endpoints accept:

| Parameter | Default | Rules |
| --- | --- | --- |
| `page` | `1` | Integer from 1 to 1000000 |
| `per_page` | `20` | Integer from 1 to 100 |

Results are ordered by `created_at` descending, then `id` descending. A page past the end returns an empty `data` array and the real `total`. It is not an error.

Unknown query parameters are `422`. Invalid parameters are reported together, not one at a time.

### Links

Resource JSON includes a `links` object of path-only URLs. Use them instead of building paths by hand when you can. They are relative to the same host.

## Errors

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": [
      { "field": "target_format", "message": "This field is required." }
    ]
  }
}
```

`details` is always an array. It is empty when the error is not tied to a field.

`conversion_failed` also includes `conversion_id` so the client can fetch the failed row:

```json
{
  "error": {
    "code": "conversion_failed",
    "message": "The PDF could not be converted to DOCX.",
    "details": [
      { "field": "file", "message": "The PDF could not be converted to DOCX." }
    ],
    "conversion_id": "6f1c4b0e-1a2b-4c3d-8e9f-001122334455"
  }
}
```

| HTTP | `code` | When |
| --- | --- | --- |
| 400 | `bad_request` | Malformed request that is not a field validation failure |
| 404 | `not_found` | Unknown resource, or no route |
| 405 | `method_not_allowed` | Verb not implemented for this path |
| 409 | `conflict` | The resource exists but the operation is illegal in its current state |
| 413 | `payload_too_large` | File or request body is over the limit |
| 415 | `unsupported_media_type` | Extension is not `.pdf` or `.docx` |
| 422 | `validation_error` | Field validation failed |
| 422 | `conversion_failed` | The converter ran and could not produce a valid file. The row is stored as `failed`. |
| 500 | `internal_error` | Unexpected server error |
| 500 | `storage_missing` | The database row exists but the file is gone |
| 503 | — | Health check only. The body is the success envelope with `status` `degraded`, not the error envelope. |

The server does not return stack traces or filesystem paths.

## GET /

Service index. Useful as a sanity check from a browser.

**Response `200`**

```json
{
  "data": {
    "name": "document-converter",
    "version": "1.0.0",
    "resources": {
      "health": "/api/v1/health",
      "convert": "/api/v1/convert",
      "documents": "/api/v1/documents",
      "conversions": "/api/v1/conversions",
      "debug": "/web/debug"
    }
  }
}
```

## GET /api/v1/health

Checks that the process can run `SELECT 1` against SQLite.

**Response `200`**

```json
{
  "data": {
    "status": "ok",
    "database": "sqlite",
    "database_status": "ok",
    "version": "1.0.0"
  }
}
```

**Response `503`** when SQLite cannot be opened. `status` is `degraded` and `database_status` is `error`. `database` stays `sqlite` so clients know which engine was configured.

## POST /api/v1/convert

Upload a PDF or DOCX and synchronously convert it to the opposite format in one request.
This creates a source document, an output document, and a conversion record.

**Request**

- `Content-Type: multipart/form-data`
- `file`: the PDF or DOCX upload
- `output`: `file` to stream the converted bytes, or `link` to return conversion metadata
- No other fields or files

When `output=file`, the response is the converted file with `201`, an attachment
`Content-Disposition`, and `X-Conversion-Id` and `X-Output-Document-Id` headers.
`Location` points to the conversion resource.

When `output=link`, the response is `201`:

```json
{
  "data": {
    "id": "6f1c4b0e-1a2b-4c3d-8e9f-001122334455",
    "status": "completed",
    "links": {
      "result": "/api/v1/conversions/6f1c4b0e-1a2b-4c3d-8e9f-001122334455/result"
    }
  },
  "link": "/api/v1/conversions/6f1c4b0e-1a2b-4c3d-8e9f-001122334455/result",
  "output": "link"
}
```

`output` is required and case-insensitive. Upload validation and conversion errors
are the same as for the document and conversion endpoints.

## Documents

A document is one stored file. `role` is `source` for uploads and `output` for files produced by a conversion.

```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "filename": "Quarterly Report.pdf",
  "format": "pdf",
  "mime_type": "application/pdf",
  "size_bytes": 48211,
  "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "role": "source",
  "created_at": "2026-11-25T07:00:00.000000Z",
  "links": {
    "self": "/api/v1/documents/3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "content": "/api/v1/documents/3fa85f64-5717-4562-b3fc-2c963f66afa6/content"
  }
}
```

`sha256` is the hex digest of the stored bytes. The storage path is not part of the API.

### POST /api/v1/documents

Upload one file.

**Request**

- `Content-Type: multipart/form-data`
- Field name: `file`
- No other form fields. Extra fields are `422`.

**Response `201`**

```text
Location: /api/v1/documents/{id}
```

Body is `{ "data": <document> }` with `role` equal to `source`.

**Errors**

| Status | Cause |
| --- | --- |
| 413 | File or multipart body is larger than the limit |
| 415 | Extension is not `.pdf` or `.docx` |
| 422 | Missing file, empty file, filename rejected, content does not match the extension, truncated PDF, DOCX that expands too far, extra form fields |

Filename rules:

- Path segments are stripped. `../../report.pdf` is stored as `report.pdf`.
- Control characters are rejected.
- Maximum length is 255 characters.
- Names that are empty, `.`, `..`, or start with `.` are rejected.
- The name is metadata. It is never used as a filesystem path.

Content rules:

- `.pdf` must start with `%PDF-` and contain `%%EOF` in the last 2048 bytes.
- `.docx` must be a ZIP archive that contains `word/document.xml`.
- The declared uncompressed size of a DOCX must be at most 20 times `MAX_UPLOAD_BYTES`.
- Extension and detected type must agree. A DOCX renamed to `.pdf` is `422`.

### GET /api/v1/documents

**Query**

| Parameter | Rules |
| --- | --- |
| `page`, `per_page` | See [Pagination](#pagination) |
| `format` | Optional. `pdf` or `docx` |
| `role` | Optional. `source` or `output` |

Any other query key is `422`.

**Response `200`**

```json
{
  "data": [ { "id": "...", "filename": "notes.pdf" } ],
  "meta": { "page": 1, "per_page": 20, "total": 1, "total_pages": 1 }
}
```

### GET /api/v1/documents/{document_id}

**Response `200`** with `{ "data": <document> }`.

**Errors:** `422` if `document_id` is not a UUID. `404` if it is a UUID and no row exists.

### GET /api/v1/documents/{document_id}/content

Downloads the bytes.

**Response `200`**

- `Content-Type` is the document MIME type.
- `Content-Disposition: attachment` uses the original filename.
- Body is the file. It is not wrapped in JSON.

**Errors:** `422`, `404`, or `500` with `storage_missing` if the row exists but the file does not.

### DELETE /api/v1/documents/{document_id}

**Query**

| Parameter | Default | Meaning |
| --- | --- | --- |
| `cascade` | `false` | `true` or `false` only |

**Response `204`** empty.

**Behavior**

- No conversions reference the document: the row and the file are deleted.
- One or more conversions reference it and `cascade` is omitted or `false`: `409`. Nothing is deleted.
- `cascade=true` on a **source** document: those conversions are deleted, their output documents and files are deleted, then the source is deleted.
- `cascade=true` on an **output** document: the conversion that produced it is deleted and the output file is deleted. The original upload is kept. If that output was itself converted again, those later conversions and their outputs are deleted too.

**Errors:** `422` for a bad id or a bad `cascade` value, `404` if the document does not exist, `409` if it is still referenced.

`409` body:

```json
{
  "error": {
    "code": "conflict",
    "message": "Document is referenced by one or more conversions.",
    "details": [
      {
        "field": "cascade",
        "message": "Delete those conversions first, or retry with cascade=true."
      }
    ]
  }
}
```

## Conversions

A conversion reads one existing document and writes a new output document.

```json
{
  "id": "6f1c4b0e-1a2b-4c3d-8e9f-001122334455",
  "source_document_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "output_document_id": "8c6b1a20-1111-4222-8333-444455556666",
  "source_format": "pdf",
  "target_format": "docx",
  "status": "completed",
  "error": null,
  "created_at": "2026-11-25T07:01:00.000000Z",
  "updated_at": "2026-11-25T07:01:02.000000Z",
  "finished_at": "2026-11-25T07:01:02.000000Z",
  "links": {
    "self": "/api/v1/conversions/6f1c4b0e-1a2b-4c3d-8e9f-001122334455",
    "source_document": "/api/v1/documents/3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "output_document": "/api/v1/documents/8c6b1a20-1111-4222-8333-444455556666",
    "result": "/api/v1/conversions/6f1c4b0e-1a2b-4c3d-8e9f-001122334455/result"
  }
}
```

| `status` | Meaning |
| --- | --- |
| `processing` | Converter is running. You only observe this if you read the row during the request, or if the process died and has not restarted yet. After restart it becomes `failed`. |
| `completed` | `output_document_id` is set. `error` is null. `links.result` is set. |
| `failed` | `output_document_id` is null. `error` is `{ "code", "message" }`. `links.result` is null. |

`finished_at` is set for both `completed` and `failed`. It is when the attempt settled, not only when it succeeded.

`error.code` on a failed row is `conversion_failed`, or `interrupted` when startup cleaned up a crashed attempt. `storage_missing` is used when the source file disappeared before the converter could run.

The call is synchronous. `POST` does not return until the status is `completed` or the error response has been written. There is no polling step for the happy path.

### POST /api/v1/conversions

**Request**

```http
Content-Type: application/json
```

```json
{
  "document_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "target_format": "docx"
}
```

Both fields are required. Unknown fields are `422`. `target_format` may be `pdf` or `docx`, any letter case.

**Response `201`**

```text
Location: /api/v1/conversions/{id}
```

Body is `{ "data": <conversion> }` and `status` is `completed`.

**Errors**

| Status | Cause |
| --- | --- |
| 404 | `document_id` is a UUID but no document exists |
| 422 `validation_error` | Body is not a JSON object, content type is not JSON, fields are missing or invalid, or the target format is not the opposite of the source |
| 422 `conversion_failed` | The library could not produce a valid file, or the output exceeded `MAX_OUTPUT_BYTES`. The conversion row exists and is `failed`. |
| 500 `storage_missing` | The source row exists but its file is gone. The conversion row is stored as `failed`. |

Wrong direction example. A PDF submitted with `"target_format": "pdf"`:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": [
      {
        "field": "target_format",
        "message": "A PDF document can only be converted to DOCX."
      }
    ]
  }
}
```

That response does not create a conversion.

Allowed pairs:

| Source document | `target_format` |
| --- | --- |
| `pdf` | `docx` |
| `docx` | `pdf` |

Converting an output document is allowed. A DOCX that was produced from a PDF can be converted back to PDF. That creates a new document; it does not replace the original.

### GET /api/v1/conversions

**Query**

| Parameter | Rules |
| --- | --- |
| `page`, `per_page` | See [Pagination](#pagination) |
| `status` | Optional. `processing`, `completed`, or `failed` |
| `document_id` | Optional UUID. Matches the **source** document only. A miss returns an empty list, not `404`. |
| `target_format` | Optional. `pdf` or `docx` |

**Response `200`** with `data` and `meta`.

### GET /api/v1/conversions/{conversion_id}

**Response `200`** with `{ "data": <conversion> }`.

**Errors:** `422` for a bad id, `404` if it does not exist.

### GET /api/v1/conversions/{conversion_id}/result

Downloads the output file of a completed conversion. This is a sub-resource of the conversion. The same bytes are available at the output document's `/content` URL.

**Response `200`**

- Attachment download.
- The filename is the source filename with the target extension. `Quarterly Report.pdf` converted to DOCX is downloaded as `Quarterly Report.docx`.

**Errors**

| Status | Cause |
| --- | --- |
| 404 | Unknown conversion, or the output document row is gone |
| 409 | Status is not `completed` |
| 422 | Bad id |
| 500 | Output row exists but the file is missing |

`409` body:

```json
{
  "error": {
    "code": "conflict",
    "message": "This conversion has no result to download.",
    "details": [
      { "field": "status", "message": "Conversion status is failed." }
    ]
  }
}
```

### DELETE /api/v1/conversions/{conversion_id}

**Response `204`** empty.

Deletes the conversion row. If an output document exists, that row and its file are deleted too. The source document is not deleted.

A second delete is `404`.

**Errors:** `422` for a bad id, `404` if the conversion does not exist.

## GET /web/debug

Returns a browser-based API tester. It can send GET, POST, PUT, and DELETE requests;
choose JSON or multipart bodies; inspect status and headers; and download binary
responses.

## Validation rules

These are enforced on the server. Clients should still check them to avoid a round trip.

1. Upload field name is `file`. There must be exactly one file.
2. Extension is `.pdf` or `.docx`. Comparison is case-insensitive.
3. File size is from 1 byte through `MAX_UPLOAD_BYTES` (default 20 MiB). The multipart request may be up to 1 MiB larger than that, for boundaries and headers. Over that, the status is `413`.
4. PDF magic and a trailing `%%EOF` are required. A cut-off upload is rejected.
5. DOCX must be a real Office ZIP, not a renamed PDF and not a ZIP without `word/document.xml`.
6. Conversion JSON is an object with `document_id` and `target_format` only.
7. The target format must be the other format. Same-format requests are rejected before a job is created.
8. Query strings only accept the parameters listed for that route.
9. Integers must be canonical decimal integers (`1`, `20`). `1.5`, `1e2`, and `+1` are rejected.
10. After conversion, the output is inspected the same way. A converter that writes the wrong type fails the job.
11. Direct conversion requires `output=file` or `output=link`.

Every independent field problem in one request is returned in `details`. Example: a bad `document_id`, a missing `target_format`, and an unknown extra property are three entries in one `422`.
