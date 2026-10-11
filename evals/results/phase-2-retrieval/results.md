# ContractIQ evaluation results

Run status: **completed**.

These are bounded development-set results, not legal conclusions or a full CUAD benchmark.

## Retrieval

Relevance: at least 50% of a gold span covered. Recall uses the union of top-four intervals.

| Dataset | Configuration | Measured / answerable | Failures | Hit@4 | MRR@4 | Span Recall@4 |
| --- | --- | --- | --- | --- | --- | --- |
| cuad | clause+dense | 94/94 | 0 | 0.4574 | 0.3156 | 0.3936 |
| cuad | clause+hybrid | 94/94 | 0 | 0.5532 | 0.3918 | 0.4846 |
| cuad | clause+hybrid_rerank | 94/94 | 0 | 0.5213 | 0.3723 | 0.4449 |
| cuad | recursive+dense | 94/94 | 0 | 0.4255 | 0.3067 | 0.3697 |
| cuad | recursive+hybrid | 94/94 | 0 | 0.5532 | 0.3936 | 0.4766 |
| cuad | recursive+hybrid_rerank | 94/94 | 0 | 0.5106 | 0.3794 | 0.4328 |
| golden | clause+dense | 35/35 | 0 | 1.0000 | 0.9238 | 1.0000 |
| golden | clause+hybrid | 35/35 | 0 | 0.8286 | 0.7714 | 0.8286 |
| golden | clause+hybrid_rerank | 35/35 | 0 | 1.0000 | 1.0000 | 1.0000 |
| golden | recursive+dense | 35/35 | 0 | 0.9714 | 0.8262 | 0.9714 |
| golden | recursive+hybrid | 35/35 | 0 | 0.9714 | 0.8143 | 0.9714 |
| golden | recursive+hybrid_rerank | 35/35 | 0 | 1.0000 | 0.9810 | 1.0000 |

Unanswerable questions are excluded from retrieval denominators, not counted as failures or successes.

## Generation

Claim-support faithfulness and 0/0.5/1 directness rubric; not numerically interchangeable with RAGAS.

| Dataset | Configuration | Scored / total | Failed | Not run | Faithfulness | Answer relevance | Abstention accuracy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cuad | clause+dense | 0/94 | 0 | 94 | not run / undefined | not run / undefined | not run / undefined |
| cuad | clause+hybrid | 0/94 | 0 | 94 | not run / undefined | not run / undefined | not run / undefined |
| cuad | clause+hybrid_rerank | 0/94 | 0 | 94 | not run / undefined | not run / undefined | not run / undefined |
| cuad | recursive+dense | 0/94 | 0 | 94 | not run / undefined | not run / undefined | not run / undefined |
| cuad | recursive+hybrid | 0/94 | 0 | 94 | not run / undefined | not run / undefined | not run / undefined |
| cuad | recursive+hybrid_rerank | 0/94 | 0 | 94 | not run / undefined | not run / undefined | not run / undefined |
| golden | clause+dense | 0/40 | 0 | 40 | not run / undefined | not run / undefined | not run / undefined |
| golden | clause+hybrid | 0/40 | 0 | 40 | not run / undefined | not run / undefined | not run / undefined |
| golden | clause+hybrid_rerank | 0/40 | 0 | 40 | not run / undefined | not run / undefined | not run / undefined |
| golden | recursive+dense | 0/40 | 0 | 40 | not run / undefined | not run / undefined | not run / undefined |
| golden | recursive+hybrid | 0/40 | 0 | 40 | not run / undefined | not run / undefined | not run / undefined |
| golden | recursive+hybrid_rerank | 0/40 | 0 | 40 | not run / undefined | not run / undefined | not run / undefined |

## CUAD clause extraction

Micro precision/recall/F1: same label and character-span IoU >= 0.5 with one-to-one matching. Not the official CUAD scorer.

| Chunker | Scored / documents | Failed | Not run | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| clause | 0/10 | 0 | 10 | not run / undefined | not run / undefined | not run / undefined |
| recursive | 0/10 | 0 | 10 | not run / undefined | not run / undefined | not run / undefined |

Unavailable or undefined values are null in JSON. Failures are excluded from metric means and displayed explicitly; compare only complete runs.
The extraction workflow does not use retrieval: it is run once per document/chunker, not three times per retrieval strategy.

See results.json for dataset hashes, exact selected IDs, configuration, per-question ranks/offsets, errors and runtime/model provenance.

No latency percentile, cost, full-corpus, statistical-significance or production-memory claim is made.
