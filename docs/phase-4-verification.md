# Phase 4 verification

Recorded on 16 October 2026. Synthetic fixtures verify application behavior, not legal correctness or real-model quality. No private TnC PDF was transmitted and no paid provider calls were made in this phase.

## Recorded checks

| Check | Result |
| --- | --- |
| Complete backend suite with real infrastructure enabled | 81 passed, 1 skipped, 1 dependency deprecation warning; 68.74 seconds, exit 0 |
| Real infrastructure coverage | Seven tests against Postgres/pgvector, Redis and HTTP Moto S3, included above |
| Native OCR skip | Windows Tesseract executable absent; Linux image supplies it |
| Backend Ruff / strict mypy | Passed; 34 source files type checked |
| Python dependency consistency | `pip check` passed |
| Frontend unit/component suite | 41 passed across 10 files in the Linux image; 17.09 seconds |
| Playwright Chromium | Both existing scenarios passed; the new Phase 4 scenario passed on its targeted rerun, including guest revocation |
| Final production frontend build | Passed with authentication enabled; lint and TypeScript validation passed without the earlier hook warning |
| Linux API / worker / migration images | Built successfully with ReportLab 5.0.1; runtime `pip check` passed |
| Compose startup and migration | All services started; migration completed and API readiness returned 200 |
| Linux worker/product smoke | Synthetic TXT ingested with real MiniLM embeddings, retrieved, saved as an audit, rendered as PDF, shared, revoked and deleted successfully |
| Production route smoke | Unauthenticated `/documents` returned 401; built frontend `/share` returned 200 |
| PDF output | Two-page synthetic sample rendered with PDFium and both pages visually inspected; no clipping or missing footer |
| PDF regression cases | Escaped markup, unsupported-glyph notation and long multi-page output passed |
| Browser screenshots | Workspace, heatmap and guest audit captured from synthetic browser fixtures and visually inspected |

Product tests cover saved report retrieval, missing/forged report rejection, local-mode sharing denial, document listing/deletion, bounded cross-document requests, authorization before provider calls and after generation, redaction, prompt delimiter escaping, citation identity and fabricated citation rejection. Infrastructure tests also check owner isolation, hashed tokens, immutable share snapshots, expiry, revocation, source deletion, public no-store responses and unauthenticated private-route denial. Frontend tests cover stale responses, account lifecycle, share creation/revocation, local-mode restrictions and expiry of the shared page.

The native Windows Vitest run stalled and was cancelled without a complete result. The unchanged test configuration passed in a Linux container. Browser development servers run natively; browser checks therefore provide separate Windows application coverage. Initial browser attempts exposed test locator issues: a filename included child metadata, Next.js also supplied an alert role, and fragment-only navigation retained the previously viewed copy. Selectors now target semantic controls/the main page, and revocation checks explicitly perform a fresh navigation. The server correctly returned 404 after revocation.

## Dependency advisory check

The clean frontend image's `npm audit --json` reported three moderate advisories and zero high/critical advisories on this date. Affected dependency chain: `mammoth` / `argparse` / `sprintf-js`. This differs from the historical Phase 3 registry result without changing the lockfile. It is not evidence that the dependency tree is vulnerability-free. Registry checks returned Mammoth 1.13.0 and sprintf-js 1.1.3 as latest; sprintf-js 1.1.3 remains within [the advisory's affected range](https://github.com/advisories/GHSA-hp3w-g68c-fv3c). The audit suggested a major downgrade to Mammoth 0.3.29, which was not applied. The local fallback extraction route using Mammoth remains disabled in authenticated production mode; the dependency is still present in the build.

## Evidence and limits

README reproduces the existing Phase 2 harness measurements and Phase 3 CRUD load smoke without inventing new figures. CUAD extraction F1 was zero in the one-document pilot; the generation pilot scored only one of 24 cases. Phase 4 fixtures do not supersede those results. The 410 ms p95 is a rounded aggregate for the earlier tiny CRUD workload, not generation latency. Real-provider p95, cost/document and 512 MiB fitness remain unmeasured.

Hosted Supabase flows/key rotation, private cloud bucket policy, a real second provider, Langfuse pricing/correlation, Sentry delivery, and Render/Vercel deployment remain unverified because their deployment configuration/accounts were not supplied. Moto does not establish cloud access control. Downloaded PDFs and already viewed shares cannot be erased by revocation. Non-Latin PDF typography uses explicit Unicode escapes when the embedded font lacks glyphs.

All ContractIQ test services were stopped after verification; images and database/Redis volumes were preserved. The disposable frontend test container was removed. Changed-file credential-pattern and documentation-link checks passed.

See [exact commands and manual checklist](phase-4.md) and [the design decision](adr/0009-audit-sharing-and-workspace.md).
