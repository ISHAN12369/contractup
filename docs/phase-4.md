# Phase 4: product polish

## Plan and implementation

Add saved audit snapshots, PDF export and capability sharing; expose a bounded cross-document workspace and a risk heatmap; publish actual evaluation evidence and screenshots. The only new runtime dependency is pinned `reportlab==5.0.1` for local PDF pagination and embedded fonts. No frontend package was added. Main risks are confidential data in shared snapshots, source expiry/deletion races, misleading partial evidence, and unsupported PDF glyphs.

Backend additions: `product_schemas.py`, `product_store.py`, `workspace.py`, `reports.py`, `migrations/002_product.sql`, and product/infrastructure tests. Frontend additions: the workspace, report actions, heatmap, `/share` page and runtime product schemas. Existing API, account lifecycle, audit and history hooks integrate these features. `scripts/sample_report.py` produces a synthetic report without model calls.

## User workflow

1. Upload two or more documents, then select two to five in Workspace. Ask a question and expand each citation to see its document and source. A maximum of two retrieved excerpts per document is sampled; use the all-chunk audit for a broader review.
2. Run a clause audit. Inspect the heatmap and source-located findings; a missing finding is never scored as safe. Reopening an uploaded document restores its saved audit if available.
3. Export the latest server-saved audit as PDF. The report includes source coordinates, scores and reasons, negotiation drafts, checklist references, coverage and disclaimers. Re-running an audit replaces the saved report.
4. In authenticated production mode, choose a link lifetime and create a read-only snapshot. Share the complete fragment URL deliberately: the audit contains filenames, quotations and potentially names. Re-running the audit does not change existing shares. Revoke all links for that document to deny future reads.

## API contracts

| Method / route | Result / authorization |
| --- | --- |
| `GET /documents` | Owner's ready, unexpired metadata, newest first, maximum 1,000 |
| `POST /workspace/chat` | `{doc_ids: [2..5 distinct UUIDs], question: string}`; owner-check every document before retrieval and after generation |
| `GET /document/{id}/audit` | Latest server-generated audit and report metadata; 409 before first audit |
| `GET /document/{id}/report` | PDF attachment from saved audit; owner and TTL rechecked after rendering |
| `POST /document/{id}/shares` | `{ttl_seconds: 60..86400}` (default 900); random token and expiry capped by source TTL |
| `DELETE /document/{id}/shares` | Revoke all links for an owned document |
| `POST /share/read` | `{token: 43-character base64url string}`; public capability check, immutable audit only |

Existing `/audit` now saves a successful result; clients cannot supply a report body to fabricate a saved audit. Reports and workspace inference share the bounded operation gate. Private routes retain JWT authentication in production. Only exact POST `/share/read` bypasses JWT; global IP rate limits, body bounds, no-store responses and CORS still apply.

## Retention and privacy

Share tokens contain 256 random bits; only SHA-256 hashes are persisted. URL fragments do not travel in HTTP paths/referrers, and the browser clears the fragment after reading it. Tokens are sent in a POST body; application logs omit request bodies. Do not enable proxy/APM body capture for that endpoint. A refresh after the fragment is cleared needs the original complete link again. Existing viewed/downloaded copies cannot be remotely erased; the shared page clears itself at its advertised expiry, but revocation is enforced on subsequent server reads.

Each share stores an immutable audit snapshot, not original documents or all extracted text. It still includes sensitive quotations and restored names. Maximum ten active shares per document; expired shares are removed when another link is created, or with document cleanup. A share read also checks the source is ready and unexpired, so delayed physical cleanup cannot extend access. Deleting the database document cascades to its share rows. Local mode saves `audit.json` within the document's existing TTL directory and disables sharing.

PDF copies do not expire. The embedded Vera font supports a limited glyph set; unsupported characters are displayed as explicit `[U+XXXX]` escapes rather than silently disappearing. Use the original source for exact non-Latin typography. Paragraph markup from documents is escaped; no external images/URLs are fetched during rendering.

