import hashlib
import json
import zipfile

import pytest
from evals import ROOT
from evals.data import label_name, load_cuad, load_golden
from evals.prepare import prepare


def archive(tmp_path, monkeypatch, answer_start=4):
    path = tmp_path / "cuad.zip"
    data = {"data": [{"title": f"doc-{i}", "paragraphs": [{"context": "The rent is due.", "qas": [
        {"id": f"doc-{i}__Document Name", "question": "Name?", "is_impossible": False,
         "answers": [{"text": "rent", "answer_start": answer_start}]},
        {"id": f"doc-{i}__Insurance", "question": "Insurance?", "is_impossible": True, "answers": []},
    ]}]} for i in range(3)]}
    with zipfile.ZipFile(path, "w") as target:
        target.writestr("test.json", json.dumps(data))
    monkeypatch.setattr("evals.data.CUAD_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    return path


def test_cuad_uses_exact_offsets_and_reproducible_test_subset(tmp_path, monkeypatch):
    path = archive(tmp_path, monkeypatch)
    first, manifest = load_cuad(path, limit=2, questions_per_doc=1)
    second, _ = load_cuad(path, limit=2, questions_per_doc=1)
    assert [d.id for d in first] == [d.id for d in second]
    assert manifest["split"] == "test" and manifest["test_documents"] == 3
    assert first[0].text[first[0].clauses[0].start:first[0].clauses[0].end] == "rent"
    assert label_name("Notice Period to Terminate Renewal") == "Notice Period To Terminate Renewal"
    with pytest.raises(ValueError, match="Unknown CUAD"):
        label_name("invented")


def test_invalid_cuad_span_or_archive_is_rejected(tmp_path, monkeypatch):
    path = archive(tmp_path, monkeypatch, answer_start=0)
    with pytest.raises(ValueError, match="Invalid CUAD source"):
        load_cuad(path)
    path.write_bytes(b"not the dataset")
    with pytest.raises(ValueError, match="checksum"):
        load_cuad(path)
    with pytest.raises(ValueError, match="checksum"):
        prepare(path)


def test_all_40_authored_questions_have_valid_gold_evidence():
    documents = load_golden(ROOT / "evals/fixtures/golden.json")
    assert sum(len(d.questions) for d in documents) == 40
    assert sum(q.unanswerable for d in documents for q in d.questions) == 5
    assert all(len(d.text) > 4000 for d in documents)
    assert len({q.id for d in documents for q in d.questions}) == 40


def test_golden_repeated_quote_unicode_and_corruption(tmp_path):
    path = tmp_path / "golden.json"
    payload = {"documents": [{"id": "x", "pages": ["😀 rent then rent"], "questions": [
        {"id": "q", "question": "Which?", "answer": "rent", "quotes": [{"text": "rent", "occurrence": 1}]}]}]}
    path.write_text(json.dumps(payload))
    doc = load_golden(path)[0]
    assert doc.questions[0].spans[0].start == 12
    payload["documents"][0]["questions"][0]["quotes"][0]["text"] = "absent"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="absent"):
        load_golden(path)
