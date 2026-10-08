# Phase 1 — Core AI

## Plan and delivered surfaces

This phase extends the existing FastAPI/Chroma and Next.js deployment with source-located chunking, configurable retrieval, a CUAD audit graph, a transparent priority rubric, negotiation drafts, version comparison, SSE chat, local OCR and local PII redaction. The original upload/paste, benefits, REST chat and metadata history interfaces remain. Phase 2 evaluation and Phase 3 ownership/storage infrastructure are separate work.

Backend responsibilities are separated into `chunking.py`, `locations.py`, `retrieval.py`, `privacy.py`, `ocr.py`, `audit_schemas.py`, `audit.py`, `risk.py`, `india_rules.py`, `comparison.py` and `streaming.py`. Storage now retains page text, source metadata and the original PDF under one TTL. The frontend adds audit/comparison panels and a source viewer, plus typed contracts, an SSE parser and highlighting helpers.

New exact-pinned packages: LangGraph 1.2.14 (workflow control), Presidio Analyzer 2.2.364 and spaCy 3.8.16 with `en_core_web_sm` 3.8.0 (local detection), PDFium 5.14.0 and pytesseract 0.3.13 (bounded local OCR), and PDF.js 5.4.296 (same PDF engine version already used by the fallback parser). FastEmbed's existing ONNX cross-encoder support supplies reranking. BM25/RRF use small explicit implementations rather than another retrieval framework. Compatible NumPy and WebSockets transitive versions are frozen in `constraints.txt`.

## Source and retention contracts

Canonical text joins extracted page strings with two newlines. `start`/`end` are half-open **Unicode code-point** offsets in canonical text; `page_start`/`page_end` index the individual page. They are not PDF byte offsets. Each chunk carries page, section identifier and OCR provenance. Heading detection covers numbered clauses, ARTICLE headings and Section headings. Long sections fall back to the existing recursive 1000/150 splitter. `CHUNKING_STRATEGY=recursive` preserves a comparison baseline. A section continuing onto a new page keeps its identifier.

The source viewer retrieves the original PDF and canonical text from TTL-checked endpoints. PDF.js renders a page and locates the quoted text in its text layer; OCR pages use word boxes from Tesseract. If text order prevents a reliable match, the viewer explicitly shows the canonical extracted passage instead of inventing an approximate PDF highlight. OCR boxes/text are recognition outputs and require visual verification. Repeated quotation occurrences are selected using their page position only when normalized page text agrees between extraction and rendering; otherwise the viewer falls back to canonical text.

**Privacy change:** uploaded PDF bytes are now saved as `source.pdf` in the same UUID document directory as the manifest and vectors. Original DOCX/TXT files are still not retained; extracted page text is. Expiry, explicit deletion, startup cleanup and the periodic sweep cover that entire directory. Original PDFs are readable by anyone with the bearer document ID until expiry/deletion; Phase 3 authentication is still required. Existing Phase 0 documents without page/original-file data require re-upload for audit/source viewing. Browser storage remains metadata-only, including PDF availability, OCR page count and chunking strategy.

## Retrieval

- `dense`: cosine retrieval of four chunks, preserving the Phase 0 strategy.
- `hybrid`: BM25 (k1=1.5, b=0.75) and cosine candidates, combined by Reciprocal Rank Fusion `sum(1 / (60 + rank))`, then four results.
- `hybrid_rerank` (default): rerank the top 12 fused candidates with local ONNX `Xenova/ms-marco-MiniLM-L-6-v2`, then four results. One ONNX thread, batch size four. Increase candidates only after measuring memory/latency. A missing/failed reranker returns a clear 503 rather than silently changing the strategy.

These parameters are engineering defaults, not evaluated optima. RRF and reranker scores are not cosine distances or confidence percentages; responses keep the fields distinct. `Retriever.search(..., strategy=...)` is available for later configuration comparisons. No accuracy/recall claims are made.

## PII and provider boundary

Presidio detects names/locations through the small English spaCy model and identifiers through explicit recognizers (email, phone, card, IBAN, IP, Indian PAN/Aadhaar-shaped strings and a narrow street-address pattern). Detected spans become per-request opaque placeholders before chat questions, history, excerpts, benefits batches and audit evidence reach Groq. The in-memory map restores validated output for display; it is neither logged nor persisted. Date and money entities are deliberately not blanket-redacted because they are contract evidence. No automatic runtime model downloads are permitted for PII; unavailable detection fails closed with 503.

This is best-effort detection, not anonymization certification. Names split across extraction boundaries, unusual identifiers/addresses, non-English text and model misses can remain. `PII_MODE=patterns` is a lighter explicit mode without statistical name detection; it has weaker coverage. Original text/vectors/PDFs remain on the backend until TTL cleanup. No LangGraph checkpointer is used, and external graph tracing is disabled for document processing.

