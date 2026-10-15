# Phase 3 verification

Verified locally on 12 and 15 October 2026. Results refer to software behavior with synthetic fixtures, not legal correctness or production capacity. All legal output remains informational only, not legal advice.

## Recorded checks

| Check | Outcome |
| --- | --- |
| Backend unit/API/infrastructure suite, final rerun on 15 October | 74 passed, 1 skipped in 40.45 seconds; exit 0 |
| Real infrastructure | Six tests passed against Postgres/pgvector, Redis and HTTP Moto S3 |
| Native OCR skip | Windows Tesseract executable absent; Linux CI installs it |
| Backend Ruff / strict mypy | Passed; 30 source files type checked |
| Phase 2 regression tests | 18 passed |
| Evaluation Ruff / strict mypy | Passed; 9 source files type checked |
| Backend dependency consistency | `pip check` passed |
| Playwright Chromium | 2 tests passed in 1.9 minutes, including real RQ ingestion |
| Frontend unit/component tests | 35 passed across 9 files; final Linux image rerun passed in 10.63 seconds |
| Frontend ESLint / TypeScript | Passed |
| Next.js production build | Passed in the final Docker image with authentication enabled and one build worker |
| Production web container | HTTP 200; headless Chromium confirmed the hydrated sign-in form |
| Compose configuration | `docker compose config --quiet` passed; three data services started |
| Linux API / worker / migration images | Built successfully on 15 October; runtime `pip check` passed |
| Linux RQ worker smoke | Synthetic TXT queued, parsed, embedded with real MiniLM, retrieved through pgvector and deleted successfully |
| API container checks | `/ready` returned 200; unauthenticated upload returned 401; Tesseract 5.5.0 is installed |
| Synthetic Locust smoke | Two users, 30-second requested run, 34 requests including cleanup, zero failures |

The final Locust reporter includes deletion requests after the timed workload, unlike the periodic CSV. The [saved final measurements](phase-3-load-smoke.json) report an aggregate rounded p95 of 410 ms for this tiny mixed CRUD workload. This run used deterministic vectors, synthetic locally signed JWTs, real SQL/S3/RQ operations, no provider calls, and a Windows host running other checks. It cannot establish model latency, sustained throughput, cloud performance, cost/document or 512 MiB fitness. An earlier run exposed a localhost IPv6 connection delay; fixture defaults now explicitly use `127.0.0.1`.

## Coverage and remaining deployment checks

Docker's previous Windows `dockerInference` startup failure no longer reproduces in this session: on 15 October the client and engine both reported 29.8.2, and the API/worker/migration images built and ran successfully. The worker smoke uses the normal Linux RQ process and real local embeddings, without provider calls or HTTP authentication; browser and API tests separately exercise authorization. This verifies a small successful job, not worker termination/recovery or production capacity.

The native Windows frontend rerun stalled; a thread-pool retry ended without a complete suite result. The same 35 tests passed in the final Linux image using the unchanged repository configuration. This validates the frontend in Linux but does not diagnose the Windows runner issue. Exact container test commands are in the phase guide. All ContractIQ test services were stopped afterward; images and persistent volumes were preserved.

Tests cover JWT signature/claims, tenant denial across every document endpoint, Redis fail-closed admission, tenant cache keys and stale cache authorization, RQ identifier payloads, durable ingestion failures, duplicate/late jobs, deletion tombstones, expiry, bounded signed URL issuance, provider retry/fallback boundaries, prompt delimiter escaping, structured/citation validation, metadata-only telemetry and frontend account namespaces/session changes.

Real hosted Supabase login/email confirmation and signing-key rotation, private S3/R2 policy/URL expiry, a real second provider, Sentry delivery, Langfuse dashboard correlation/pricing and a Render/Vercel deployment were not exercised: their accounts/configuration were not supplied. Moto is ephemeral and does not prove cloud access control. Browser fixtures use real signature verification against a local synthetic JWKS and intercept only Supabase auth responses. Test embeddings/provider outputs do not measure AI quality. No private TnC PDF was transmitted in Phase 3.

The dependency audit still reports existing transitive advisories involving `braces` and `sprintf-js`; the registry's available versions checked during this phase were 3.0.3 and 1.1.3, respectively. No patched release was available in those checks. Do not describe the dependency tree as vulnerability-free. Updating those tooling/parser chains needs a compatible upstream release or separately reviewed replacement; a forced major downgrade was not applied.

See [exact commands and the manual deployment checklist](phase-3.md), [load-test instructions](../load/README.md), and the five Phase 3 ADRs beginning with [authentication and data](adr/0004-production-auth-and-data.md). Phase 4 remains outside this change.
