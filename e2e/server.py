"""Loopback-only browser fixture. Real SQL/S3/Redis/RQ; synthetic JWTs and AI.

Never deploy this module. Test credentials are generated per process and cannot
authenticate against a real Supabase project.
"""
import json
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "contractiq-backend"), str(ROOT / "contractiq-backend/tests")]

import ingestion
import jwt
import uvicorn
from auth import SupabaseVerifier
from config import Settings
from cryptography.hazmat.primitives.asymmetric import ec
from ingestion import Ingestion
from main import create_app
from privacy import RedactionVault
from rag_pipeline import RAGService
from rq import SimpleWorker
from rq.serializers import JSONSerializer
from rq.timeouts import TimerDeathPenalty
from schemas import AnswerResult
from test_infrastructure import infra


class FixtureProvider:
    def generate(self, schema, prompt, *, deadline, validate=None):
        if schema.__name__ in {"ContractClassification", "ClauseBatch", "WorkspaceResult"}:
            evidence = json.loads(prompt.split('<untrusted_contract_data>\n', 1)[1].split('\n</untrusted_contract_data>', 1)[0])
            if schema.__name__ == "ContractClassification":
                payload = {"contract_type": "lease", "evidence": evidence[0]["text"][:100], "chunk_id": evidence[0]["id"]}
            elif schema.__name__ == "ClauseBatch":
                payload = {"clauses": [{"type": "Uncapped Liability", "quoted_text": item["text"], "chunk_id": item["id"], "party": "Tenant", "confidence": 0.8} for item in evidence if "unlimited" in item["text"].lower()]}
            else:
                seen = {}
                for item in evidence["excerpts"]:
                    seen.setdefault(item["document"], item["excerpt"])
                payload = {"answer": " ".join(f"{label} contains relevant terms. [Excerpt {number}]" for label, number in seen.items()), "excerpt_ids": list(seen.values())}
            value = schema.model_validate(payload)
        else:
            value = schema.model_validate({"answer": "Monthly rent is INR 24000. [Excerpt 1]", "excerpt_ids": [1]})
        if validate:
            validate(value)
        return value

    def stream_json(self, schema, prompt, *, deadline, cancelled):
        yield self.generate(AnswerResult, prompt, deadline=deadline).model_dump_json()


class ThreadWorker(SimpleWorker):
    death_penalty_class = TimerDeathPenalty

    def _install_signal_handlers(self):
        pass  # The test server owns shutdown, rather than a worker thread.


def serve(resources):
    settings, store, redis, queue = next(resources)
    settings = settings.model_copy(update={"cors_origins": ["http://127.0.0.1:3013"], "rate_limit_requests": 10000})
    store.settings = settings
    key = ec.generate_private_key(ec.SECP256R1())
    public = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()))
    public.update(kid="e2e", alg="ES256", use="sig")
    verifier = SupabaseVerifier(settings)
    verifier.keys.fetch_data = lambda: {"keys": [public]}
    sessions = {}
    for name in ("alice", "bob"):
        owner, now = str(uuid4()), int(time.time())
        claims = {"sub": owner, "aud": "authenticated", "role": "authenticated", "iat": now,
                  "exp": now + 3600, "iss": verifier.issuer}
        sessions[name] = {"access_token": jwt.encode(claims, key, algorithm="ES256", headers={"kid": "e2e"}),
                          "token_type": "bearer", "refresh_token": "test-only", "expires_in": 3600,
                          "expires_at": now + 3600, "user": {"id": owner, "aud": "authenticated",
                          "role": "authenticated", "email": f"{name}@example.test", "app_metadata": {},
                          "user_metadata": {}, "created_at": "2026-01-01T00:00:00Z"}}
    target = ROOT / "test-results/e2e-auth.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(sessions), encoding="utf-8")
    # RQ imports the actual ingestion function, whose dependencies are isolated here.
    ingestion.production_store = lambda _: store
    Settings.from_env = classmethod(lambda cls: settings)
    stop = threading.Event()

    def consume():
        while not stop.is_set():
            worker = ThreadWorker([queue], connection=redis, serializer=JSONSerializer)
            worker.work(burst=True, logging_level="WARNING")
            stop.wait(0.25)

    app = create_app(settings, RAGService(settings, store, FixtureProvider()),
                     verifier=verifier, ingestion=Ingestion(settings, store, queue))
    # Load the real local redactor before readiness, keeping cold imports outside
    # browser assertion timeouts on resource-constrained Windows hosts.
    RedactionVault(settings).redact("Synthetic fixture readiness")
    thread = threading.Thread(target=consume, daemon=True)
    thread.start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=8013, access_log=False)
    finally:
        stop.set()
        thread.join(timeout=30)


if __name__ == "__main__":
    resources = infra.__wrapped__()
    try:
        serve(resources)
    finally:
        resources.close()
