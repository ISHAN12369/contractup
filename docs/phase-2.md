# Phase 2 — Evaluation

## Delivered plan

Add `evals/data.py`, `prepare.py`, `metrics.py`, `judge.py`, `run.py`, `report.py` and `score_predictions.py`; forty fixed synthetic questions in `evals/fixtures/golden.json`; unit/integration tests and evaluation lint/type configuration; root Make targets and CI checks. No new runtime dependencies: all imports use the pinned Phase 1 backend environment. The Render/Vercel application and production model settings are unchanged.

The main risks are benchmark selection bias, chunk-dependent relevance definitions, imperfect model judges and leaking private samples into published fixtures. The implementation pins CUAD and selected IDs, preserves exact gold spans, discloses scoring definitions and missing denominators, makes provider use opt-in, and keeps the supplied PDF and derived cases ignored/local.

## Run and inspect

See [the evaluation guide](../evals/README.md) for exact commands, licensing, configuration controls, metric formulae, input schemas and limits. `make eval` performs real local retrieval and writes Markdown/JSON; Windows equivalents use `python -m evals.prepare` followed by `python -m evals.run`. Generation/extraction require `--online` and a locally configured provider, or existing extraction predictions for the saved scorer.

The committed measured retrieval report is [results.md](../evals/results/phase-2-retrieval/results.md), with complete machine-readable evidence in [results.json](../evals/results/phase-2-retrieval/results.json). [Verification](phase-2-verification.md) records tests, the incomplete live pilot and a separate measured extraction example. `evals/pilot.py` provides the bounded live reproduction command. Do not infer a generation or extraction score from an unrun cell. Tests use mocks to validate plumbing, but those outputs are not benchmark results.

## Manual verification checklist

- [ ] Reproduce the pinned dataset checksum and selected document IDs on another machine.
- [x] Inspect failed retrieval questions in JSON by locating their gold/ranked offsets in CUAD `test.json`; include examples where a more complex configuration loses.
- [ ] Review the forty authored references and unanswerable labels; add independent human annotations before making a quality claim.
- [x] Configure a real provider locally, run the fixed live pilot and inspect its surviving claim judgments. Rate-limit failures remain explicit; complete generation coverage is still pending.
- [ ] Use a different judge model and human spot-check to assess same-model judge bias.
- [x] Score saved predictions only against matching canonical-text hashes; test empty predictions versus missing runs.
- [ ] Measure a full eligible CUAD run separately from the bounded report; document long-contract exclusions and any failures.
- [x] Keep the user's sample PDF and derived fixtures outside commits, public artifacts and provider requests.

Suggested commit: `feat: add reproducible CUAD and golden-set evaluation harness`.

Phase 3 infrastructure and optional classifier fine-tuning are not included. Legal content and evaluation outputs are informational only, not legal advice.
