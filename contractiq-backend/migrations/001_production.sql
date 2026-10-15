CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS documents (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL,
    filename text NOT NULL,
    status text NOT NULL CHECK (status IN ('uploading','queued','processing','ready','failed','deleting')),
    object_key text NOT NULL,
    created_at double precision NOT NULL,
    expires_at double precision NOT NULL,
    record jsonb,
    error_code text,
    UNIQUE (id, owner_id)
);
CREATE INDEX IF NOT EXISTS documents_owner_expiry ON documents(owner_id, expires_at);
CREATE INDEX IF NOT EXISTS documents_expiry ON documents(expires_at);
CREATE TABLE IF NOT EXISTS chunks (
    document_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    chunk_id text NOT NULL,
    embedding vector(384) NOT NULL,
    PRIMARY KEY (document_id, owner_id, chunk_id),
    FOREIGN KEY (document_id, owner_id) REFERENCES documents(id, owner_id) ON DELETE CASCADE
);
-- Exact cosine search inside the small tenant/document-filtered set avoids approximate
-- index post-filter recall loss. MAX_CHUNKS bounds each search; benchmark before HNSW.
