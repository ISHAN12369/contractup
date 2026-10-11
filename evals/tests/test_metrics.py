import pytest
from evals.data import Span
from evals.metrics import aggregate_retrieval, coverage, extraction, prf, retrieval


def test_retrieval_rank_denominators_and_absent_answers():
    gold = [Span(10, 20), Span(80, 100)]
    hits = [Span(100, 110), Span(0, 20), Span(80, 90)]
    assert retrieval(gold, hits) == {"hit_at_4": 1, "mrr_at_4": 0.5, "span_recall_at_4": 1}
    assert retrieval(gold, []) == {"hit_at_4": 0, "mrr_at_4": 0, "span_recall_at_4": 0}
    assert retrieval([], hits) is None
    assert retrieval([Span(10, 20)], [Span(0, 5)] * 4 + [Span(10, 20)])["hit_at_4"] == 0
    with pytest.raises(ValueError):
        retrieval(gold, hits, k=1)


def test_overlapping_chunks_do_not_double_count_recall():
    gold = Span(0, 100)
    assert coverage(gold, [Span(0, 30), Span(0, 30)]) == 0.3
    assert coverage(gold, [Span(0, 30), Span(20, 50)]) == 0.5
    assert retrieval([gold], [Span(0, 30), Span(20, 50)])["span_recall_at_4"] == 1
    assert retrieval([gold], [Span(0, 30), Span(20, 50)])["hit_at_4"] == 0
    with pytest.raises(ValueError):
        Span(4, 4)


def test_extraction_is_label_sensitive_and_one_to_one():
    gold = [Span(0, 10, "a"), Span(20, 30, "a")]
    assert extraction(gold, [Span(0, 10, "a"), Span(0, 10, "a"), Span(20, 30, "b")]) == {"tp": 1, "fp": 2, "fn": 1}
    assert extraction([], [Span(0, 10, "a")]) == {"tp": 0, "fp": 1, "fn": 0}
    assert extraction(gold, []) == {"tp": 0, "fp": 0, "fn": 2}


def test_maximum_matching_reassigns_ambiguous_pairs():
    gold = [Span(0, 10, "a"), Span(5, 15, "a")]
    predicted = [Span(0, 15, "a"), Span(0, 10, "a")]
    assert extraction(gold, predicted) == {"tp": 2, "fp": 0, "fn": 0}
    assert prf({"tp": 2, "fp": 1, "fn": 2})["f1"] == pytest.approx(4 / 7)
    assert prf({"tp": 0, "fp": 0, "fn": 0})["f1"] is None
    assert prf({"tp": 0, "fp": 0, "fn": 2})["f1"] == 0


def test_failures_and_impossible_questions_are_visible_not_fabricated():
    rows = [{"unanswerable": False, "retrieval": {"hit_at_4": 1, "mrr_at_4": 0.5, "span_recall_at_4": 0.5}},
            {"unanswerable": False, "retrieval": None}, {"unanswerable": True, "retrieval": None}]
    result = aggregate_retrieval(rows)
    assert result["measured"] == 1 and result["failed"] == 1 and result["unanswerable_excluded"] == 1
    assert result["hit_at_4"] == 1
    assert aggregate_retrieval([])["hit_at_4"] is None
