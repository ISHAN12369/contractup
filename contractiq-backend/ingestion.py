"""RQ only carries identifiers; raw documents remain in private object storage."""
from typing import Any

from redis import Redis
from rq import Queue
from rq.serializers import JSONSerializer

from auth import current_owner, owner_id
from chunking import split_pages
from config import Settings
from errors import ServiceError
from object_store import ObjectStore
from parsing import extract_document
from postgres_store import PostgresStore
from redis_services import RetrievalCache
from telemetry import configure_telemetry, flush_telemetry


def redis_client(settings: Settings) -> Redis:
    return Redis.from_url(settings.redis_url, socket_connect_timeout=5, socket_timeout=5)


def production_store(settings: Settings) -> PostgresStore:
    return PostgresStore(settings, ObjectStore(settings), RetrievalCache(redis_client(settings)))


class Ingestion:
    def __init__(self, settings: Settings, store: PostgresStore, queue: Any = None):
        self.settings, self.store = settings, store
        self.queue = queue if queue is not None else Queue("ingestion", connection=redis_client(settings), serializer=JSONSerializer)

    def submit(self, filename: str, content: bytes) -> dict[str, Any]:
        ticket = self.store.reserve(filename)
        identifier = ticket["doc_id"]
        try:
            self.store.stage(identifier, content)
            self.queue.enqueue("ingestion.process_document", owner_id(), identifier, job_id=identifier,
                               job_timeout=self.settings.ingestion_timeout_seconds,
                               ttl=self.settings.ingestion_timeout_seconds, result_ttl=0, failure_ttl=600)
        except Exception as exc:
            self.store.fail(identifier)
            raise ServiceError(503, "Upload could not be queued. Please retry later.") from exc
        return {"doc_id": identifier, "status": "queued"}


def process_document(owner: str, doc_id: str) -> None:
    settings = Settings.from_env()
    configure_telemetry(settings)
    store = production_store(settings)
    try:
        process_with_store(owner, doc_id, store, settings)
    finally:
        flush_telemetry()


def process_with_store(owner: str, doc_id: str, store: PostgresStore, settings: Settings) -> None:
    token = current_owner.set(owner)
    try:
        row = store.claim(doc_id)
        if row is None:
            return  # Duplicate delivery or already deleted/expired.
        try:
            content = store.objects.get(row["object_key"])
            pages = extract_document(row["filename"], content, settings)
            store.finish(doc_id, row["filename"], pages, split_pages(pages, settings))
        except Exception:
            store.fail(doc_id)  # No parser exceptions/text are saved to Redis failure traces.
    finally:
        current_owner.reset(token)
