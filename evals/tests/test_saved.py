import hashlib

import pytest
from evals.data import Document, Span, page_texts
from evals.score_predictions import score_saved


def test_saved_predictions_require_text_identity_and_distinguish_empty_from_missing():
    doc = Document("a", "cuad", page_texts(["Contract"]), [], [Span(0, 8, "Document Name")])
    assert score_saved([doc], {"documents": []})["micro"] is None
    payload = {"documents": [{"id": "a", "text_sha256": hashlib.sha256(doc.text.encode()).hexdigest(), "predictions": []}]}
    result = score_saved([doc], payload)
    assert result["micro"]["fn"] == 1 and result["micro"]["f1"] == 0
    payload["documents"][0]["predictions"] = [{"start": 0, "end": 8, "label": "Document Name"}]
    assert score_saved([doc], payload)["micro"]["f1"] == 1
    payload["documents"][0]["text_sha256"] = "wrong"
    with pytest.raises(ValueError, match="different document"):
        score_saved([doc], payload)
