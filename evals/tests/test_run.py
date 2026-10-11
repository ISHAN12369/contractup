import json

from config import Settings
from evals.data import Document, Question, Span, page_texts
from evals.run import evaluate


class TestIndex:
    def add(self, directory, chunks):
        directory.mkdir()
        (directory / "ids.json").write_text(json.dumps([c.id for c in chunks]))

    def search(self, directory, question, k):
        return [(key, 0.1) for key in json.loads((directory / "ids.json").read_text())[:k]]


class TestReranker:
    def score(self, query, texts):
        return [float(len(text)) for text in texts]


class SchemaProvider:
    def generate(self, schema, prompt, *, deadline, validate=None):
        quote = "Liability is capped at ten."
        values = {
            "AnswerResult": {"answer": quote + " [Excerpt 1]", "excerpt_ids": [1]},
            "ContractClassification": {"contract_type": "other", "evidence": quote, "chunk_id": "c00000"},
            "ClauseBatch": {"clauses": [{"type": "Cap On Liability", "quoted_text": quote, "chunk_id": "c00000", "party": "Both", "confidence": 0.5}]},
            "Claims": {"claims": [quote], "abstains": False},
            "Judgment": {"verdicts": [{"claim_index": 0, "supported": True, "evidence_quote": quote, "reason": "Quote"}], "relevance": 2, "relevance_reason": "Direct"},
        }
        value = schema.model_validate(values[schema.__name__])
        if validate:
            validate(value)
        return value


def dataset():
    text = "Liability is capped at ten."
    return [Document("fixture", "cuad", page_texts([text]),
                     [Question("q1", "What is the cap?", "Ten.", [Span(0, len(text))]),
                      Question("q2", "Who is the insurer?", "Not specified.", [], True)],
                     [Span(0, len(text), "Cap On Liability")])]


def test_offline_production_pipeline_uses_all_six_configs_without_provider(tmp_path):
    class NoProvider:
        def generate(self, *args, **kwargs):
            raise AssertionError("Offline evaluation must not call a provider")

    report = evaluate(dataset(), Settings(pii_mode="patterns"), tmp_path, {},
                      index=TestIndex(), reranker=TestReranker(), llm=NoProvider())
    assert report["status"] == "completed"
    assert len(report["rows"]) == 12
    assert len({row["config"] for row in report["rows"]}) == 6
    assert all(row["generation"]["status"] == "not_run" for row in report["rows"])
    assert len(report["audits"]) == 2 and all(row["status"] == "not_run" for row in report["audits"])
    assert not list(tmp_path.glob("contractiq-eval-*"))


def test_provider_path_generates_judges_and_scores_extraction_with_test_doubles(tmp_path):
    report = evaluate(dataset(), Settings(pii_mode="patterns"), tmp_path, {}, online=True,
                      index=TestIndex(), reranker=TestReranker(), llm=SchemaProvider())
    assert report["status"] == "completed"
    assert all(row["generation"]["status"] == "ok" for row in report["rows"])
    assert all(a["counts"] == {"tp": 1, "fp": 0, "fn": 0} for a in report["audits"])
    assert all(row["abstention_accuracy"] == 0.5 for row in report["summary"]["generation"])


def test_index_failure_does_not_silently_remove_questions(tmp_path):
    class BrokenIndex(TestIndex):
        def add(self, directory, chunks):
            raise RuntimeError("Controlled failure")

    report = evaluate(dataset(), Settings(), tmp_path, {}, index=BrokenIndex(),
                      reranker=TestReranker(), llm=SchemaProvider())
    assert report["status"] == "completed_with_errors"
    assert len(report["rows"]) == 12
    assert all(row["retrieval_error"] == "RuntimeError" for row in report["rows"])
    assert all(row["hit_at_4"] is None for row in report["summary"]["retrieval"])
