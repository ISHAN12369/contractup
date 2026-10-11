# Phase 2 verification

Local verification completed on 11 October 2026; individual run timestamps are retained in JSON. These results measure information retrieval and a limited extraction/judge workflow, not legal correctness. All legal output remains informational only, not legal advice.

## Implemented and tested

The evaluation harness uses the production chunker, embedding/index, hybrid retriever, reranker, answer service and audit graph. It adds exact CUAD span validation, forty fixed synthetic golden questions, six configurations, retrieval metrics, a versioned claim-support/directness judge, extraction span matching, saved-prediction scoring, JSON/Markdown reporting, source/model provenance, Make targets and CI checks. No dependency versions or deployed application code changed.

| Check | Actual local outcome |
| --- | --- |
| Evaluation tests | 18 passed |
| Evaluation Ruff | Passed |
| Evaluation mypy | Passed, 9 source files |
| Backend regression tests | 55 passed, 1 skipped (native Tesseract unavailable) |
| Complete local retrieval matrix | 804 question/configuration rows, zero runtime failures |
| Groq native schema probe with the configured key | HTTP 200, validated AnswerResult |
| Bounded live pilot | Completed with errors: 1/24 generation evaluations scored; both audits failed |
| Separate live extraction diagnostic | Two HTTP 200 calls; one source-located clause extracted and scored |
| Supplied PDF local-only retrieval | 60 question/configuration rows, zero runtime failures; raw data and report ignored |

The initial sandboxed pytest run could not create its temporary directories; the same suite passed with normal filesystem permissions. The pilot's new selection test initially caught missing document prefixes in question IDs; that code was fixed before provider execution and all 18 tests passed afterward. Frontend build/browser checks were not repeated because Phase 2 changes no frontend code; prior Phase 1 results remain historical. Linux CI and deployment were not run in this phase.

## Full bounded retrieval run

Command: `python -m evals.run --output evals/results/phase-2-retrieval` with `HF_HUB_OFFLINE=1` and existing model caches. The real run completed in 1719.2 seconds; this is whole-benchmark wall time, not an application latency statistic.

Ten deterministically selected CUAD test documents yielded 94 answerable category questions and 198 extraction gold spans. Five synthetic documents contributed 40 golden questions, including five unanswerable cases. Every question ran against both chunkers and all three retrievers: (94 + 40) * 6 = 804 rows. The generation/extraction cells in this offline run are unrun, not zero.

CUAD retrieval, each row measured over all 94 answerable questions:

| Configuration | Hit@4 | MRR@4 | Span Recall@4 |
| --- | --- | --- | --- |
| Recursive + dense | 0.4255 | 0.3067 | 0.3697 |
| Recursive + hybrid | 0.5532 | 0.3936 | 0.4766 |
| Recursive + hybrid + rerank | 0.5106 | 0.3794 | 0.4328 |
| Clause + dense | 0.4574 | 0.3156 | 0.3936 |
| Clause + hybrid | 0.5532 | 0.3918 | 0.4846 |
| Clause + hybrid + rerank | 0.5213 | 0.3723 | 0.4449 |

Hybrid improves aggregate CUAD retrieval over dense on this sample; reranking loses some of that improvement. Clause-aware hybrid has the highest span recall here, but this is neither a statistical-significance result nor a reason to silently change the production configuration. On the easier synthetic set, both reranked configurations reach Hit@4 and span Recall@4 of 1.0 across 35 answerable questions. All configurations and denominators appear in [the measured table](../evals/results/phase-2-retrieval/results.md) and [raw evidence](../evals/results/phase-2-retrieval/results.json).

Examples inspected by comparing saved ranks to validated gold offsets:

- HC2 cooperation agreement, Document Name: the gold interval is [40054, 40075). Recursive hybrid retrieves [39786, 40542) at rank two; dense misses it. Clause hybrid also finds it at rank two, while reranking pushes supporting evidence out of the top four.
- SPOK cooperation agreement, Expiration Date: clause hybrid misses [16533, 16956), while its reranked version retrieves [16373, 17370) at rank two. Reranking can help individual questions while hurting the aggregate.
- Synthetic service question 2, withholding a disputed invoice: clause dense finds [744, 855) at rank one; clause hybrid returns administrative distractors and misses it. This demonstrates why the synthetic suite retains distractor text.

## Live generation pilot: incomplete coverage

Exact command used:

```powershell
$env:HF_HUB_OFFLINE='1'
.\.venv\Scripts\python.exe -m evals.pilot --env-file contractiq-backend/.env --output evals/results/provider-pilot
```

The explicit local env file overrides a stale process key; the credential is ignored by Git and absent from reports. The provider and judge used `openai/gpt-oss-20b`. The fixed pilot selects one CUAD question plus deposit/termination/unanswerable questions from the existing lease fixture, for four questions * six configurations. It is not a second forty-question corpus. Both clients share a three-second minimum interval, including schema retries.

