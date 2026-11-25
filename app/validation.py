"""Server-side request validation.

Validators accumulate every independent field error they can see, then raise
once. Streaming checks (upload size) still fail immediately because the rest
of the body must not be trusted past the limit.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from werkzeug.datastructures import FileStorage, ImmutableMultiDict

from app.errors import PayloadTooLargeError, UnsupportedMediaError, ValidationError

PDF = "pdf"
DOCX = "docx"
FORMATS = {PDF, DOCX}
ROLES = {"source", "output"}
STATUSES = {"processing", "completed", "failed"}
DIRECT_OUTPUTS = {"file", "link"}
MIME_TYPES = {
    PDF: "application/pdf",
    DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
EXTENSIONS = {PDF: ".pdf", DOCX: ".docx"}
OPPOSITE_FORMAT = {PDF: DOCX, DOCX: PDF}

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_INT_RE = re.compile(r"^-?\d+$")


@dataclass(frozen=True)
class AcceptedUpload:
    filename: str
    format: str
    mime_type: str
    data: bytes
    sha256: str


class _Check:
    def __init__(self) -> None:
        self.errors: list[dict] = []

    def add(self, field: str, message: str) -> None:
        self.errors.append({"field": field, "message": message})

    def ok(self, condition: bool, field: str, message: str) -> bool:
        if not condition:
            self.add(field, message)
        return condition

    def finish(self) -> None:
        if self.errors:
            raise ValidationError(self.errors)


def _reject_unknown(check: _Check, args: ImmutableMultiDict, allowed: set[str]) -> None:
    for name in sorted(set(args.keys()) - allowed):
        check.add(name, "Unknown query parameter.")


def parse_document_filters(args: ImmutableMultiDict) -> tuple[int, int, str | None, str | None]:
    check = _Check()
    _reject_unknown(check, args, {"page", "per_page", "format", "role"})
    page = _optional_int(check, args.get("page"), "page", default=1, minimum=1, maximum=1_000_000)
    per_page = _optional_int(
        check, args.get("per_page"), "per_page", default=20, minimum=1, maximum=100
    )
    format_value = _optional_choice(check, args.get("format"), "format", FORMATS)
    role = _optional_choice(check, args.get("role"), "role", ROLES)
    check.finish()
    assert page is not None and per_page is not None
    return page, per_page, format_value, role


def parse_conversion_filters(
    args: ImmutableMultiDict,
) -> tuple[int, int, str | None, str | None, str | None]:
    check = _Check()
    _reject_unknown(check, args, {"page", "per_page", "status", "document_id", "target_format"})
    page = _optional_int(check, args.get("page"), "page", default=1, minimum=1, maximum=1_000_000)
    per_page = _optional_int(
        check, args.get("per_page"), "per_page", default=20, minimum=1, maximum=100
    )
    status = _optional_choice(check, args.get("status"), "status", STATUSES)
    target_format = _optional_choice(check, args.get("target_format"), "target_format", FORMATS)
    document_id = _optional_uuid(check, args.get("document_id"), "document_id")
    check.finish()
    assert page is not None and per_page is not None
    return page, per_page, status, document_id, target_format


def parse_cascade(args: ImmutableMultiDict) -> bool:
    check = _Check()
    _reject_unknown(check, args, {"cascade"})
    raw = args.get("cascade", "false")
    if not isinstance(raw, str) or raw.strip().lower() not in {"true", "false"}:
        check.add("cascade", "Must be true or false.")
        cascade = False
    else:
        cascade = raw.strip().lower() == "true"
    check.finish()
    return cascade


def parse_uuid_path(value: str, field: str = "id") -> str:
    if not isinstance(value, str) or not _UUID_RE.fullmatch(value.strip()):
        raise ValidationError(
            [{"field": field, "message": "Must be a UUID."}]
        )
    return value.strip().lower()


def parse_conversion_body(payload: object) -> tuple[str, str]:
    check = _Check()
    if not isinstance(payload, dict):
        raise ValidationError([{"field": "body", "message": "JSON body must be an object."}])
    extra = sorted(set(payload.keys()) - {"document_id", "target_format"})
    for field in extra:
        check.add(field, "Unknown field.")
    if "document_id" not in payload:
        check.add("document_id", "This field is required.")
        document_id = None
    else:
        document_id = _required_uuid(check, payload.get("document_id"), "document_id")
    if "target_format" not in payload:
        check.add("target_format", "This field is required.")
        target_format = None
    else:
        target_format = _required_choice(check, payload.get("target_format"), "target_format", FORMATS)
    check.finish()
    assert document_id is not None and target_format is not None
    return document_id, target_format


def parse_direct_conversion_output(form: ImmutableMultiDict) -> str:
    check = _Check()
    if "output" not in form:
        check.add("output", "This field is required.")
        output = None
    else:
        output = _required_choice(
            check,
            form.get("output"),
            "output",
            DIRECT_OUTPUTS,
        )
    check.finish()
    assert output is not None
    return output


def read_upload(file: FileStorage | None, *, max_bytes: int, extra_fields: list[str]) -> AcceptedUpload:
    check = _Check()
    for field in extra_fields:
        check.add(field, "Unknown form field.")
    if file is None:
        check.add("file", "A file upload is required.")
        check.finish()

    filename = _sanitize_filename(check, file.filename or "")
    extension = Path(filename).suffix.lower() if filename else ""
    if filename and extension not in {".pdf", ".docx"}:
        if check.errors:
            check.add("file", "Allowed extensions are .pdf and .docx.")
            check.finish()
        raise UnsupportedMediaError(
            "Only PDF and DOCX files are accepted.",
            details=[{"field": "file", "message": "Allowed extensions are .pdf and .docx."}],
        )

    data = _read_limited(file, max_bytes)
    if not data:
        check.add("file", "File is empty.")
    if not filename or not data:
        check.finish()

    detected = _detect_format(data, max_bytes)
    expected = PDF if extension == ".pdf" else DOCX
    if detected is None:
        check.add("file", f"File content is not a valid {expected.upper()} document.")
    elif detected != expected:
        check.add("file", f"File content does not match the {extension} extension.")
    check.finish()
    assert detected is not None
    return AcceptedUpload(
        filename=filename,
        format=detected,
        mime_type=MIME_TYPES[detected],
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
    )


def assert_output(data: bytes, target_format: str, max_output_bytes: int) -> None:
    if not data:
        raise ValidationError([{"field": "file", "message": "Converter produced an empty file."}])
    if len(data) > max_output_bytes:
        raise PayloadTooLargeError(
            "Converter output exceeds the configured limit.",
            details=[{"field": "file", "message": f"Output is larger than {max_output_bytes} bytes."}],
        )
    detected = _detect_format(data, max_output_bytes)
    if detected != target_format:
        raise ValidationError(
            [{"field": "file", "message": f"Converter did not produce a valid {target_format.upper()} file."}]
        )


def _sanitize_filename(check: _Check, filename: str) -> str:
    name = filename.replace("\\", "/").split("/")[-1].replace("\x00", "").strip()
    if not check.ok(bool(name), "file", "Filename is required."):
        return ""
    if any(ord(char) < 32 for char in name):
        check.add("file", "Filename contains control characters.")
        return ""
    if name in {".", ".."} or name.startswith("."):
        check.add("file", "Filename is not allowed.")
        return ""
    if len(name) > 255:
        check.add("file", "Filename must be 255 characters or fewer.")
        return ""
    return name


def _read_limited(file: FileStorage, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = file.stream.read(64 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise PayloadTooLargeError(
                "The uploaded file exceeds the configured limit.",
                details=[{"field": "file", "message": f"File is larger than {max_bytes} bytes."}],
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _detect_format(data: bytes, max_uncompressed: int) -> str | None:
    if data.startswith(b"%PDF-"):
        tail = data[-2048:]
        if b"%%EOF" not in tail:
            return None
        return PDF
    if data.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                if "word/document.xml" not in names:
                    return None
                expanded = sum(info.file_size for info in archive.infolist())
        except zipfile.BadZipFile:
            return None
        limit = max(max_uncompressed * 20, 1)
        if expanded > limit:
            raise ValidationError(
                [
                    {
                        "field": "file",
                        "message": "DOCX archive expands beyond the allowed size.",
                    }
                ]
            )
        return DOCX
    return None


def _optional_int(
    check: _Check,
    raw: str | None,
    field: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int | None:
    if raw is None:
        return default
    if not isinstance(raw, str) or not _INT_RE.fullmatch(raw.strip()):
        check.add(field, "Must be an integer.")
        return None
    value = int(raw.strip())
    if value < minimum or value > maximum:
        check.add(field, f"Must be between {minimum} and {maximum}.")
        return None
    return value


def _optional_choice(check: _Check, raw: str | None, field: str, choices: set[str]) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or raw.strip().lower() not in choices:
        allowed = ", ".join(sorted(choices))
        check.add(field, f"Must be one of: {allowed}.")
        return None
    return raw.strip().lower()


def _optional_uuid(check: _Check, raw: str | None, field: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not _UUID_RE.fullmatch(raw.strip()):
        check.add(field, "Must be a UUID.")
        return None
    return raw.strip().lower()


def _required_uuid(check: _Check, raw: object, field: str) -> str | None:
    if not isinstance(raw, str) or not _UUID_RE.fullmatch(raw.strip()):
        check.add(field, "Must be a UUID.")
        return None
    return raw.strip().lower()


def _required_choice(check: _Check, raw: object, field: str, choices: set[str]) -> str | None:
    if not isinstance(raw, str) or raw.strip().lower() not in choices:
        allowed = ", ".join(sorted(choices))
        check.add(field, f"Must be one of: {allowed}.")
        return None
    return raw.strip().lower()
