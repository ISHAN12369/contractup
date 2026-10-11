# ContractIQ evaluation

This harness measures the existing backend; it does not replace its retrieval or audit implementations. No new packages are required: use Python 3.12 and the exact-pinned backend development requirements. It is a developer workload, not a Render/Vercel request handler.

## Reproduce

With the virtual environment active, from the repository root:

```bash
python -m pip install -r contractiq-backend/requirements-dev.txt
make eval
```

`make eval` verifies/downloads the pinned CUAD archive, then writes `evals/runs/local/results.md` and `results.json`. The default run selects ten CUAD test documents and all answerable categories in those documents, plus all forty golden questions. It uses real local FastEmbed embeddings, Chroma cosine retrieval and ONNX cross-encoding. Initial model downloads require network access. Generator/judge calls are disabled by default, even when a key exists.

Without GNU Make (including this Windows environment), use the equivalent commands:

```powershell
.\.venv\Scripts\python.exe -m evals.prepare
.\.venv\Scripts\python.exe -m evals.run
.\.venv\Scripts\python.exe -m pytest -q evals/tests
.\.venv\Scripts\python.exe -m ruff check evals
.\.venv\Scripts\python.exe -m mypy --config-file evals/pyproject.toml evals --exclude tests
```

A smaller integration run: `python -m evals.run --cuad-limit 3 --questions-per-doc 6`. All length-eligible CUAD test documents: `python -m evals.run --cuad-limit 0 --questions-per-doc 0`. Zero means all, never none. Selection is the ascending SHA-256 of `seed:title`, with seed 42 by default. Questions, when limited, use the same seeded hash of question ID. Selection is fixed before scoring; no tuning is performed against the reported sample.

Use `make eval EVAL_ARGS="--cuad-limit 3 --questions-per-doc 6"` to pass those options through Make. You can override `PYTHON` when the environment is not activated.

## Data and provenance

CUAD is The Atticus Project's expert-annotated contract dataset: Hendrycks et al., *CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review*, NeurIPS 2021. [Official dataset and license](https://www.atticusprojectai.org/cuad/), [repository](https://github.com/The-Atticus-Project/cuad), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

The downloader pins repository revision `67faa0e6023b04fcaae6cc09497ab00e5d63a2a2`, file `data.zip`, SHA-256 `f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a`. Only `test.json` is read. The archive stays in ignored `evals/.cache`; its paths are never extracted or executed. A modified archive or an answer whose exact text does not match its source offset fails validation.

The test split has 102 documents. The deployed 100,000-character document limit and single-context requirement leave 88 eligible; the other 14 are explicitly excluded. The default ten-document sample therefore is **not a full CUAD score**. The JSON records selected IDs, limits, corpus/fixture checksums, Python/package versions, ONNX file hashes, source-code hashes, Git state, retrieval settings and per-question ranks. A run before the delivery commit can legitimately record a dirty working tree; the source hashes identify that run's implementation.

`fixtures/golden.json` contains forty fixed, assistant-authored questions and reference answers across five synthetic contracts: lease, services, software license, employment and consumer subscription. Thirty-five have exact supporting quotes and five are unanswerable. Each context exceeds 4,000 characters and includes an intentionally shared administrative annex to create retrieval competition. These are developer stress fixtures, **not human-expert legal labels or a blind holdout**. The subscription fixture includes an explicitly untrusted instruction-like comment. Reference answers support manual error review; the generation metrics below score source support and responsiveness rather than reference-answer correctness.

CUAD questions with no answer span are excluded from retrieval scoring because they have no relevance denominator. All 41 labels, including absent categories, remain eligible for clause-extraction scoring: an emitted clause of an absent type is a false positive. Retrieval question subsampling never reduces the extraction gold labels for a selected document.

## Configuration comparison

The complete 2-by-3 matrix isolates changes:

| Chunking | Retriever |
| --- | --- |
| recursive 1000/150 | dense top four (baseline) |
| recursive 1000/150 | BM25 + dense RRF |
| recursive 1000/150 | BM25 + dense RRF + ONNX cross-encoder |
| heading-aware with recursive fallback | dense top four |
| heading-aware with recursive fallback | BM25 + dense RRF |
| heading-aware with recursive fallback | BM25 + dense RRF + ONNX cross-encoder |

All use the production `split_pages`, `DocumentStore`, `ChromaIndex` and `Retriever`, RRF constant 60 and twelve hybrid candidates. One embedding model and one reranker are retained; documents are indexed sequentially and deleted after each document/chunker. Temporary indexes live beneath the specified output directory. Different retrieval strategies share the same indexed document. Full text is not cropped to gold spans or used as a generated answer.

## Metric definitions

Offsets are half-open Python Unicode code-point intervals. A retrieved chunk is relevant if it covers at least 50% of any reference span. The fixed threshold is declared before the run.

