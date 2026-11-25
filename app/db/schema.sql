PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    format TEXT NOT NULL CHECK (format IN ('pdf', 'docx')),
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
    sha256 TEXT NOT NULL,
    storage_name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('source', 'output')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversions (
    id TEXT PRIMARY KEY,
    source_document_id TEXT NOT NULL,
    output_document_id TEXT,
    source_format TEXT NOT NULL CHECK (source_format IN ('pdf', 'docx')),
    target_format TEXT NOT NULL CHECK (target_format IN ('pdf', 'docx')),
    status TEXT NOT NULL CHECK (status IN ('processing', 'completed', 'failed')),
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (source_document_id) REFERENCES documents (id),
    FOREIGN KEY (output_document_id) REFERENCES documents (id),
    CHECK (
        (
            status = 'completed'
            AND output_document_id IS NOT NULL
            AND error_code IS NULL
            AND finished_at IS NOT NULL
        )
        OR (
            status = 'failed'
            AND output_document_id IS NULL
            AND error_code IS NOT NULL
            AND finished_at IS NOT NULL
        )
        OR (
            status = 'processing'
            AND output_document_id IS NULL
            AND error_code IS NULL
            AND finished_at IS NULL
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents (created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_conversions_created_at ON conversions (created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_conversions_source ON conversions (source_document_id);
CREATE INDEX IF NOT EXISTS idx_conversions_output ON conversions (output_document_id);
CREATE INDEX IF NOT EXISTS idx_conversions_status ON conversions (status);