## Migration and startup

Run `python migrate.py` in `contractiq-backend` with production migration credentials before starting the updated API. The runner applies sorted, idempotent migrations under the existing advisory lock. Migration 002 adds `documents.audit_snapshot` and `audit_shares` with an owner/document foreign key. It preserves existing documents. Older documents simply need their first audit before export/sharing. Roll back the application without dropping these additive columns/tables; destructive schema rollback is unnecessary.

For Compose, copy `compose.env.example` to ignored `compose.env`, supply real Supabase and provider settings, then run `docker compose up --build`. The migration/bootstrap service runs before API and worker startup. Moto in Compose is a local emulator, not production storage. See [Phase 3 setup](phase-3.md) for hosted provisioning and the unauthenticated local-development alternative in the root README.

## Reproducible checks

From an activated Python environment in the repository root:

```sh
docker compose up -d --wait postgres redis s3
# PowerShell: $env:RUN_INFRA_TESTS='1'
# POSIX: export RUN_INFRA_TESTS=1
python -m pytest contractiq-backend/tests -q
python -m ruff check contractiq-backend e2e scripts
cd contractiq-backend
python -m mypy
cd ..
npm run lint
npm run typecheck
npm test
npm run build
npx playwright test
python scripts/sample_report.py
```

Playwright needs its Chromium runtime (`npx playwright install chromium`). It starts its own loopback frontend/API and uses isolated SQL schemas, buckets, queues and synthetic JWTs. It uses real infrastructure but deterministic embeddings/provider fixtures. Optional `CAPTURE_DOCS=1` records synthetic screenshots; PowerShell sets this with `$env:CAPTURE_DOCS='1'`. Linux container frontend test commands are in [Phase 3](phase-3.md); expect 41 tests for this phase. Do not use private contracts for published screenshots.

After `docker compose up -d --build --wait`, run the Linux smoke in PowerShell with `Get-Content e2e/docker_smoke.py -Raw | docker compose exec -T api python -` (POSIX: `docker compose exec -T api python - < e2e/docker_smoke.py`). This creates and deletes a synthetic document, checks real embeddings/RQ/SQL/S3, renders a PDF and verifies share revocation without a provider call. Stop the local services afterward with `docker compose stop`; it preserves images and volumes.

## Manual verification checklist

- [ ] Sign in with two disposable real Supabase accounts; verify each workspace, report and share-management endpoint rejects the other account's IDs.
- [ ] Upload two distinct contracts, select both, ask about a difference and inspect each citation against its own original source. Missing evidence must be stated explicitly.
- [ ] Run an audit, export PDF, inspect all pages and compare coverage, quotations and scores with the saved audit. Test non-Latin text and long paragraphs.
- [ ] Create a short-lived share, open it in a guest browser, verify there are no original-source or editing controls, then test expiry and revocation using a fresh fetch. Re-run the audit and confirm the old link remains the original snapshot.
- [ ] Delete the source document and confirm private report and public share access fail. Confirm object/database backup retention independently.
- [ ] Check the read-only page on narrow screens and keyboard navigation; the heatmap must remain understandable without color.
- [ ] Complete hosted bucket, JWKS rotation, fallback-provider, telemetry and deployment checks from Phase 3 before public use.

## Limits and lighter deployment

No paid/live provider calls or private TnC PDF uploads were made in Phase 4. Fixtures verify mechanics, not model quality. The weak/incomplete Phase 2 extraction and generation pilot remains visible in README. Cross-document Q&A adds retrieval work proportional to up to five selected documents; no new cost/latency benchmark was performed. Reports render in memory and are bounded by existing audit/document limits.

The full stack is not certified for 512 MiB or a free tier. For lower memory, use hybrid retrieval without the reranker, pattern-only PII detection (weaker name coverage), disabled OCR, smaller document bounds and managed data services. Public deployment still needs real service configuration and measurements. Dependency advisories and the native Windows Vitest stall remain documented in the verification record.
