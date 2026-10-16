"""Synthetic worker smoke; pipe into Python inside the private local Compose API."""
import time
from uuid import uuid4

from audit_schemas import AuditResponse
from auth import current_owner
from config import Settings
from errors import MissingDocument
from ingestion import Ingestion, production_store
from product_store import ProductStore
from reports import render_report

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
            products = ProductStore(store)
            audit = AuditResponse(doc_id=doc, contract_type="lease", checklist=["rent"],
                clauses=[], overall_risk=None, summary="Synthetic infrastructure smoke only.",
                dropped_claims=0, analyzed_chunks=1, total_chunks=1, rule_checks=[],
                warnings=["Not a model-quality evaluation."], steps=["synthetic fixture"])
            saved = products.save(audit)
            assert render_report(saved).startswith(b"%PDF-")
            link = products.share(doc, 60)
            assert products.read_share(link.token).audit.doc_id == saved.audit.doc_id
            products.revoke(doc)
            try:
                products.read_share(link.token)
            except MissingDocument:
                pass
            else:
                raise AssertionError("Revoked audit remained accessible")
            print("PASS: Linux PDF render, migrated audit snapshots, sharing and revocation")
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
