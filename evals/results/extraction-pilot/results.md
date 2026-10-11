# Separate live extraction pilot

One CUAD document, clause chunking, `openai/gpt-oss-20b`; informational only, not legal advice.

| Documents scored | Gold spans | Predictions | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 7 | 1 | 0 | 1 | 7 | 0.0 | 0.0 | 0.0 |

Computed by `evals.score_predictions` using equal labels and character-span IoU >= 0.5 with one-to-one matching. The predicted Effective Date passage is much broader than the gold date interval and does not match at this threshold. This is not the official CUAD scorer or a full-corpus result.

See [results.json](results.json), [predictions.json](predictions.json), [audit.json](audit.json), [provenance.json](provenance.json), and [verification](../../../docs/phase-2-verification.md). This separate successful audit does not replace the two failed audits in the matrix pilot.
