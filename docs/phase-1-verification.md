# Phase 1 verification

Verified locally on Windows on 2026-10-08 with Node 22.14.0, Python 3.12 and the pinned dependency graph. These are software/integration checks, not measurements of extraction accuracy or legal correctness.

| Check | Observed result |
| --- | --- |
| Backend `python -m pytest -q` | 55 passed, 1 skipped; native Tesseract is absent locally |
| Backend `python -m ruff check .` | Passed |
| Backend `python -m mypy` | Passed, 20 source files |
| `python -m pip check` | No broken requirements |
| `npm run lint` and `npm run typecheck` | Passed; production build also completed lint/type validation |
| `npm test` | 30 passed across 7 files |
| `npm run build` | Next.js 15.5.27 production build passed |
| Production HTTP smoke | Homepage 200; actual PDF/DOCX/TXT fallback extraction; request IDs, no-store, cross-origin rejection and upload size limit passed |
| Real local ONNX inference | FastEmbed returned two finite 384-dimensional vectors; MiniLM cross-encoder returned a finite score per candidate |
| Production browser smoke | Synthetic PDF upload, source-located audit, India context fields/checks, PDF rendering with exact quotation highlight, SSE chat completion with citation, and ordered version comparison with both source links passed using a mocked provider |
| npm dependency audit | 10 affected entries: 7 high, 3 moderate, 0 critical; inherited advisories remain unresolved |

## What the tests establish

Backend tests cover heading detection and exact page/global offsets, recursive fallback, BM25/RRF and strategy selection, all 41 CUAD labels, quote verification and unsupported-claim removal, the executable LangGraph workflow, risk/redline output, one-to-one semantic clause comparison, context-dependent India rules, Presidio identifier/name detection and reversible display, redaction of provider-bound chat/history, SSE parsing/retries/truncation/cancellation, original-PDF expiry/deletion, and OCR limits/coordinates. The existing Phase 0 regression suite remains passing.

The OCR renderer test uses real PDFium with mocked Tesseract output. The native executable test skips only when Tesseract is unavailable. GitHub Actions installs English Tesseract before running pytest; that Linux CI run has not been observed here.

Frontend tests cover typed responses, fragmented UTF-8/CRLF SSE frames and safe completion, draft clearing on errors, canonical Unicode code-point offsets, repeated-quotation ambiguity, audit/redline/source controls, ordered distinct-version selection, accessible source-dialog closure, expired source errors and stale-audit clearing, alongside the existing history/API/parser/component tests. PDF text order that cannot establish an unambiguous repeated occurrence falls back to canonical extracted text.

The browser check ran the production Next.js build with the real FastAPI routes, document parser, storage, audit graph and UI. Its Groq transport and vector index were deterministic local doubles using synthetic contracts. Actual ONNX inference was checked separately. It therefore establishes connected application behavior, not the quality of model judgments. The PDF worker loaded, the page rendered, and the quotation highlight visibly aligned with the synthetic sentence. No browser error/warning was reported at that point.

The sandboxed preview was inaccessible from the browser; running the same production build outside the sandbox resolved the connection. The final build/test processes exited successfully. Frontend tests run with one worker after an earlier concurrent dependency/model workload caused worker-start and parser-import timeouts. Test durations are not application latency measurements.

## Reproduction

From the repository root (PowerShell):

```powershell
npm.cmd ci
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
.\.venv\Scripts\python.exe -m pip install -r contractiq-backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
Push-Location contractiq-backend
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m mypy
..\.venv\Scripts\python.exe -m pytest -q
Pop-Location
```

Create/activate a Python 3.12 virtual environment first if needed. Install the native Tesseract executable with English language data and put it on PATH to run the skipped OCR test. Configure `.env` using the backend example for actual provider requests. For the local inference smoke, the delivery package includes `.phase1-delivery/verify_models.py`; run it with the workspace Python. It downloads the exact configured models if they are absent.

See [the manual verification checklist](phase-1.md#reproduction-and-manual-checks) for multipage/repeated-text PDFs, scans, real provider requests, cancellation, expiry and deployment checks. Synthetic single-page visual success does not complete all those checks.

## Remaining limits

- No live Groq credentials were available. Provider contract tests use mocked HTTP responses; actual streamed/native-schema compatibility still needs a real-key check.
- Native Tesseract OCR, the Docker image, Linux dependency/model preloading and Render/Vercel deployment were not verified locally. Docker was unavailable. CI is configured but has not run on GitHub in this task.
- No CUAD/QA quality metrics, retrieval comparison metrics, latency percentiles, memory measurements or cost figures have been produced. Phase 2 must establish them; no estimates are substituted.
- The full ONNX/Chroma/spaCy/OCR combination is not certified for a 512 MB/free host. Documented lighter options are hybrid retrieval without reranking, pattern-only PII detection and disabled OCR, with their explicit coverage tradeoffs.
- PII detection is best effort. Source/PDF/vector storage remains TTL-based and UUIDs remain bearer handles pending Phase 3 ownership controls. Legal outputs are informational and require qualified review.
- Existing npm advisories are described in [Phase 0 verification](phase-0-verification.md#dependency-decisions-and-remaining-advisories). This phase does not claim a clean vulnerability audit; Python dependencies have not undergone an independent vulnerability audit.
