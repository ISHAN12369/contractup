"""Reports keep failures, excluded denominators and unavailable metrics visible."""
import json
from pathlib import Path
from typing import Any

from evals.metrics import aggregate_retrieval, mean, prf


def summarize(rows: list[dict[str, Any]], audits: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval, generation, extraction = [], [], []
    for source in sorted({r["source"] for r in rows}):
        for config in sorted({r["config"] for r in rows}):
            selected = [r for r in rows if r["source"] == source and r["config"] == config]
            retrieval.append({"source": source, "config": config, **aggregate_retrieval(selected)})
            scored = [r for r in selected if r.get("generation", {}).get("status") == "ok"]
            scores = [r["generation"]["scores"] for r in scored]
            generation.append({"source": source, "config": config, "measured": len(scores),
                               "total": len(selected), "failed": sum(r.get("generation", {}).get("status") == "failed" for r in selected),
                               "not_run": sum(r.get("generation", {}).get("status") == "not_run" for r in selected),
                               "faithfulness": mean([s["faithfulness"] for s in scores if s["faithfulness"] is not None]),
                               "faithfulness_denominator": sum(s["faithfulness"] is not None for s in scores),
                               "answer_relevance": mean([s["answer_relevance"] for s in scores]),
                               "abstention_accuracy": mean([float(r["generation"]["scores"]["abstains"] == r["unanswerable"]) for r in scored])})
    for chunker in sorted({a["chunker"] for a in audits}):
        selected = [a for a in audits if a["chunker"] == chunker]
        measured = [a for a in selected if a["status"] == "ok"]
        counts = {key: sum(a["counts"][key] for a in measured) for key in ("tp", "fp", "fn")}
        extraction_scores = prf(counts) if measured else {"precision": None, "recall": None, "f1": None}
        extraction.append({"source": "cuad", "chunker": chunker, "documents": len(selected),
                           "measured": len(measured), "failed": sum(a["status"] == "failed" for a in selected),
                           "not_run": sum(a["status"] == "not_run" for a in selected), **extraction_scores})
    return {"retrieval": retrieval, "generation": generation, "extraction": extraction}


def number(value: object) -> str:
    return "not run / undefined" if value is None else f"{float(value):.4f}"  # type: ignore[arg-type]


def write_report(output: Path, report: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    report["summary"] = summarize(report["rows"], report["audits"])
    # Replace files atomically; allow_nan=False rejects non-finite fabricated results.
    temporary = output / "results.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(output / "results.json")
    lines = ["# ContractIQ evaluation results", "", f"Run status: **{report['status']}**.", "",
             "These are bounded development-set results, not legal conclusions or a full CUAD benchmark.", "",
             "## Retrieval", "", "Relevance: at least 50% of a gold span covered. Recall uses the union of top-four intervals.", "",
             "| Dataset | Configuration | Measured / answerable | Failures | Hit@4 | MRR@4 | Span Recall@4 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in report["summary"]["retrieval"]:
        lines.append(f"| {row['source']} | {row['config']} | {row['measured']}/{row['answerable']} | {row['failed']} | {number(row['hit_at_4'])} | {number(row['mrr_at_4'])} | {number(row['span_recall_at_4'])} |")
    lines += ["", "Unanswerable questions are excluded from retrieval denominators, not counted as failures or successes.", "",
              "## Generation", "", "Claim-support faithfulness and 0/0.5/1 directness rubric; not numerically interchangeable with RAGAS.", "",
              "| Dataset | Configuration | Scored / total | Failed | Not run | Faithfulness | Answer relevance | Abstention accuracy |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in report["summary"]["generation"]:
        lines.append(f"| {row['source']} | {row['config']} | {row['measured']}/{row['total']} | {row['failed']} | {row['not_run']} | {number(row['faithfulness'])} | {number(row['answer_relevance'])} | {number(row['abstention_accuracy'])} |")
    lines += ["", "## CUAD clause extraction", "", "Micro precision/recall/F1: same label and character-span IoU >= 0.5 with one-to-one matching. Not the official CUAD scorer.", "",
              "| Chunker | Scored / documents | Failed | Not run | Precision | Recall | F1 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in report["summary"]["extraction"]:
        lines.append(f"| {row['chunker']} | {row['measured']}/{row['documents']} | {row['failed']} | {row['not_run']} | {number(row['precision'])} | {number(row['recall'])} | {number(row['f1'])} |")
    lines += ["", "Unavailable or undefined values are null in JSON. Failures are excluded from metric means and displayed explicitly; compare only complete runs.",
              "The extraction workflow does not use retrieval: it is run once per document/chunker, not three times per retrieval strategy.", "",
              "See results.json for dataset hashes, exact selected IDs, configuration, per-question ranks/offsets, errors and runtime/model provenance.", "",
              "No latency percentile, cost, full-corpus, statistical-significance or production-memory claim is made.", ""]
    (output / "results.md").write_text("\n".join(lines), encoding="utf-8")
