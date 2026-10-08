# ContractIQ

Explore property contracts through source-backed Q&A and a benefits/obligations scorecard. **Informational only, not legal advice.** Check findings against the original agreement and consult a qualified professional before making decisions.

Phase 1 adds core AI workflows to the tested foundations. This is a bounded, single-worker prototype. Authentication and per-user isolation are planned for Phase 3. Anyone holding a document ID can read its text/original PDF, query it, analyze it, or delete it. Use non-sensitive sample documents for a public demo.

## Functionality through Phase 1

- Upload PDF, DOCX, UTF-8 TXT/MD or paste text. Default limits: 2 MiB, 60 PDF pages, 100,000 extracted characters, 120 chunks, 20 retained documents.
- Clause-aware splitting with section/page/character offsets and recursive fallback (1,000 characters / 150 overlap), local ONNX FastEmbed `sentence-transformers/all-MiniLM-L6-v2`, per-document persisted Chroma with cosine distance.
- Configurable dense, BM25+dense/RRF, or hybrid+ONNX cross-encoder retrieval (default). Four final excerpts feed Groq `openai/gpt-oss-20b`. REST/audits use strict structured output; SSE chat uses JSON-object mode with Pydantic/citation validation, clearly marked drafts and a validated final response.
- Benefits analysis maps **every** chunk in bounded batches, checks quoted evidence, then deterministically merges duplicate party/kind/quotation findings. No keyword/top-five sampling or lossy LLM reduction. A failed batch fails the whole request; partial results are never reported as complete.
- All parties and benefits remain visible. Benefit significance scores (1–10) are model-generated and uncalibrated. The separate audit provides an explicit review-priority rubric; neither score measures fairness or enforceability.
- A LangGraph classify/checklist/extract/verify/summarize workflow extracts CUAD's 41 clause types over all chunks, drops unsupported quotations, computes review priorities and supplies illustrative negotiation drafts. Version comparison aligns extracted clauses and shows both sources and priority deltas.
- PDF source viewer with text/word-box highlights, bounded Tesseract OCR for empty PDF pages, local Presidio redaction before provider calls, and an optional India lease checklist citing official sources. Detection, OCR, model interpretations and legal applicability remain fallible.
- Byte/type/size validation, archive expansion checks, limits before multipart parsing, explicit CORS origins, generated request IDs, bounded rate limits, sanitized errors, periodic document expiry/deletion.
- Components/hooks/lib, a runtime-validated typed API client, and metadata-only history with migration that removes old stored contract text and obsolete API keys.

## Architecture

```mermaid
flowchart LR
  B[Browser: metadata-only history] --> N[Next.js 15 on Vercel]
  B --> A[FastAPI on Render: one worker]
  N --> X[Optional /api/extract: bounded local extraction]
  A --> P[Validate and parse]
  P --> O[Empty pages: bounded Tesseract OCR]
  P --> C[Clause-aware chunks + FastEmbed]
  O --> C
  C --> D[(Page text, original PDF, manifest and Chroma)]
  D --> Q[BM25 + dense RRF + ONNX rerank]
  D --> M[All-chunk map + deterministic reduce]
  D --> W[LangGraph audit and semantic comparison]
  Q --> R[Local Presidio redaction]
  M --> R
  W --> R
  R --> G[Groq JSON + Pydantic + source verification]
  D --> V[TTL-checked source viewer]
  T[TTL sweep + explicit DELETE] --> D
```

The UI uploads once to FastAPI. `/api/extract` remains a standalone text-extraction fallback, not an alternative AI backend. Its output is never saved to browser storage by the app.

## Local setup

Use Node 22 and Python 3.12 (the Docker/CI version).

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r contractiq-backend/requirements-dev.txt
cd contractiq-backend
# Copy .env.example to .env and set GROQ_API_KEY.
uvicorn main:app --reload --port 8000
```

In another terminal, from the repository root:

```bash
npm ci
# Copy .env.example to .env.local.
npm run dev
```

Open `http://localhost:3000`. First ingestion/retrieval downloads embedding/reranking models unless cached. Requirements install the pinned small spaCy model. Install the Tesseract executable with English language data on PATH for local OCR; the Dockerfile supplies it on Linux. Unit/API tests require neither ONNX downloads nor Groq credentials. Use one Uvicorn worker: locks, rate limits, and admission control are process-local.

## Verification

```bash
# Repository root
npm run lint
npm run typecheck
npm test
npm run build

# Activated Python environment, backend directory
cd contractiq-backend
python -m ruff check .
python -m mypy
python -m pytest -q
```

Tests cover whole-document map coverage, deduplication, invalid/truncated model outputs and bounded retries, unsupported quotations, failed batches, upload spoofing, archive bombs, streamed limits, CORS, request IDs, rate limits, TTL/restart/failure cleanup, API flow with mocked Groq, history migration/expiry, failed deletion, stale async results, citations, and fallback extraction. Real Chroma persistence/retrieval/deletion is tested with deterministic vectors. GitHub Actions runs backend lint/typecheck/tests and frontend lint/typecheck/tests/build.

No retrieval accuracy, faithfulness, latency p95, cost-per-document, or legal-accuracy metrics have been measured. Phase 2 must produce actual evaluation results; none are estimated here.

## Privacy and retention

