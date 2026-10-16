ALTER TABLE documents ADD COLUMN IF NOT EXISTS audit_snapshot jsonb;
CREATE TABLE IF NOT EXISTS audit_shares (
    token_hash text PRIMARY KEY,
    document_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    expires_at double precision NOT NULL,
    snapshot jsonb NOT NULL,
    FOREIGN KEY (document_id, owner_id) REFERENCES documents(id, owner_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS audit_shares_document ON audit_shares(document_id, owner_id);
CREATE INDEX IF NOT EXISTS audit_shares_expiry ON audit_shares(expires_at);