The run made 20 HTTP 200 responses and received 24 HTTP 429 responses. Only one of 24 answer-plus-judge workflows completed; 22 question rows ended with a rate-limit ServiceError and one with ModelFailure. Both matrix audit rows ended with a rate-limit ServiceError. HTTP successes do not equal scored answers because each workflow makes multiple calls. The report exits nonzero and retains `completed_with_errors` status. The account returned a token limit of 8,000 per minute; request pacing alone did not ensure token-budget compliance. [Groq documents the separate quota dimensions](https://console.groq.com/docs/rate-limits).

The single surviving recursive+dense CUAD answer scored faithfulness 0.5, relevance 1.0 and abstention accuracy 1.0. This is **one observation**, not a mean with comparable coverage across configurations. The judge supported the effective/signature dates but counted a recommendation for lawyer review among unsupported claims, despite the decomposition rubric excluding simple disclaimers. That manual inspection exposes judge bias and imperfect claim decomposition; do not interpret the 0.5 as a calibrated legal or factual quality score. No prompt was tuned or case removed to raise it.

The [live pilot table](../evals/results/provider-pilot/results.md) and [per-answer judgments/errors](../evals/results/provider-pilot/results.json) preserve all attempted rows. A complete generation comparison remains pending an adequate provider token budget and independently reviewed scoring. Re-running the command may still hit the same limits; changing to a different model requires separately labelled results.

## Separate extraction observation

After the pilot, a separate diagnostic audit processed the same 857-character CUAD amendment with the production clause chunker, standard PII redaction and the same provider model. Its classify and extract calls returned HTTP 200. The audit processed its one chunk, returned one source-located Effective Date passage and dropped zero quotations. This diagnostic does not replace either failed matrix audit.

| Scope | True positives | False positives | False negatives | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| One document, seven annotated spans, one predicted span | 0 | 1 | 7 | 0.0 | 0.0 | 0.0 |

The extracted Effective Date quotation covers [69, 488), whereas the exact gold date is [168, 184). Their character IoU is below the fixed 0.5 threshold, so the broad quotation is unmatched. The other annotations include Agreement Date, Document Name and Parties. Source support alone does not establish span precision or extraction completeness. This exposes a real mismatch between the application's broad quotations and CUAD's fine-grained annotations. The score is not the official CUAD token-overlap metric.

The [raw audit](../evals/results/extraction-pilot/audit.json), [predicted spans](../evals/results/extraction-pilot/predictions.json), [provenance](../evals/results/extraction-pilot/provenance.json) and [computed scores](../evals/results/extraction-pilot/results.json) are retained. Reproduce the deterministic scoring without any provider call:

```powershell
.\.venv\Scripts\python.exe -m evals.score_predictions --cuad-limit 1 --predictions evals/results/extraction-pilot/predictions.json --output evals/runs/extraction-recheck.json
```

The ignored delivery helper `quota_diagnostic.py` reproduces the live audit path; fresh model output need not be identical. Its checksum is in the provenance. No full-corpus extraction result is claimed.

## Local sample and privacy

The supplied five-page sample was parsed by the production PDF extractor into 19 chunks with no OCR. Its lettered headings remain `unsectioned`, so clause-aware mode falls back to recursive splitting and both modes produce identical sample metrics. This limitation was observed without modifying the chunker during evaluation.

Ten locally authored draft questions (nine answerable, one absent term) ran across six configurations. Dense found supporting evidence for 8/9 answerable questions, hybrid for 7/9, and hybrid+rerank for 9/9. The latter MRR@4 was 0.8056. No generated-answer or extraction score is inferred from this local retrieval check. The PDF was not sent to Groq. Its text, derived fixture and detailed results remain in ignored local paths, outside published artifacts and Git.

## Reproduction and remaining checks

From the repository root, after installing the existing pinned development requirements:

```powershell
.\.venv\Scripts\python.exe -m evals.prepare
.\.venv\Scripts\python.exe -m pytest -q evals/tests
.\.venv\Scripts\python.exe -m ruff check evals
.\.venv\Scripts\python.exe -m mypy --config-file evals/pyproject.toml evals --exclude tests
Push-Location contractiq-backend
..\.venv\Scripts\python.exe -m pytest -q
Pop-Location
.\.venv\Scripts\python.exe -m evals.run --output evals/runs/reproduction
```

With GNU Make installed and the environment active, `make eval` is equivalent to dataset preparation plus the default retrieval run. Make is unavailable on this Windows host, so the Python equivalents were used. Reports capture the pre-commit Git revision and source-file hashes. The full retrieval benchmark predates the new bounded pilot module and a type-only annotation in the saved scorer; its chunker, retrieval and metric implementations were unchanged.

- Independently review the forty authored references and judge outputs, particularly exceptions, missing information and disclaimers.
- Complete a provider run with sufficient token quota; retain failed runs and compare only complete coverage.
- Test a different judge and human annotations before making quality claims.
- Evaluate all 88 length-eligible CUAD test documents separately; 14 longer/multi-context documents are excluded by declared application limits.
- Reproduce on another host; Linux CI, native OCR, Docker deployment, memory, latency percentiles and cost remain unmeasured here.
- Use a distinct development set for future extraction/chunking improvements instead of repeatedly tuning on this reported test sample.

Phase 3 infrastructure and optional classifier fine-tuning were not started.