1. Upload bodies are bounded and parsed transiently; framework spools close after processing. Original PDFs are now retained for the source viewer; original DOCX/TXT files are not. OS temporary data can survive abrupt process/host crashes.
2. Canonical page text, OCR boxes and chunks/metadata persist in `DATA_DIR/documents/<uuid>/document.json`; original PDFs in `source.pdf`; embeddings in `vectors/`. **This is disk persistence, not zero persistence.** Default TTL: one hour from indexing start, including across restarts if the disk survives. All three are inside the same deletion boundary.
3. Expired IDs are rejected immediately. A startup sweep and a 60-second periodic sweep remove the entire directory. Explicit deletion removes access before unlinking files. Failed filesystem deletion is logged without content and retried; explicit DELETE does not claim success while removal is pending. Cleanup cannot run on a suspended/stopped host and resumes on startup. Deletion is not forensic secure erasure and does not control host backups.
4. Browser storage retains only IDs, filenames, character/chunk counts, and creation/expiry times. Filenames can themselves be sensitive. Chat, quotations, scorecards, and pasted text stay in current-session memory. Loading this version removes old full-text history and HF/Groq keys; browsers that never load it cannot be migrated remotely.
5. Groq receives excerpts for chat, every chunk for benefits/audits, the question and up to six history messages after local Presidio replaces detected PII with reversible placeholders. Detection can miss information; no anonymity guarantee is made. Restoration maps stay in request memory. App TTL cannot remove provider-held data; review [Groq's data policy](https://console.groq.com/docs/your-data). The layout requests Google Fonts. Chroma telemetry and external LangGraph tracing are disabled; document bodies/provider responses are not logged by the app.
6. Legacy `chroma_db/` and `uploads/` folders have no TTL manifests and are not opened by this version. Before reusing an old disk, stop the old server and remove those legacy backend directories after verifying their resolved paths. Re-upload documents. The new sweeper only deletes its own UUID directories.

Delete-all removes server documents represented by the last 10 remembered entries. Older browser-history entries remain subject to their original backend TTL.

## Render + Vercel deployment

Keep the two-service deployment. On Render use Docker with context `contractiq-backend` or the existing blueprint, set `GROQ_API_KEY`, and set `CORS_ORIGINS` to the exact frontend origin. Add preview origins individually; wildcard subdomains are rejected. Set Vercel's `NEXT_PUBLIC_RAG_API_URL` to the backend HTTPS URL. Keys belong only on the backend. Deploy frontend and backend together because `/benefits` now returns structured `items` instead of a JSON string.

Docker preloads the embedding/reranker models, installs the small NER model and Tesseract English, and starts one worker. `/health` is liveness only, not provider/model readiness. Configure Uvicorn proxy trust only for known proxy addresses; do not set `FORWARDED_ALLOW_IPS=*` on an exposed origin. Until trusted proxy addresses are configured, clients behind the same proxy may share a rate-limit bucket. CORS does not authenticate non-browser clients.

Free/low-memory suitability is a goal, **not a measured guarantee**. FastEmbed, the reranker and HNSW use one thread, and only one upload/chat/analysis job is admitted at a time. Chroma, ONNX, spaCy and OCR can exceed a small tier's memory. Lighter options are `RETRIEVER_STRATEGY=hybrid`, `PII_MODE=patterns` (weaker name coverage), `OCR_ENABLED=false`, and smaller `MAX_TEXT_CHARS`, `MAX_CHUNKS`, `MAX_DOCUMENTS`. Use a larger-memory tier for the full feature set if measurements require it. No PyTorch or sentence-transformers runtime is loaded.

Whole-document analysis can exceed free provider quotas or the 240-second budget. Failures are explicit rather than silently dropping chunks. Reduce document size; raise budgets only after checking hosting/provider limits. Browser timeout: 300 seconds, or 600 for comparison of two audits; host limits may be lower. No latency or memory numbers are asserted without measurements.

## Limitations and future phases

- No auth, per-user isolation, distributed limiter, queue, cloud storage or multi-worker support yet. Next.js extraction uses a global per-instance budget, not a distributed Vercel limiter.
- Format checks are not antivirus or a full parser sandbox. PDFs/OCR can still be resource-intensive. Backend DOCX extraction reads main paragraphs/tables, not separate footnotes/headers/text boxes.
- Supported quotations and citation IDs cannot establish truth or correct legal interpretation. Coverage counts processed chunks, not extraction recall. Case/whitespace-normalized exact dedupe can retain paraphrases and party aliases.
- PDF highlights depend on matching text-layer order or OCR word boxes; unmatched PDF passages fall back visibly to canonical extracted text. Character offsets describe extraction, not the original PDF's byte layout.
- Next.js is upgraded from 14 to 15.5.27 with React 19 because the old line is affected by an unpatched Windows RCE advisory. Render/Vercel and the App Router structure remain unchanged. [Maintainer advisory](https://github.com/vercel/next.js/security/advisories/GHSA-p293-qw3h-jr36). ESLint 8 and Tailwind 3 still use older tooling; remaining advisories are documented in the verification notes.

See [Phase 1 implementation and manual checklist](docs/phase-1.md) for API contracts, privacy changes, risk rubric, source references and deployment tradeoffs, and [Phase 1 verification](docs/phase-1-verification.md) for observed results and unverified checks. [Phase 0 verification](docs/phase-0-verification.md) remains a historical record. Phase 2 evaluations start only on request.
