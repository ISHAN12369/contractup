# ADR 0008: Compose development stack and layered validation

Status: accepted for Phase 3, 12 October 2026.

Compose provides Postgres/pgvector, Redis, a localhost S3 emulator, migration/bootstrap, API, ingestion worker and Next.js. Supabase remains a hosted external identity service; supply a project URL/publishable key and enable email/password sign-in. Building a full local Supabase stack would add substantial resource demand. Frontend public variables are build-time settings, so changing them requires a rebuild.

The local emulator is Moto, pinned to 5.2.3. It is ephemeral and does not establish private-bucket authorization or signed-URL expiry semantics. Do not expose it publicly or place sensitive documents in it. Restarting only the emulator loses originals while Postgres metadata may remain; use disposable sample documents and rerun bootstrap after restart. Deployment must substitute a real private S3/R2 bucket. Local database/Redis ports bind loopback and avoid the user's pre-existing database on port 5433.

Unit tests cover cryptographic JWT validation, provider failures, prompt delimiters and telemetry scrubbing. Opt-in infrastructure tests create randomly named schemas/buckets/queues on local services and check tenant boundaries, lifecycle races, expiry, cache and deletion failure. Playwright runs real SQL/S3/RQ ingestion with synthetic identity/AI to check browser integration without paid calls. Locust supplies a bounded authenticated synthetic workload. None of those imply legal accuracy, production throughput or live vendor integration. A full-feature API plus worker plus database/Redis is not a 512 MiB deployment; use managed data services and tune model features, then measure.

Reference: [Moto server mode](https://docs.getmoto.org/en/latest/docs/server_mode.html).
