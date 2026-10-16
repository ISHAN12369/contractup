"""Real Postgres/Redis + HTTP S3-emulator tests, opt-in to avoid external side effects."""
import os
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from rq import Queue
from rq.serializers import JSONSerializer

from auth import current_owner
from chunking import split_pages
from config import Settings
from errors import MissingDocument, ServiceError
from ingestion import Ingestion, process_with_store, redis_client
from main import create_app
from object_store import ObjectStore
from postgres_store import PostgresStore
from rag_pipeline import RAGService
from redis_services import RedisLimiter, RetrievalCache
from schemas import PageText

pytestmark = pytest.mark.skipif(os.getenv("RUN_INFRA_TESTS") != "1", reason="Set RUN_INFRA_TESTS=1 with the local Compose infrastructure running")
TEXT = b"1. Rent\nThe tenant pays monthly rent of INR 24000 on the fifth day of each month.\n2. Exit\nEither party gives 45 days of written notice."


@contextmanager
def as_owner(owner):
    token = current_owner.set(owner)
    try:
        yield
    finally:
        current_owner.reset(token)


class Embeddings:
    def embed(self, texts):
        return [[1.0] + [0.0] * 383 for _ in texts]


@pytest.fixture
def infra():
    schema = "ciq_test_" + uuid4().hex
    bucket = "ciq-test-" + uuid4().hex
    settings = Settings(app_mode="production", database_url=os.getenv("TEST_DATABASE_URL", "postgresql://contractiq:contractiq-local-only@127.0.0.1:15432/contractiq"),
        redis_url=os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6380/0"), supabase_url="https://test.supabase.co",
        s3_endpoint=os.getenv("TEST_S3_ENDPOINT", "http://127.0.0.1:9000"), s3_access_key="contractiq-local",
        s3_secret_key="contractiq-local-password", s3_bucket=bucket, rate_limit_requests=1000,
        retriever_strategy="dense", pii_mode="patterns", ocr_enabled=False)
    with psycopg.connect(settings.database_url) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    def connect(*args, **kwargs):
        kwargs["options"] = kwargs.get("options", "") + f" -c search_path={schema},public"
        return psycopg.connect(*args, **kwargs)
    objects = ObjectStore(settings)
    objects.client.create_bucket(Bucket=bucket)
    redis = redis_client(settings)
    store = PostgresStore(settings, objects, RetrievalCache(redis), embedder=Embeddings(), connect=connect)
    with store.connection() as conn:
        for migration in sorted((Path(__file__).parents[1] / "migrations").glob("*.sql")):
            conn.execute(migration.read_text())
    queue = Queue("ciq-test-" + uuid4().hex, connection=redis, serializer=JSONSerializer)
    try:
        yield settings, store, redis, queue
    finally:
        # These randomly named resources were created exclusively by this fixture.
        for job in queue.get_jobs():
            job.delete()
        queue.delete()
        for item in objects.client.list_objects_v2(Bucket=bucket).get("Contents", []):
            objects.delete(item["Key"])
        objects.client.delete_bucket(Bucket=bucket)
        with psycopg.connect(settings.database_url) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        redis.close()


def test_real_storage_queue_cache_and_cross_tenant_lifecycle(infra):
    settings, store, redis, queue = infra
    alice, bob = str(uuid4()), str(uuid4())
    with as_owner(alice):
        ticket = Ingestion(settings, store, queue).submit("lease.txt", TEXT)
        identifier = ticket["doc_id"]
        assert store.status(identifier)["status"] == "queued"
        assert list(queue.get_jobs()[0].args) == [alice, identifier]
    with as_owner(bob):
        for operation in (store.get, store.status, store.pdf, store.download, store.delete):
            with pytest.raises(MissingDocument):
                operation(identifier)
        with pytest.raises(MissingDocument):
            store.search(identifier, "rent")
    process_with_store(alice, identifier, store, settings)
    with as_owner(alice):
        assert store.status(identifier)["status"] == "ready"
        first = store.search(identifier, "rent")
        assert first and first == store.search(identifier, "rent")
        assert redis.get(RetrievalCache.key(alice, identifier, "rent", 4))
        store.delete(identifier)
        # An extant cache entry cannot restore a deleted document.
        with pytest.raises(MissingDocument):
            store.search(identifier, "rent")


