"""Versioned review-priority rubric. It does not predict enforceability or loss."""

import re

from audit_schemas import AuditedClause, ClauseType, Redline, Risk

RUBRIC = "review-priority-v1"
HIGH = {
    ClauseType.UNCAPPED_LIABILITY: "The extracted provision describes uncapped exposure; negotiate a clear allocation and cap.",
    ClauseType.NON_COMPETE: "The extracted restriction may constrain future activity; review scope, duration and exceptions.",
    ClauseType.PERPETUAL_LICENSE: "An irrevocable or perpetual grant may outlast the relationship; review scope and exit rights.",
    ClauseType.NOT_TO_SUE: "A covenant not to sue may restrict remedies; review the claims and exceptions it covers.",
}
MEDIUM = {
    ClauseType.TERMINATION, ClauseType.ANTI_ASSIGNMENT, ClauseType.LIQUIDATED_DAMAGES,
    ClauseType.EXCLUSIVITY, ClauseType.MINIMUM_COMMITMENT, ClauseType.PRICE,
    ClauseType.CHANGE_OF_CONTROL, ClauseType.RENEWAL_TERM, ClauseType.NOTICE_PERIOD,
    ClauseType.IP_ASSIGNMENT, ClauseType.NON_TRANSFERABLE, ClauseType.POST_TERMINATION,
    ClauseType.NO_SOLICIT_CUSTOMERS, ClauseType.NO_SOLICIT_EMPLOYEES,
}


def assess(kind: ClauseType, quote: str) -> Risk:
    # Conservative lexical triggers; negated phrases must not trigger on 'not unlimited'.
    if re.search(r"(?<!not )(?<!no )\b(?:sole discretion|without notice|non[- ]refundable)\b", quote, re.I):
        return Risk(level="high", score=80, why="The quotation contains a unilateral or restrictive trigger (sole discretion, without notice or non-refundable); review its context and negotiate protections.", rubric_id=RUBRIC + ":restrictive-wording")
    if kind in HIGH:
        return Risk(level="high", score=80, why=HIGH[kind], rubric_id=RUBRIC + ":high-type")
    if kind in MEDIUM:
        return Risk(level="medium", score=50, why="This clause type allocates material commercial control or continuing obligations; check reciprocity, scope and exit terms.", rubric_id=RUBRIC + ":medium-type")
    return Risk(level="low", score=20, why="No elevated trigger in this limited rubric; low priority does not mean the provision is safe or complete.", rubric_id=RUBRIC + ":baseline")


def overall(clauses: list[AuditedClause]) -> Risk | None:
    if not clauses:
        return None
    score = max(item.risk.score for item in clauses)
    return Risk(
        level="high" if score >= 70 else "medium" if score >= 40 else "low", score=score,
        why="Maximum priority among extracted, source-located clauses; counts and coverage must be reviewed separately. Missing clauses never count as safe.",
        rubric_id=RUBRIC + ":maximum",
    )


def suggest(kind: ClauseType, original: str, risk: Risk) -> Redline | None:
    if risk.level != "high":
        return None
    proposals = {
        ClauseType.UNCAPPED_LIABILITY: "Each party's aggregate liability under this provision is limited to the fees paid or payable in the preceding twelve months, except for fraud, wilful misconduct and liability that applicable law does not permit the parties to limit.",
        ClauseType.NON_COMPETE: "Any restriction is limited to activities directly involving the other party's confidential information during the agreement. It does not restrict independent work, general skills or activities unrelated to that information.",
        ClauseType.PERPETUAL_LICENSE: "The licence applies only to the agreed purpose during the agreement. Continuing use after termination requires a separate written agreement, except for copies retained solely to meet legal recordkeeping duties.",
        ClauseType.NOT_TO_SUE: "Any release is limited to specifically identified claims known at the date of signing. It does not waive claims arising from future breach, fraud or wilful misconduct, or remedies that applicable law does not permit the parties to waive.",
    }
    return Redline(
        original=original,
        suggested=proposals.get(kind, "Any exercise of a right under this provision requires reasonable written notice stating the grounds and an opportunity to respond. Payments may be retained only for documented amounts properly due under the agreement; disputed deductions remain subject to the agreed dispute process."),
        rationale="Illustrative replacement for negotiation: narrows scope and adds an express protection. It changes the commercial bargain and needs review for the parties, surrounding clauses and governing law before use.",
    )
