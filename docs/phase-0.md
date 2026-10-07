# Phase 0 notes

## Plan and implementation

The backend separates configuration, schemas, safe errors, parsing, structured generation, storage/lifecycle, request limits, and RAG orchestration. The frontend separates presentation, state, typed API access, and metadata-only storage. Upload/paste, history, chat/full-screen chat, scorecards, and source quotations remain available. Unused browser key inputs and the unsupported fairness percentage are removed. The new risk rubric is Phase 1, not implied by significance scores.

Exact direct pins and an npm lockfile are included. `httpx` calls Groq directly, removing redundant LangChain Groq/community/Hugging Face wrappers; LangChain still splits text. `defusedxml` protects DOCX XML, `fflate` preflights fallback DOCX archives, and Zod validates frontend responses. pytest/Ruff/mypy and ESLint/Vitest/jsdom/Testing Library provide verification.

References: [Groq structured outputs](https://console.groq.com/docs/structured-outputs), [Chroma client](https://docs.trychroma.com/reference/python/client). The installed pinned Chroma concrete client has public `close()`; its factory return annotation omits it. A concrete-class cast and integration test cover that boundary.

## API contracts

- `POST /upload`: multipart `file`; returns UUID `doc_id`, `filename`, `chars`, `num_chunks`, Unix-second `created_at`/`expires_at`.
- `GET /document/{id}`: metadata only, used for history restoration; 404 for missing/expired IDs.
- `POST /chat`: UUID, nonblank question up to 2,000 chars, up to six user/assistant messages of up to 6,000 chars. Returns answer, cited sources, informational disclaimer.
- `POST /benefits`: UUID; returns validated `items`, `analyzed_chunks`, `total_chunks`, disclaimer. This replaces the obsolete JSON-string `answer`; deploy frontend/backend together.
- `DELETE /document/{id}`: idempotent, successful only after directory removal. Failed cleanup returns 503 and leaves a tombstone.
- `GET /health`: liveness only. All responses, including preflight, carry request IDs. Safe error bodies omit request data, paths, traces, and provider output.

Every chunk maps into exactly one character-bounded input batch. Default: at most one validation retry (configurable 0–2). Transport/provider failures do not multiply retries. Rejected model text is never reinserted into prompts. Each finding must quote every cited chunk after case/whitespace normalization. Reduce groups party/kind/quotation, keeps distinct items, combines source IDs, and retains the maximum significance for duplicates. This is conservative exact deduplication, not semantic deduplication.

UUIDs are bearer handles, not authenticated ownership. One heavy operation is admitted at a time. Blocking parsing/model calls run in worker threads so health remains responsive. Rate buckets are bounded and process-local. See README for legacy-disk cleanup and accurate retention limits.

## Commands

```bash
# Repository root, Node 22
npm ci
npm run lint
npm run typecheck
npm test
npm run build

# Python 3.12 virtual environment active
python -m pip install -r contractiq-backend/requirements-dev.txt
cd contractiq-backend
python -m ruff check .
python -m mypy
python -m pytest -q
```

## Manual verification checklist

- [ ] Start the backend with a real Groq key and exact browser origin; start Next.js.
- [ ] Upload PDF, DOCX, UTF-8 TXT/MD, then paste text. Confirm ID, expiry, character/chunk counts.
- [ ] Analyze a sample with a late benefit. Check full chunk coverage and its supported quotation; this does not measure extraction recall.
- [ ] Ask about a known clause and open its excerpt/page. Check source text and disclaimer.
- [ ] Seed legacy history/key entries; reload. Verify they are deleted and v2 storage contains only metadata.
- [ ] Reload and restore history without re-uploading. Delete; verify directory removal and 404.
- [ ] Set TTL 10 seconds/sweep 2 seconds; verify browser/API/disk expiry. Restart with expired data and verify startup cleanup.
- [ ] Try spoofed extensions, oversized/streamed requests, disallowed Origin, and rate overflow. Check safe errors and request IDs.
- [ ] Exercise `/api/extract` with supported/malformed files. Verify no-store and sanitized errors.
- [ ] Stop the backend during a request; verify pasted/question text remains for retry. Reset during chat; ensure stale results stay discarded.
- [ ] Check desktop/mobile upload, all parties, quotations, history, and full-screen chat.

## Suggested commits

Phase commit: `feat: establish tested ContractIQ phase 0 foundations`

Optional review split: `fix: analyze every contract chunk with validated outputs`; `fix: bound uploads and expire persisted documents`; `refactor: split contract UI and persist metadata only`; `test: add backend frontend and CI checks`; `docs: document privacy deployment and phase 0 limits`.

## Known limits

See [verification results](phase-0-verification.md) for the checks actually run, remaining dependency advisories, and production HTTP smoke results.

Live Groq quality, free-tier performance, provider quotas, Linux Docker deployment, and evaluation metrics require actual target-environment runs. Mocked tests prove contracts/control flow, not AI quality. No Phase 1–4 features are implied. Python direct versions and the resolved environment are pinned in requirements/constraints; Linux-only uvloop is explicitly constrained but needs Linux validation. The npm lockfile freezes the resolved frontend graph.