def test_late_worker_cannot_resurrect_deleted_document_and_expiry_is_enforced(infra):
    settings, store, _, queue = infra
    owner = str(uuid4())
    with as_owner(owner):
        doc = Ingestion(settings, store, queue).submit("lease.txt", TEXT)["doc_id"]
        assert store.claim(doc)
        store.delete(doc)
        with pytest.raises(MissingDocument):
            store.finish(doc, "lease.txt", [], [])
        doc = Ingestion(settings, store, queue).submit("lease.txt", TEXT)["doc_id"]
        process_with_store(owner, doc, store, settings)
        with store.connection() as conn:
            conn.execute("UPDATE documents SET expires_at=%s WHERE id=%s", (time.time()-1, doc))
        with pytest.raises(MissingDocument):
            store.get(doc)
        assert store.cleanup() == 1


def test_failed_physical_delete_remains_inaccessible_until_cleanup(infra, monkeypatch):
    settings, store, _, queue = infra
    owner = str(uuid4())
    with as_owner(owner):
        doc = Ingestion(settings, store, queue).submit("lease.txt", TEXT)["doc_id"]
        process_with_store(owner, doc, store, settings)
        original = store.objects.delete
        def fail(key):
            raise OSError("controlled outage")
        monkeypatch.setattr(store.objects, "delete", fail)
        with pytest.raises(ServiceError) as error:
            store.delete(doc)
        assert error.value.status == 503
        with pytest.raises(MissingDocument):
            store.get(doc)
        monkeypatch.setattr(store.objects, "delete", original)
        assert store.cleanup() == 1


def test_redis_limit_is_shared_between_instances(infra):
    _, _, redis, _ = infra
    key = "test:" + str(uuid4())
    first, second = RedisLimiter(redis, 2, 60), RedisLimiter(redis, 2, 60)
    assert first.allow(key) and second.allow(key)
    assert not first.allow(key)


def test_pdf_signed_download_is_owner_checked_and_lifetime_bounded(infra):
    settings, store, _, _ = infra
    owner = str(uuid4())
    with as_owner(owner):
        doc = store.reserve("sample.pdf")["doc_id"]
        original = b"%PDF-1.4 synthetic storage fixture"
        store.stage(doc, original)
        assert store.claim(doc)
        pages = [PageText(page=1, text=TEXT.decode())]
        store.finish(doc, "sample.pdf", pages, split_pages(pages, settings))
        assert store.pdf(doc) == original
        url = store.download(doc)["url"]
        assert int(parse_qs(urlsplit(url).query)["X-Amz-Expires"][0]) <= settings.signed_url_seconds
        import httpx
        assert httpx.get(url, timeout=10).content == original
    with as_owner(str(uuid4())):
        with pytest.raises(MissingDocument):
            store.download(doc)


