"""Transparent metrics; undefined denominators produce null, never invented zeroes."""
from collections.abc import Sequence
from typing import Any

from evals.data import Span


def coverage(gold: Span, retrieved: Sequence[Span]) -> float:
    intervals = sorted((max(gold.start, hit.start), min(gold.end, hit.end)) for hit in retrieved
                       if hit.start < gold.end and hit.end > gold.start)
    covered, last = 0, gold.start
    for start, end in intervals:
        covered += max(0, end - max(start, last))
        last = max(last, end)
    return covered / (gold.end - gold.start)


def retrieval(gold: list[Span], ranked: list[Span], k: int = 4, threshold: float = 0.5) -> dict[str, float] | None:
    if k != 4 or not 0 < threshold <= 1:
        raise ValueError("This benchmark fixes k=4 and requires a valid coverage threshold")
    if not gold:
        return None  # Unanswerable questions have no relevant span denominator.
    selected = ranked[:k]
    ranks = [i for i, span in enumerate(selected, 1) if any(coverage(g, [span]) >= threshold for g in gold)]
    return {"hit_at_4": float(bool(ranks)), "mrr_at_4": 1 / ranks[0] if ranks else 0.0,
            "span_recall_at_4": sum(coverage(g, selected) >= threshold for g in gold) / len(gold)}


def iou(left: Span, right: Span) -> float:
    intersection = max(0, min(left.end, right.end) - max(left.start, right.start))
    return intersection / (max(left.end, right.end) - min(left.start, right.start))


def extraction(gold: list[Span], predicted: list[Span], threshold: float = 0.5) -> dict[str, int]:
    # Maximum-cardinality bipartite matching prevents duplicates inflating recall.
    matches: dict[int, int] = {}

    def augment(index: int, visited: set[int]) -> bool:
        for target, reference in enumerate(gold):
            if target in visited or predicted[index].label != reference.label or iou(predicted[index], reference) < threshold:
                continue
            visited.add(target)
            if target not in matches or augment(matches[target], visited):
                matches[target] = index
                return True
        return False

    for index in range(len(predicted)):
        augment(index, set())
    tp = len(matches)
    return {"tp": tp, "fp": len(predicted) - tp, "fn": len(gold) - tp}


def prf(counts: dict[str, int]) -> dict[str, float | int | None]:
    tp, fp, fn = (counts[name] for name in ("tp", "fp", "fn"))
    return {**counts, "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None}


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate_retrieval(rows: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [r for r in rows if not r["unanswerable"]]
    measured = [r for r in answerable if r.get("retrieval") is not None]
    return {"questions": len(rows), "answerable": len(answerable), "measured": len(measured),
            "failed": len(answerable) - len(measured), "unanswerable_excluded": len(rows) - len(answerable),
            **{name: mean([r["retrieval"][name] for r in measured])
               for name in ("hit_at_4", "mrr_at_4", "span_recall_at_4")}}
