# Phase 0 verification

Verified locally on Windows on 2026-10-08, with Node 22.14.0 and Python 3.12 in `.venv`. These are software checks, not AI-quality evaluation results.

| Check | Observed result |
| --- | --- |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed |
| `npm test` | 21 tests passed across 5 files |
| `npm run build` | Next.js 15.5.27 production build passed |
| `python -m ruff check .` (backend) | Passed |
| `python -m mypy` (backend) | Passed, 9 source files |
| `python -m pytest -q` (backend) | 37 tests passed |
| Production HTTP smoke test | Homepage HTTP 200 with upload/chat content; actual PDF, DOCX and TXT extraction succeeded; request IDs and no-store verified; cross-origin and oversized requests rejected |
| `npm audit --json` | 10 affected package entries: 7 high, 3 moderate, 0 critical; see below |

The HTTP smoke test launched the final production build on localhost, exercised `/api/extract`, and stopped its server afterward. This confirms the `pdf-parse` external package/worker path in a local production process. It does not establish deployment success on Vercel or Render. Visual browser review was not completed: the browser connection timed out.

The backend suite uses mocked Groq responses and deterministic embeddings. It also runs actual Chroma persistence/search/deletion and actual PDF parsing. It covers all-chunk processing, exact deduplication, quote/citation validation, bounded retries, failure behavior, upload validation, CORS/rate limits, request IDs, and TTL cleanup. Frontend tests cover metadata-only history and migration, API validation, asynchronous state races, retry behavior, all-party findings/citations, and actual fallback parsers.

One backend run printed a Windows WMI exception diagnostic during a dependency import; the process nevertheless exited successfully with all 37 tests passing. This should be checked if it recurs outside this Windows/OneDrive environment. Tests needed to run outside the restricted filesystem sandbox because temporary directory/file creation was denied inside it.

## Dependency decisions and remaining advisories

Next.js 14 was affected by the maintainer's [Windows command-injection advisory](https://github.com/vercel/next.js/security/advisories/GHSA-p293-qw3h-jr36). This phase pins Next.js 15.5.27 and matching ESLint configuration, with React 19.3.0. The App Router and Render/Vercel topology remain. Existing CSS is retained on Tailwind 3.

A real-PDF regression exposed `pdf-parse` 1.1.1 rejecting a valid PDF with a bad-XRef error. The fallback now uses pinned `pdf-parse` 2.4.5 with its documented `PDFParse` lifecycle, explicit cleanup, disabled JavaScript evaluation, and Next.js external-package configuration. Tests and the production HTTP smoke both extracted the fixture. References: [parser documentation](https://github.com/mehmet-kozan/pdf-parse), [maintainer's Next.js configuration](https://github.com/mehmet-kozan/vercel-next-app-demo/blob/main/next.config.ts).

The remaining npm advisories are **not resolved**:

- [`braces` stack-exhaustion DoS](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), propagated through `micromatch`, `fast-glob`, `chokidar`, Tailwind and Next ESLint tooling: seven high-severity package entries. These paths process repository globs during tooling; the application does not pass uploaded contract text as glob patterns. Moving to Tailwind 4/other tooling requires a separate compatibility migration. This scope assessment is not a guarantee of safety.
- [`sprintf-js` precision DoS](https://github.com/advisories/GHSA-hp3w-g68c-fv3c), through `argparse` and `mammoth`: three moderate package entries. Inspection found Mammoth's use of `argparse` in its CLI; the application calls the `extractRawText` library API. The installed graph still contains the affected dependency. The audit's suggested Mammoth downgrade is not adopted because it would replace the supported parser with a much older release.

There was no newer patched `braces` or `sprintf-js` release available when checked. Do not treat the audit as clean or run `npm audit fix --force` without reviewing the resulting framework/parser changes. Python dependencies have not undergone an independent vulnerability audit in this phase.

Direct dependencies are exact-pinned. `package-lock.json` and Python `constraints.txt` capture resolved versions. npm 10.9.2 hit an `edgesOut` resolver error while upgrading the dependency graph; an isolated npm 11.6.0 invocation completed installation without changing global npm. Normal reproduction uses the committed lockfile with `npm ci`. If that local npm bug recurs, use `npm exec --yes --package=npm@11.6.0 -- npm ci`.

## Reproduction

From the repository root:

```bash
npm ci
npm run lint
npm run typecheck
npm test
npm run build
python -m venv .venv
# Activate .venv before the remaining Python commands.
python -m pip install -r contractiq-backend/requirements-dev.txt
cd contractiq-backend
python -m ruff check .
python -m mypy
python -m pytest -q
```

The [manual checklist](phase-0.md#manual-verification-checklist) remains the guide for a real-key and visual deployment check. Automated test success does not mark those manual items complete.

The typecheck command generates Next.js route types first, so it can run before the production build in a fresh checkout.

## Unverified and deferred

- No live Groq request, semantic extraction-quality benchmark, retrieval evaluation, latency p95, cost-per-document or memory measurement was performed. No values are estimated.
- The Docker daemon was unavailable, so the Linux image was not built/run. CI is configured but has not run on GitHub. Linux-only dependency resolution and model preloading still require a target-environment check.
- No authenticated ownership exists; UUIDs are bearer handles until Phase 3. Rate/admission controls are process-local, and only one backend worker is supported.
- No OCR, PII redaction, exact PDF highlights, clause-aware/hybrid retrieval, risk rubric, streaming or later-phase product features are included.
- Whole-document analysis can exceed free provider quotas/time budgets. Low-memory hosting is not certified; lower document/chunk limits or use a larger tier if measurements require it.
