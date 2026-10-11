"""Validated source spans, frozen CUAD test split, and explicitly authored Q&A."""
import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from audit_schemas import ClauseType
from schemas import PageText

CUAD_REVISION = "67faa0e6023b04fcaae6cc09497ab00e5d63a2a2"
CUAD_URL = f"https://raw.githubusercontent.com/The-Atticus-Project/cuad/{CUAD_REVISION}/data.zip"
CUAD_SHA256 = "f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a"


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    label: str = ""

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("Spans must be positive-length half-open source intervals")


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    answer: str
    spans: list[Span]
    unanswerable: bool = False


@dataclass(frozen=True)
class Document:
    id: str
    source: str
    pages: list[PageText]
    questions: list[Question]
    clauses: list[Span] | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_key(value: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()


def page_texts(texts: list[str]) -> list[PageText]:
    result, start = [], 0
    for number, text in enumerate(texts, 1):
        result.append(PageText(page=number, text=text, start=start))
        start += len(text) + 2
    return result


def label_name(value: str) -> str:
    known = {item.value.casefold(): item.value for item in ClauseType}
    try:
        return known[value.casefold()]
    except KeyError as exc:
        raise ValueError(f"Unknown CUAD label: {value}") from exc


def load_golden(path: Path, source: str = "golden") -> list[Document]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = []
    ids: set[str] = set()
    question_ids: set[str] = set()
    for raw in payload["documents"]:
        identifier = raw["id"]
        if identifier in ids:
            raise ValueError("Duplicate document ID")
        ids.add(identifier)
        pages = page_texts(raw["pages"])
        if not pages or not raw["questions"]:
            raise ValueError("Each document needs pages and questions")
        text = "\n\n".join(page.text for page in pages)
        questions = []
        for item in raw["questions"]:
            qid = f"{identifier}:{item['id']}"
            if qid in question_ids:
                raise ValueError("Duplicate question ID")
            question_ids.add(qid)
            spans = []
            for quotation in item["quotes"]:
                quote = quotation["text"]
                if not quote or quotation.get("occurrence", 0) < 0:
                    raise ValueError("Empty reference quotation")
                start = -1
                for _ in range(quotation.get("occurrence", 0) + 1):
                    start = text.find(quote, start + 1)
                    if start < 0:
                        raise ValueError(f"Reference quote absent: {qid}")
                spans.append(Span(start, start + len(quote)))
            absent = bool(item.get("unanswerable", False))
            if bool(spans) == absent:
                raise ValueError(f"Answerability/span mismatch: {qid}")
            questions.append(Question(qid, item["question"], item["answer"], spans, absent))
        documents.append(Document(identifier, source, pages, questions))
    if not documents:
        raise ValueError("Empty evaluation dataset")
    return documents


def load_cuad(path: Path, limit: int = 3, questions_per_doc: int = 6, seed: int = 42,
              max_chars: int = 100_000) -> tuple[list[Document], dict[str, Any]]:
    if digest(path) != CUAD_SHA256:
        raise ValueError("CUAD archive checksum differs from the pinned dataset")
    with zipfile.ZipFile(path) as archive:
        data = json.loads(archive.read("test.json"))["data"]
    eligible = [item for item in data if len(item["paragraphs"]) == 1
                and len(item["paragraphs"][0]["context"]) <= max_chars]
    selected = sorted(eligible, key=lambda item: stable_key(item["title"], seed))[:limit or None]
    documents = []
    for raw in selected:
        paragraph = raw["paragraphs"][0]
        text = paragraph["context"]
        questions, clauses = [], set()
        for item in paragraph["qas"]:
            label = label_name(item["id"].rsplit("__", 1)[1])
            spans = []
            for answer in item["answers"]:
                start, quote = answer["answer_start"], answer["text"]
                if start < 0 or not quote or text[start:start + len(quote)] != quote:
                    raise ValueError(f"Invalid CUAD source span: {item['id']}")
                span = Span(start, start + len(quote), label)
                spans.append(span)
                clauses.add(span)
            if bool(spans) == bool(item["is_impossible"]):
                raise ValueError("CUAD answerability mismatch")
            questions.append(Question(item["id"], item["question"], "\n".join(a["text"] for a in item["answers"]), spans, not spans))
        positives = sorted((q for q in questions if q.spans), key=lambda q: stable_key(q.id, seed))
        # Retain all labels for extraction; only retrieval questions are subsampled.
        chosen = positives[:questions_per_doc or None]
        documents.append(Document(raw["title"], "cuad", page_texts([text]), chosen,
                                  sorted(clauses, key=lambda span: (span.label, span.start, span.end))))
    return documents, {"revision": CUAD_REVISION, "archive_sha256": CUAD_SHA256,
                       "split": "test", "test_documents": len(data), "eligible_documents": len(eligible),
                       "excluded_by_length_or_structure": len(data) - len(eligible), "max_chars": max_chars,
                       "selected_documents": [d.id for d in documents], "seed": seed,
                       "questions_per_doc": questions_per_doc, "document_limit": limit}
