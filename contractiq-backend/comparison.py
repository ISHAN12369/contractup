"""One-to-one clause alignment using exact matches then local dense cosine similarity."""

import math
from collections.abc import Callable

from audit_schemas import AuditResponse, ClauseChange, CompareResponse
from locations import normalized_map


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Incompatible embedding dimensions")
    denominator = math.sqrt(sum(x * x for x in left) * sum(x * x for x in right))
    if not denominator:
        return 0.0
    return sum(x * y for x, y in zip(left, right, strict=True)) / denominator


def compare_audits(before: AuditResponse, after: AuditResponse, embed: Callable[[list[str]], list[list[float]]]) -> CompareResponse:
    old, new = before.clauses, after.clauses
    matched_old: set[int] = set()
    matched_new: set[int] = set()
    unchanged = 0
    for i, first in enumerate(old):
        for j, second in enumerate(new):
            if j not in matched_new and first.type == second.type and normalized_map(first.quoted_text)[0] == normalized_map(second.quoted_text)[0]:
                matched_old.add(i)
                matched_new.add(j)
                unchanged += 1
                break
    remaining_old = [i for i in range(len(old)) if i not in matched_old]
    remaining_new = [j for j in range(len(new)) if j not in matched_new]
    texts = [old[i].quoted_text for i in remaining_old] + [new[j].quoted_text for j in remaining_new]
    vectors = embed(texts) if texts and remaining_old and remaining_new else []
    pairs: list[tuple[float, int, int]] = []
    if vectors:
        if len(vectors) != len(texts):
            raise ValueError("Invalid embedding count")
        for a, i in enumerate(remaining_old):
            for b, j in enumerate(remaining_new):
                if old[i].type != new[j].type:
                    continue
                score = cosine(vectors[a], vectors[len(remaining_old) + b])
                if math.isfinite(score) and score >= 0.72:
                    pairs.append((score, i, j))
    changes: list[ClauseChange] = []
    for score, i, j in sorted(pairs, key=lambda value: (-value[0], value[1], value[2])):
        if i in matched_old or j in matched_new:
            continue
        matched_old.add(i)
        matched_new.add(j)
        changes.append(ClauseChange(
            kind="changed", before=old[i], after=new[j], similarity=round(score, 6),
            risk_delta=new[j].risk.score - old[i].risk.score,
            explanation="Same CUAD type and local cosine similarity above 0.72; inspect both quotations. Alignment is a heuristic, not proof of equivalent meaning.",
        ))
    for i, clause in enumerate(old):
        if i not in matched_old:
            changes.append(ClauseChange(kind="removed", before=clause, after=None, similarity=None, risk_delta=-clause.risk.score, explanation="Extracted only in the earlier version; an extraction miss can look like removal."))
    for j, clause in enumerate(new):
        if j not in matched_new:
            changes.append(ClauseChange(kind="added", before=None, after=clause, similarity=None, risk_delta=clause.risk.score, explanation="Extracted only in the later version; an extraction miss can look like addition."))
    return CompareResponse(
        before_id=before.doc_id, after_id=after.doc_id, changes=changes, unchanged=unchanged,
        overall_risk_delta=(after.overall_risk.score - before.overall_risk.score) if before.overall_risk and after.overall_risk else None,
        warnings=["Comparison covers extracted CUAD passages, not every textual edit.", "Similarity threshold is uncalibrated; Phase 2 must evaluate it.", "A negative risk delta is not proof that a removal or revision is beneficial."],
    )
