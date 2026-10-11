import json

import pytest
from evals.judge import Claims, Judgment, score_judgment
from evals.report import summarize, write_report


def test_judge_requires_complete_claims_and_verbatim_evidence():
    claims = Claims(claims=["Rent is ten.", "Deposit is five."], abstains=False)
    judgment = Judgment(verdicts=[
        {"claim_index": 0, "supported": True, "evidence_quote": "Rent is ten.", "reason": "Direct evidence"},
        {"claim_index": 1, "supported": False, "evidence_quote": "", "reason": "Absent"},
    ], relevance=1, relevance_reason="Partial")
    score = score_judgment(claims, judgment, ["Rent is ten."])
    assert score["faithfulness"] == 0.5 and score["answer_relevance"] == 0.5
    with pytest.raises(ValueError, match="verbatim"):
        score_judgment(claims, judgment, ["No evidence"])
    with pytest.raises(ValueError, match="exactly once"):
        score_judgment(claims, judgment.model_copy(update={"verdicts": judgment.verdicts[:1]}), ["Rent is ten."])
    empty = score_judgment(Claims(claims=[], abstains=True), Judgment(verdicts=[], relevance=2, relevance_reason="Missing evidence"), [])
    assert empty["faithfulness"] is None


def test_report_keeps_not_run_distinct_from_zero(tmp_path):
    report = {"status": "completed", "rows": [{"source": "golden", "config": "recursive+dense",
        "unanswerable": False, "retrieval": {"hit_at_4": 0, "mrr_at_4": 0, "span_recall_at_4": 0},
        "generation": {"status": "not_run"}}],
        "audits": [{"chunker": "recursive", "status": "not_run"}]}
    write_report(tmp_path, report)
    saved = json.loads((tmp_path / "results.json").read_text())
    assert saved["summary"]["retrieval"][0]["hit_at_4"] == 0
    assert saved["summary"]["generation"][0]["faithfulness"] is None
    assert saved["summary"]["extraction"][0]["f1"] is None
    assert "not run / undefined" in (tmp_path / "results.md").read_text()


def test_empty_predictions_are_measured_false_negatives_not_not_run():
    result = summarize([], [{"chunker": "clause", "status": "ok", "counts": {"tp": 0, "fp": 0, "fn": 3}}])
    assert result["extraction"][0]["f1"] == 0
    assert result["extraction"][0]["measured"] == 1
