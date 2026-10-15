"""Tenant-filtered Postgres/pgvector repository and durable ingestion state machine."""
import logging
import math
import time
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from auth import owner_id
from config import Settings
from errors import MissingDocument, ServiceError
from object_store import ObjectStore
from redis_services import RetrievalCache
from schemas import Chunk, DocumentMetadata, DocumentRecord, PageText
from storage import ChromaIndex

logger = logging.getLogger(__name__)


def vector_literal(values: list[float]) -> str:
    if len(values) != 384 or not all(math.isfinite(v) for v in values):
        raise ValueError("Invalid embedding")
    return "[" + ",".join(str(float(v)) for v in values) + "]"


class PostgresStore:
    def __init__(self, settings: Settings, objects: ObjectStore, cache: RetrievalCache,
                 embedder: Any = None, connect: Callable[..., Any] = psycopg.connect):
        self.settings, self.objects, self.cache, self.connect = settings, objects, cache, connect
        # Reuse only the local embedding adapter; no Chroma client or files are opened.
        self.index = embedder or ChromaIndex(settings.model_cache_dir)

    def connection(self) -> Any:
        return self.connect(self.settings.database_url, row_factory=dict_row, connect_timeout=5,
                            options="-c statement_timeout=15000 -c lock_timeout=5000")

    def reserve(self, filename: str) -> dict[str, Any]:
        owner, identifier, now = owner_id(), str(uuid4()), time.time()
        with self.connection() as conn:
            # Serialize capacity checks per tenant across API replicas.
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (owner,))
            count = conn.execute("SELECT count(*) AS n FROM documents WHERE owner_id=%s AND expires_at>%s AND status<>'deleting'", (owner, now)).fetchone()["n"]
            if count >= self.settings.max_documents:
                raise ServiceError(429, "Document capacity reached. Delete an earlier upload.")
            conn.execute("INSERT INTO documents(id,owner_id,filename,status,object_key,created_at,expires_at) VALUES(%s,%s,%s,'uploading',%s,%s,%s)",
                         (identifier, owner, filename, self.objects.key(owner, identifier), now, now + self.settings.document_ttl_seconds))
        return {"doc_id": identifier, "status": "uploading"}

    def stage(self, doc_id: str, content: bytes) -> None:
        owner = owner_id()
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id=%s AND owner_id=%s AND status='uploading' AND expires_at>%s FOR UPDATE", (doc_id, owner, time.time())).fetchone()
            if not row:
                raise MissingDocument()
            # The row lock prevents a concurrent delete from racing the object write.
            self.objects.put(row["object_key"], content)
            conn.execute("UPDATE documents SET status='queued' WHERE id=%s AND owner_id=%s", (doc_id, owner))

    def status(self, doc_id: str) -> dict[str, Any]:
        owner, now = owner_id(), time.time()
        with self.connection() as conn:
            conn.execute("UPDATE documents SET status='failed',error_code='ingestion_timeout' WHERE id=%s AND owner_id=%s AND status IN ('uploading','queued','processing') AND created_at<%s", (doc_id, owner, now - self.settings.ingestion_timeout_seconds))
            row = conn.execute("SELECT status,record,error_code FROM documents WHERE id=%s AND owner_id=%s AND expires_at>%s AND status<>'deleting'", (doc_id, owner, now)).fetchone()
        if not row:
            raise MissingDocument()
        result: dict[str, Any] = {"doc_id": doc_id, "status": row["status"]}
        if row["status"] == "ready":
            result["document"] = DocumentRecord.model_validate(row["record"]).metadata.model_dump(mode="json")
        if row["status"] == "failed":
            result["detail"] = "Document processing failed or timed out. Delete this upload and try again."
        return result

    def claim(self, doc_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("UPDATE documents SET status='processing' WHERE id=%s AND owner_id=%s AND status='queued' AND expires_at>%s RETURNING *", (doc_id, owner_id(), time.time())).fetchone()
            return dict(row) if row is not None else None

    def finish(self, doc_id: str, filename: str, pages: list[PageText], chunks: list[Chunk]) -> None:
        vectors = self.index.embed([c.text for c in chunks])
        if len(vectors) != len(chunks):
            raise ValueError("Embedding count mismatch")
        owner = owner_id()
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id=%s AND owner_id=%s AND status='processing' AND expires_at>%s FOR UPDATE", (doc_id, owner, time.time())).fetchone()
            if not row:
                raise MissingDocument()  # A deletion/expiry wins over a worker's late completion.
            metadata = DocumentMetadata(doc_id=UUID(doc_id), filename=filename, chars=sum(len(p.text) for p in pages),
                num_chunks=len(chunks), created_at=row["created_at"], expires_at=row["expires_at"],
                has_pdf=filename.lower().endswith(".pdf"), ocr_pages=sum(p.ocr for p in pages),
                chunking_strategy=self.settings.chunking_strategy)
            record = DocumentRecord(metadata=metadata, pages=pages, chunks=chunks)
            with conn.cursor() as cursor:
                cursor.executemany("INSERT INTO chunks(document_id,owner_id,chunk_id,embedding) VALUES(%s,%s,%s,%s::vector)",
                                   [(doc_id, owner, c.id, vector_literal(v)) for c, v in zip(chunks, vectors, strict=True)])
            conn.execute("UPDATE documents SET status='ready',record=%s WHERE id=%s AND owner_id=%s", (Jsonb(record.model_dump(mode="json")), doc_id, owner))

    def fail(self, doc_id: str) -> None:
        with self.connection() as conn:
            conn.execute("UPDATE documents SET status='failed',error_code='ingestion_failed' WHERE id=%s AND owner_id=%s AND status IN ('uploading','queued','processing')", (doc_id, owner_id()))

    def get(self, doc_id: str) -> DocumentRecord:
        with self.connection() as conn:
            row = conn.execute("SELECT record FROM documents WHERE id=%s AND owner_id=%s AND status='ready' AND expires_at>%s", (doc_id, owner_id(), time.time())).fetchone()
        if not row:
            raise MissingDocument()
        return DocumentRecord.model_validate(row["record"])

    def search(self, doc_id: str, question: str, k: int = 4) -> list[tuple[Chunk, float]]:
        record = self.get(doc_id)  # Authorize and check TTL even on a cache hit.
        owner = owner_id()
        key = self.cache.key(owner, doc_id, question, k)
        hits = self.cache.get(key)
        by_id = {c.id: c for c in record.chunks}
        if not isinstance(hits, list) or any(not isinstance(h, list) or len(h) != 2 or not isinstance(h[0], str) or h[0] not in by_id
                or not isinstance(h[1], (float, int)) or not math.isfinite(h[1]) for h in hits):
            query = vector_literal(self.index.embed([question])[0])
            with self.connection() as conn:
                rows = conn.execute("SELECT chunk_id, embedding <=> %s::vector AS distance FROM chunks WHERE document_id=%s AND owner_id=%s ORDER BY distance,chunk_id LIMIT %s", (query, doc_id, owner, k)).fetchall()
            hits = [(r["chunk_id"], float(r["distance"])) for r in rows]
            ttl = min(self.settings.cache_ttl_seconds, int(record.metadata.expires_at - time.time()))
            if ttl > 0:
                self.cache.put(key, hits, ttl)
        self.get(doc_id)
        return [(by_id[key], float(distance)) for key, distance in hits]

    def pdf(self, doc_id: str) -> bytes:
        record = self.get(doc_id)
        if not record.metadata.has_pdf:
            raise MissingDocument()
        content = self.objects.get(self.objects.key(owner_id(), doc_id))
        self.get(doc_id)
        return content

    def download(self, doc_id: str) -> dict[str, Any]:
        record = self.get(doc_id)
        if not record.metadata.has_pdf:
            raise MissingDocument()
        ttl = min(self.settings.signed_url_seconds, int(record.metadata.expires_at - time.time()))
        if ttl < 1:
            raise MissingDocument()
        return {"url": self.objects.signed_url(self.objects.key(owner_id(), doc_id), ttl), "expires_at": time.time() + ttl}

    def delete(self, doc_id: str) -> None:
        self._delete(doc_id, owner_id())

    def _delete(self, doc_id: str, owner: str, *, expired_only: bool = False) -> None:
        with self.connection() as conn:
            row = conn.execute("UPDATE documents SET status='deleting',record=NULL WHERE id=%s AND owner_id=%s AND (%s=false OR expires_at<=%s OR status='deleting') RETURNING object_key", (doc_id, owner, expired_only, time.time())).fetchone()
            if not row:
                if expired_only:
                    return
                raise MissingDocument()
            conn.execute("DELETE FROM chunks WHERE document_id=%s AND owner_id=%s", (doc_id, owner))
        try:
            self.objects.delete(row["object_key"])
        except Exception as exc:
            raise ServiceError(503, "Deletion is pending cleanup. Please retry shortly.") from exc
        with self.connection() as conn:
            conn.execute("DELETE FROM documents WHERE id=%s AND owner_id=%s AND status='deleting'", (doc_id, owner))

    def cleanup(self) -> int:
        # Internal maintenance only; never an HTTP endpoint. Does not return content.
        with self.connection() as conn:
            rows = conn.execute("SELECT id,owner_id FROM documents WHERE expires_at<=%s OR status='deleting' LIMIT 100", (time.time(),)).fetchall()
        count = 0
        for row in rows:
            try:
                self._delete(str(row["id"]), str(row["owner_id"]), expired_only=True)
                count += 1
            except ServiceError:
                logger.error("object_cleanup_pending")
        return count

    def create(self, filename: str, chars: int, chunks: list[Chunk], *, pages: list[PageText] | None = None,
               pdf: bytes | None = None) -> DocumentMetadata:
        raise ServiceError(409, "Production uploads must use background ingestion.")
