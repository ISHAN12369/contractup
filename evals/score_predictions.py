"""Score saved CUAD clause spans without a provider; absent predictions are not zeroes."""
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from evals.data import Document, Span, digest, label_name, load_cuad
from evals.metrics import extraction, prf


def score_saved(documents: list[Document], payload: dict[str, Any]) -> dict[str, Any]:
    supplied = {item["id"]: item for item in payload["documents"]}
    if len(supplied) != len(payload["documents"]):
        raise ValueError("Duplicate prediction document ID")
    known = {doc.id for doc in documents}
    if set(supplied) - known:
        raise ValueError("Predictions include documents outside the declared evaluation subset")
    rows: list[dict[str, Any]] = []
    for doc in documents:
        if doc.id not in supplied:
            rows.append({"document": doc.id, "status": "not_run"})
            continue
        item = supplied[doc.id]
        if item["text_sha256"] != hashlib.sha256(doc.text.encode()).hexdigest():
            raise ValueError("Prediction offsets belong to a different document text")
        predictions = [Span(p["start"], p["end"], label_name(p["label"])) for p in item["predictions"]]
        if any(span.end > len(doc.text) for span in predictions):
            raise ValueError("Prediction outside source text")
        if doc.clauses is None:
            raise ValueError("Exhaustive clause labels are required")
        rows.append({"document": doc.id, "status": "ok", "counts": extraction(doc.clauses, predictions)})
    measured = [row for row in rows if row["status"] == "ok"]
    counts = {name: sum(row["counts"][name] for row in measured) for name in ("tp", "fp", "fn")}
    return {"method": "label-and-character-IoU-0.5-one-to-one", "documents": rows,
            "measured": len(measured), "not_run": len(rows) - len(measured),
            "micro": prf(counts) if measured else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--cuad", type=Path, default=Path("evals/.cache/cuad-data.zip"))
    parser.add_argument("--cuad-limit", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("evals/runs/saved-extraction.json"))
    args = parser.parse_args()
    if args.cuad_limit < 0:
        parser.error("--cuad-limit must be nonnegative")
    documents, manifest = load_cuad(args.cuad, limit=args.cuad_limit, questions_per_doc=0, seed=args.seed)
    result = score_saved(documents, json.loads(args.predictions.read_text(encoding="utf-8")))
    result.update(dataset=manifest, predictions_sha256=digest(args.predictions))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Scored {result['measured']} documents; {result['not_run']} not run. Output: {args.output}")