## Audit graph and CUAD attribution

`classify -> choose checklist -> extract -> verify -> summarize` is an executable LangGraph StateGraph. Classification uses opening evidence as a routing hint; an unsupported type quotation falls back to `other`. Checklist selection focuses review but never filters the all-chunk extraction pass. The extractor has a Pydantic enum containing CUAD's 41 types and returns quoted text, chunk ID, party and confidence. The server computes source locations itself, drops unsupported quotations, deduplicates the same type/span, and summarizes counts deterministically. Failed batches or configured clause-limit overflow fail the whole audit.

Quotation verification establishes that the passage exists; **it does not verify the model's clause label, affected party or interpretation**. Those remain explicitly identified model judgments. Confidence is uncalibrated. Empty extraction yields an unscored audit, never a safe-contract verdict. CUAD labels do not cover every lease-specific concern.

Label taxonomy attribution: The Atticus Project, Hendrycks et al., *CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review*, NeurIPS 2021. See the [official CUAD page](https://www.atticusprojectai.org/cuad/), [category definitions](https://github.com/The-Atticus-Project/cuad/blob/main/category_descriptions.csv) and [paper](https://arxiv.org/abs/2103.06268). CUAD v1 is distributed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Labels are used here for classification; no CUAD benchmark or fine-tuning has been run.

## Risk rubric and negotiation drafts

`review-priority-v1` is deterministic and intentionally conservative:

| Priority | Score | Trigger |
| --- | --- | --- |
| High | 80 | Uncapped Liability, Non-Compete, Irrevocable Or Perpetual License, Covenant Not To Sue; or quotation contains restrictive wording such as sole discretion, without notice or non-refundable |
| Medium | 50 | Material-control/continuing-obligation types listed in `risk.py`, such as assignment, termination, minimum commitment, renewal, notice or IP assignment |
| Low | 20 | Other extracted types without an elevated trigger |
| Unscored | null | No verified passages |

Overall priority is the **maximum** clause score. This prevents adding low-priority clauses from diluting a high-priority finding. It is not a probability, fairness ratio, legal-risk prediction or measure of completeness. Scores are insensitive to many numeric/commercial changes; a zero delta can accompany a material change. Keyword triggers can misread context or negation, and clause labels are model-generated; inspect the quote and rationale.

High-priority items receive deterministic illustrative replacement language with the original quote and rationale. These are proposals for negotiation, not source facts, automatic document edits or statements that a clause is unlawful. They must be checked against the entire agreement, the parties' intent and governing law. All outputs retain the informational-only disclaimer.

## Version comparison

The service audits both versions, matches identical normalized quotes/type first, then greedily matches remaining same-type passages by local dense cosine similarity at an explicit 0.72 threshold. Each passage is matched at most once. Remaining passages are added/removed; paired nonidentical passages are changed. The UI shows both original quotes, source links, clause priority deltas and an overall delta when both audits are scored. An extraction miss can appear as an addition/removal. Similarity is uncalibrated, and comparison covers CUAD-extracted passages rather than every textual edit. No semantic-diff accuracy is claimed before Phase 2.

## Streaming

`POST /chat/stream` sends SSE `status`, `draft`, `complete` or `error` events and comment heartbeats. Groq [does not support streaming with strict Structured Outputs](https://console.groq.com/docs/structured-outputs), so streamed chat explicitly uses JSON-object mode plus Pydantic/citation validation and bounded retry. REST chat and audit generation retain native strict schemas. Only the first JSON `answer` field can appear in a draft; reasoning/other fields are not displayed. Drafts retain PII placeholders and are labelled unverified. Final responses restore detected PII and include citations/disclaimer. A failed/truncated stream clears the draft and never appends it to history. Disconnects signal cancellation; a blocked provider read may continue until the configured read timeout, while admission remains locked.

## India lease checklist

The optional pack is configurable per request: state/UT, premises type, user-supplied rent/deposit, explicit model-act comparison assumption and individual rule toggles. The server can disable it with `INDIA_RULE_PACK=false`. It reports evidence/context/review states, never an automatic legal-compliance result. Monetary comparison uses user-entered figures and labels them unverified.

- Applicability: [MoHUA/PIB adoption statement](https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=1779681&lang=2&reg=48); Model Tenancy Act adoption must be checked against state law, exclusions and tenancy facts.
- Deposit and escalation: [Model Tenancy Act 2021](https://mohua.gov.in/upload/uploadfiles/files/Model-Tenancy-Act-English-02_06_2021.pdf), sections 11 and 9. The model deposit benchmark is two months residential/six non-residential; it is not presented as a nationwide cap.
- Notice: [Transfer of Property Act 1882](https://www.indiacode.nic.in/bitstream/123456789/14037/1/transfer_of_property_act8_%281%29.pdf), sections 106–107, with contractual/local-law context.
- Registration: [Registration Act 1908](https://www.indiacode.nic.in/bitstream/123456789/14646/1/ra1908-16.pdf), section 17(1)(d), subject to applicable amendments/exemptions.
- Stamp: [Indian Stamp Act 1899](https://www.indiacode.nic.in/bitstream/123456789/13205/1/the_indian_stamp_act%2C_1899.pdf), sections 3/35 and Schedule I Article 35; applicable state legislation/rates still need verification.
- Lock-in/exit payment: [Indian Contract Act 1872](https://www.indiacode.nic.in/handle/123456789/2187?col=123456789%2F1362), sections 73–74. The checker raises review questions, not an enforceability conclusion.

References were consulted on 2026-10-08. This pack does not maintain a current state-by-state law database, validate stamp/registration records, or substitute for qualified local advice.

## API and deployment

- `POST /audit`: `{doc_id, india?}` -> `AuditResponse` with clauses, locations, risk, redlines, coverage, warnings and rule checks.
- `POST /compare`: `{before_id, after_id}` -> added/removed/changed passages and priority deltas. Both documents must be unexpired.
- `POST /chat/stream`: same request as REST chat; SSE events described above.
- `GET /document/{id}/source`: metadata, canonical pages/OCR boxes and chunks; 409 for legacy records without source data.
- `GET /document/{id}/file`: original PDF bytes, attachment disposition and no-store; TTL checked.

Run one Uvicorn worker. Render Docker installs Tesseract English and preloads the embedding, reranker and small NER models. Local Windows/macOS development needs a separate Tesseract executable on PATH for OCR; `pip install pytesseract` installs only its Python wrapper. OCR triggers only when a PDF page has no extractable text, processes at most ten pages by default, bounds raster size to four million pixels and applies a per-page Tesseract timeout. Mixed pages with sparse but nonempty extraction do not trigger OCR. The fallback Next.js extraction route remains text-only; normal ingestion uses FastAPI OCR.

ONNX, Chroma, spaCy, PDF parsing and Tesseract together are **not certified to fit a free/512 MB instance**. Lighter settings are `RETRIEVER_STRATEGY=hybrid`, `PII_MODE=patterns`, `OCR_ENABLED=false` and smaller document/chunk limits; weaker features are explicitly disclosed. For the full feature set, measure the target container and choose adequate memory. Docker/model downloads increase image/build size. Comparison can use two audit budgets and has a 600-second frontend timeout; host/provider limits may be lower. No memory, cost or latency numbers are estimated.

## Reproduction and manual checks

Observed local results and their limits are recorded in [Phase 1 verification](phase-1-verification.md).

```bash
# Root, Node 22 and Python 3.12
npm ci
npm run lint
npm run typecheck
npm test
npm run build
# Activate .venv first
python -m pip install -r contractiq-backend/requirements-dev.txt
cd contractiq-backend
python -m ruff check .
python -m mypy
python -m pytest -q
# Configure .env using .env.example; install Tesseract for OCR.
uvicorn main:app --port 8000
```

- [ ] Upload a numbered, multipage PDF; check exact canonical offsets and highlighted source passages, including repeated quotations.
- [ ] Upload an image-only PDF with Tesseract installed; verify OCR word boxes against the page image and the limits/error messages.
- [ ] Audit a sample with clauses late in the document; inspect coverage, dropped claims, all parties, the risk rationale and negotiation drafts.
- [ ] Toggle India checks; leave state/applicability/figures blank, then supply explicit assumptions and check source links/context labels.
- [ ] Stream chat, interrupt the connection and reset while pending; confirm drafts never enter saved history and failures preserve the question.
- [ ] Compare two versions with added, removed and revised clauses; inspect both sources and avoid interpreting a negative delta as automatically beneficial.
- [ ] Expire/delete a PDF and verify manifest, original bytes and vectors are removed together; reload history and verify metadata only.
- [ ] Check responsive layout, keyboard navigation and the source dialog in a real browser.
- [ ] Run the Docker image and actual Groq requests on the target host; measure resource use before choosing a free tier.

Suggested phase commit: `feat: add source-grounded contract audit and comparison workflows`.

Phase 2 remains necessary for CUAD/QA evaluation, retrieval comparisons, faithfulness, clause extraction F1 and real latency/cost results. No such metrics are fabricated in this phase.
