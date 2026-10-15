# ADR 0005: RQ ingestion and shared Redis services

Status: accepted for Phase 3, 12 October 2026.

Upload returns HTTP 202 with a document ID after durable reservation, private object upload and RQ enqueue. Redis jobs contain owner/document identifiers, never document bytes. Workers claim only queued, unexpired rows. Polling exposes queued/processing/ready/failed; failures are durable sanitized states. JSON serialization avoids accepting arbitrary pickled job payloads. Redis remains trusted backend infrastructure: restrict network access and require authentication/TLS in deployment. Separate queues/caches or instances if operational contention warrants it; the local stack shares one instance with a bounded no-eviction policy.

Retries and duplicate delivery cannot resurrect deleted data: worker completion checks status under a row lock. Delete first tombstones the row and removes vectors, then removes the object and row. Object-store failures retain an inaccessible tombstone for cleanup. TTL is enforced on reads even when physical cleanup is delayed. A sweep removes at most 100 expired/tombstoned records per pass. Hard worker death is surfaced as a timeout by status polling; automatic job re-execution is not promised. A failed enqueue leaves a failed reservation until expiry, so repeated infrastructure failure may consume a tenant's bounded capacity temporarily.

Redis Lua INCR/EXPIRE makes the rate budget atomic across API replicas. Both an unauthenticated IP budget and authenticated user budget apply; Redis limiter failure returns 503. Retrieval caching fails open to fresh SQL, stores only chunk IDs/distances, hashes owner/document/query/config in keys, and caps TTL by document retention. Every cache read reauthorizes the document, so stale entries cannot restore deleted/foreign content. Inference admission remains one operation per API process to bound memory; distributed rate limiting is not a global inference-concurrency limiter.

RQ was chosen over Celery for the single ingestion queue and simple operational model. Linux workers use RQ's normal subprocess isolation/time limits. Browser tests use SimpleWorker with a thread timer on Windows, exercising real Redis JSON jobs; this is a test harness, not the deployment worker architecture.

Reference: [RQ documentation](https://python-rq.org/docs/).
