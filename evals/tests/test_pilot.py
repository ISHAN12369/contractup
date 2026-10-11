from evals import ROOT
from evals.pilot import RequestPacer, golden_pilot


def test_pilot_has_fixed_conditional_and_unanswerable_questions():
    documents = golden_pilot(ROOT / "evals/fixtures/golden.json")
    assert len(documents) == 1
    assert [q.id for q in documents[0].questions] == ["golden-lease:2", "golden-lease:5", "golden-lease:8"]
    assert [q.unanswerable for q in documents[0].questions] == [False, False, True]
    assert len(documents[0].text) > 4000


def test_request_pacer_spaces_requests_but_does_not_delay_a_slow_response(monkeypatch):
    clock = iter([10.0, 11.0, 13.0, 20.0, 20.0])
    sleeps = []
    monkeypatch.setattr("evals.pilot.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("evals.pilot.time.sleep", sleeps.append)
    pacer = RequestPacer()
    for _ in range(3):
        pacer(None)
    assert sleeps == [2.0, 0.0]