- **Hit@4:** fraction of answerable questions with at least one relevant chunk in the first four.
- **MRR@4:** mean reciprocal rank of the first relevant chunk within four; zero if absent. This is truncated MRR, not full-ranking MRR.
- **Span Recall@4:** fraction of reference spans covered at least 50% by the union of the first four chunks, then macro-averaged across questions. Overlapping chunks cannot double-count characters. Two partial chunks can jointly recover a span even if neither is individually relevant; in that case recall can be positive while Hit@4 is zero.
- **Clause extraction micro precision/recall/F1:** same CUAD label and character-span intersection-over-union at least 0.5; maximum-cardinality one-to-one matching. Repeated predictions cannot inflate true positives. This location-aware metric is **not interchangeable with the [official CUAD token-set overlap scorer](https://github.com/The-Atticus-Project/cuad/blob/67faa0e6023b04fcaae6cc09497ab00e5d63a2a2/evaluate.py)**. A successful empty extraction counts as false negatives; a failed/unrun extraction has no fabricated score.

Gold labels/offsets and ranked offsets remain available in each retrieval result for inspection. Results are separate by dataset and configuration. A failed query is excluded from means and counted explicitly; a run with errors exits nonzero and says `completed_with_errors`. Never compare partial runs as though they had identical coverage. Interrupted runs retain `running` status and should not be presented as completed metrics. Undefined denominators and unrun metrics are JSON `null`.

The audit graph extracts over all chunks, independent of the retriever. Consequently clause extraction runs once per document/chunker, not three times with identical inputs. It includes every annotated CUAD span for those documents, including spans longer than the extractor's quotation limit; no difficult labels are silently removed. This can expose a real mismatch between annotation span size and application extraction granularity.

## Generation and judge evaluation

Configure `GROQ_API_KEY` locally in the environment or `contractiq-backend/.env`. Do not commit or paste credentials. Then explicitly enable provider requests:

```bash
python -m evals.run --online --cuad-limit 3 --questions-per-doc 6 --output evals/runs/online
```

This sends detected-PII-redacted questions, contract evidence and generated answers to Groq. Detection can miss entities. It can involve many calls and consume provider quota; the full default matrix includes one answer and two judge steps per question/configuration, plus audits. Errors, rate limits and timeouts remain visible. `EVAL_JUDGE_MODEL` selects another compatible Groq model; by default generator and judge use the same model, a disclosed source of correlated/self-evaluation bias.

For the fixed, bounded live pilot used in this delivery:

```powershell
.\.venv\Scripts\python.exe -m evals.pilot --env-file contractiq-backend/.env --output evals/runs/provider-pilot
```

This explicitly opts into provider calls. It selects one seeded CUAD document/question and lease questions 2, 5 and 8 from the existing golden fixture: 24 question/configuration rows and two document audits. The optional explicit `--env-file` overrides stale process environment values; ordinary loading leaves environment values in priority. Both clients share a three-second minimum request interval, including schema retries. This limits request frequency but does not guarantee token-quota compliance. The measured pilot hit HTTP 429 responses despite pacing; [the verification report](../docs/phase-2-verification.md) preserves incomplete coverage and the separate diagnostic audit. See [Groq rate-limit definitions](https://console.groq.com/docs/rate-limits). Do not treat one surviving generation score as a configuration comparison.

`judge.py` implements a versioned alternative to installing RAGAS:

1. Decompose the generated answer into atomic factual claims, preserving qualifiers and exceptions. Exclude citation markers, disclaimers and simple abstentions.
2. Judge every claim against **all excerpts actually retrieved by the application's answer call**. A supported verdict must include a verbatim source quote, which is checked locally. Missing or duplicate claim verdicts fail validation. Faithfulness is supported claims divided by total claims; claimless answers have undefined faithfulness.
3. Independently judge answer relevance on an explicit responsiveness rubric: 0 irrelevant/evasive, 1 partially addresses the request, 2 directly addresses it or explains missing evidence; divide by two. This is not a correctness score and is not RAGAS's reverse-question embedding metric.

The claim-support definition follows the general approach in [RAGAS faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/). See [RAGAS response relevancy](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/) for the deliberately different reference metric. Our values must not be compared numerically with published RAGAS results. The rubric is `claim-support-and-directness-v1`; redacted claims, verdicts and reasons are saved for manual audit. LLM judges can miss or misjudge claims even when quotes are valid. These scores are not expert assessments.

Abstention accuracy separately compares the judge's abstention label against known question answerability. This is especially useful for the five unanswerable golden questions. Faithfulness means display a separate denominator for claim-bearing answers in JSON.

## Saved extraction predictions

No API key is needed to score existing clause predictions. Supply a JSON object with `documents`, each containing `id`, `text_sha256` (the exact canonical context hash) and `predictions`, a list of `{ "start": 0, "end": 8, "label": "Document Name" }` objects. These numbers illustrate the schema, not a prediction for an actual CUAD document. An explicit empty list means extraction returned no clauses; a missing document means not run. Unknown IDs/labels, stale text hashes and out-of-bounds spans are rejected.

```bash
python -m evals.score_predictions --predictions evals/runs/predictions.json --output evals/runs/extraction-scores.json
```

Keep `--cuad-limit` and `--seed` aligned with the generating run. The scorer records the predictions checksum and uses the same matching function as live audits.

## Private samples and limits

Use golden-format local cases through `--private evals/private/sample.json --output evals/runs/private`. The JSON schema is demonstrated by the committed synthetic fixtures. This adds local sample retrieval to the standard matrix. Private mode rejects `--online` and output outside ignored `evals/runs/`. The user's PDF and its derived fixtures are not committed or added to CUAD. Do not describe locally authored reference answers as expert legal annotations.

The harness does not fine-tune a model, infer legal correctness, manufacture generation metrics, estimate latency/cost, or establish free-tier memory fitness. Synthetic fixtures are easier and more repetitive than real documents. CUAD is commercial-contract focused and cannot establish coverage of consumer offers or Indian tenancies. The bounded sample, length filter and threshold choice constrain every reported result. Any future tuning should use a separate development split and preserve a final untouched test set.
