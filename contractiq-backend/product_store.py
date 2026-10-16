"""Server-owned audit snapshots; public capabilities expose only an immutable audit."""
import secrets
import time
from hashlib import sha256

from psycopg.types.json import Jsonb

from audit_schemas import AuditResponse
from auth import owner_id
from errors import MissingDocument, ServiceError
from postgres_store import PostgresStore
from product_schemas import SavedAudit, ShareCreated
from schemas import DocumentMetadata
from storage import DocumentStore


class ProductStore:
    def __init__(self, store: DocumentStore | PostgresStore):
        self.store = store

    def documents(self) -> list[DocumentMetadata]:
        if isinstance(self.store, PostgresStore):
            with self.store.connection() as conn:
                rows = conn.execute("SELECT record->'metadata' AS metadata FROM documents WHERE owner_id=%s AND status='ready' AND expires_at>%s ORDER BY created_at DESC LIMIT 1000", (owner_id(), time.time())).fetchall()
            return [DocumentMetadata.model_validate(row["metadata"]) for row in rows]
        with self.store.lock:
            result = []
            for path in self.store.root.iterdir():
                if not path.is_dir() or path.is_symlink():
                    continue
                try:
                    result.append(self.store.get(path.name).metadata)
                except MissingDocument:
                    continue
            return sorted(result, key=lambda item: item.created_at, reverse=True)[:1000]

    def save(self, audit: AuditResponse) -> SavedAudit:
        doc_id = str(audit.doc_id)
        record = self.store.get(doc_id)
        saved = SavedAudit(audit=audit, filename=record.metadata.filename,
                           generated_at=time.time(), expires_at=record.metadata.expires_at)
        if isinstance(self.store, PostgresStore):
            with self.store.connection() as conn:
                row = conn.execute("UPDATE documents SET audit_snapshot=%s WHERE id=%s AND owner_id=%s AND status='ready' AND expires_at>%s RETURNING id", (Jsonb(saved.model_dump(mode="json")), doc_id, owner_id(), time.time())).fetchone()
                if not row:
                    raise MissingDocument()
        else:
            with self.store.lock:
                self.store.get(doc_id)
                path = self.store.directory(doc_id) / "audit.json"
                temp = path.with_suffix(".tmp")
                temp.write_text(saved.model_dump_json(), encoding="utf-8")
                temp.replace(path)
        return saved

    def get(self, doc_id: str) -> SavedAudit:
        self.store.get(doc_id)
        if isinstance(self.store, PostgresStore):
            with self.store.connection() as conn:
                row = conn.execute("SELECT audit_snapshot FROM documents WHERE id=%s AND owner_id=%s AND status='ready' AND expires_at>%s", (doc_id, owner_id(), time.time())).fetchone()
            if not row:
                raise MissingDocument()
            if row["audit_snapshot"] is None:
                raise ServiceError(409, "Run an audit before exporting or sharing it.")
            return SavedAudit.model_validate(row["audit_snapshot"])
        with self.store.lock:
            self.store.get(doc_id)
            path = self.store.directory(doc_id) / "audit.json"
            if not path.exists():
                raise ServiceError(409, "Run an audit before exporting it.")
            return SavedAudit.model_validate_json(path.read_text(encoding="utf-8"))

    def share(self, doc_id: str, ttl: int) -> ShareCreated:
        if not isinstance(self.store, PostgresStore):
            raise ServiceError(409, "Sharing requires an authenticated production workspace.")
        # Lock the document against concurrent deletion and cap active shares per document.
        with self.store.connection() as conn:
            now = time.time()
            row = conn.execute("SELECT audit_snapshot,expires_at FROM documents WHERE id=%s AND owner_id=%s AND status='ready' AND expires_at>%s FOR UPDATE", (doc_id, owner_id(), now)).fetchone()
            if not row:
                raise MissingDocument()
            if row["audit_snapshot"] is None:
                raise ServiceError(409, "Run an audit before sharing it.")
            conn.execute("DELETE FROM audit_shares WHERE document_id=%s AND owner_id=%s AND expires_at<=%s", (doc_id, owner_id(), now))
            count = conn.execute("SELECT count(*) AS n FROM audit_shares WHERE document_id=%s AND owner_id=%s", (doc_id, owner_id())).fetchone()["n"]
            if count >= 10:
                raise ServiceError(429, "Revoke existing links before creating more.")
            token = secrets.token_urlsafe(32)
            expiry = min(now + ttl, row["expires_at"])
            snapshot = SavedAudit.model_validate(row["audit_snapshot"]).model_copy(update={"expires_at": expiry})
            conn.execute("INSERT INTO audit_shares(token_hash,document_id,owner_id,expires_at,snapshot) VALUES(%s,%s,%s,%s,%s)", (sha256(token.encode()).hexdigest(), doc_id, owner_id(), expiry, Jsonb(snapshot.model_dump(mode="json"))))
        return ShareCreated(token=token, expires_at=expiry)

    def revoke(self, doc_id: str) -> None:
        self.store.get(doc_id)
        if not isinstance(self.store, PostgresStore):
            raise ServiceError(409, "Sharing requires an authenticated production workspace.")
        with self.store.connection() as conn:
            # Same lock order as share creation provides a clear revocation boundary.
            conn.execute("SELECT id FROM documents WHERE id=%s AND owner_id=%s FOR UPDATE", (doc_id, owner_id()))
            conn.execute("DELETE FROM audit_shares WHERE document_id=%s AND owner_id=%s", (doc_id, owner_id()))

    def read_share(self, token: str) -> SavedAudit:
        if not isinstance(self.store, PostgresStore):
            raise MissingDocument()
        # Capability-only query, deliberately independent of current_owner. Never return source files.
        with self.store.connection() as conn:
            now = time.time()
            row = conn.execute("SELECT s.snapshot FROM audit_shares s JOIN documents d ON d.id=s.document_id AND d.owner_id=s.owner_id WHERE s.token_hash=%s AND s.expires_at>%s AND d.expires_at>%s AND d.status='ready'", (sha256(token.encode()).hexdigest(), now, now)).fetchone()
        if not row:
            raise MissingDocument()
        return SavedAudit.model_validate(row["snapshot"])
