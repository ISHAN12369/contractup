"""Synthetic worker smoke; pipe into Python inside the private local Compose API."""
import time
from uuid import uuid4

from auth import current_owner
from config import Settings
from ingestion import Ingestion, production_store

settings = Settings.from_env()
store = production_store(settings)
token = current_owner.set(str(uuid4()))
doc = None
try:
    ticket = Ingestion(settings, store).submit(
        "synthetic-smoke.txt",
        b"1. Rent\nThe tenant must pay monthly rent of INR 24000.\n"
        b"2. Termination\nEither party gives 45 days written notice.",
    )
    doc = ticket["doc_id"]
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        status = store.status(doc)
        if status["status"] == "ready":
            assert store.search(doc, "What is the rent?")
            print("PASS: Linux RQ worker, parsing, real embeddings, Postgres retrieval, S3 storage")
            break
        if status["status"] == "failed":
            raise RuntimeError("Synthetic ingestion failed")
        time.sleep(1)
    else:
        raise RuntimeError("Synthetic ingestion timed out")
finally:
    if doc:
        store.delete(doc)
        print("PASS: synthetic document cleanup")
    current_owner.reset(token)