def test_authenticated_api_does_not_expose_other_users_documents(infra):
    settings, store, _, queue = infra
    alice, bob = str(uuid4()), str(uuid4())
    class Verifier:
        def verify(self, token):
            if token not in {alice, bob}:
                raise ServiceError(401, "Invalid session")
            return token
    class NoProvider:
        def generate(self, *args, **kwargs):
            raise AssertionError("Unauthorized requests must not reach the provider")
    service = RAGService(settings, store, NoProvider())
    app = create_app(settings, service, verifier=Verifier(), ingestion=Ingestion(settings, store, queue))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/upload", files={"file": ("lease.txt", TEXT)}).status_code == 401
        uploaded = client.post("/upload", headers={"Authorization": "Bearer " + alice}, files={"file": ("lease.txt", TEXT)})
        assert uploaded.status_code == 202
        doc = uploaded.json()["doc_id"]
        process_with_store(alice, doc, store, settings)
        assert client.get(f"/document/{doc}/source", headers={"Authorization": "Bearer " + alice}).status_code == 200
        headers = {"Authorization": "Bearer " + bob}
        for path in (f"/document/{doc}", f"/document/{doc}/source", f"/document/{doc}/file", f"/document/{doc}/download", f"/ingestion/{doc}"):
            assert client.get(path, headers=headers).status_code == 404
        for path, body in (("/chat", {"doc_id": doc, "question": "Rent?"}), ("/chat/stream", {"doc_id": doc, "question": "Rent?"}),
                           ("/benefits", {"doc_id": doc}), ("/audit", {"doc_id": doc}),
                           ("/compare", {"before_id": doc, "after_id": str(uuid4())})):
            assert client.post(path, headers=headers, json=body).status_code == 404
        assert client.delete(f"/document/{doc}", headers=headers).status_code == 404


def test_product_reports_shares_and_workspace_tenant_boundaries(infra):
    from test_product import sample_audit

    from product_store import ProductStore

    settings, store, _, queue = infra
    alice, bob = str(uuid4()), str(uuid4())
    products = ProductStore(store)
    with as_owner(alice):
        doc = Ingestion(settings, store, queue).submit("lease.txt", TEXT)["doc_id"]
        process_with_store(alice, doc, store, settings)
        products.save(sample_audit(doc))
        shared = products.share(doc, 86400)
        assert shared.expires_at <= store.get(doc).metadata.expires_at
        with store.connection() as conn:
            row = conn.execute("SELECT token_hash FROM audit_shares WHERE document_id=%s", (doc,)).fetchone()
            assert row["token_hash"] != shared.token and len(row["token_hash"]) == 64
        products.save(sample_audit(doc, summary="A later audit"))
        assert products.read_share(shared.token).audit.summary != "A later audit"
    with as_owner(bob):
        assert products.documents() == []
        for operation in (products.get, products.revoke):
            with pytest.raises(MissingDocument):
                operation(doc)
        with pytest.raises(MissingDocument):
            products.share(doc, 60)
    class Verifier:
        def verify(self, token):
            if token not in {alice, bob}:
                raise ServiceError(401, "Invalid session")
            return token
    class NoProvider:
        def generate(self, *args, **kwargs):
            raise AssertionError("Unauthorized documents must never reach the provider")
    app = create_app(settings, RAGService(settings, store, NoProvider()), verifier=Verifier(), ingestion=Ingestion(settings, store, queue))
    with TestClient(app) as client:
        response = client.post("/share/read", json={"token": shared.token})
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert "chunks" not in response.json() and "pages" not in response.json()
        assert client.get("/documents").status_code == 401
        headers = {"Authorization": "Bearer " + bob}
        for path in (f"/document/{doc}/report", f"/document/{doc}/audit"):
            assert client.get(path, headers=headers).status_code == 404
        assert client.post(f"/document/{doc}/shares", headers=headers, json={}).status_code == 404
        assert client.delete(f"/document/{doc}/shares", headers=headers).status_code == 404
        assert client.post("/workspace/chat", headers=headers, json={"doc_ids": [doc, str(uuid4())], "question": "Compare"}).status_code == 404
        assert client.post("/share/read", json={"token": "x" * 43}).status_code == 404
        with as_owner(alice):
            products.revoke(doc)
        assert client.post("/share/read", json={"token": shared.token}).status_code == 404
        with as_owner(alice):
            shared = products.share(doc, 60)
            with store.connection() as conn:
                conn.execute("UPDATE audit_shares SET expires_at=%s WHERE document_id=%s", (time.time() - 1, doc))
        assert client.post("/share/read", json={"token": shared.token}).status_code == 404
        with as_owner(alice):
            shared = products.share(doc, 60)
            store.delete(doc)
        assert client.post("/share/read", json={"token": shared.token}).status_code == 404
