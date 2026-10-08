"""Public API and provider output contracts. No unvalidated model dictionaries."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

DISCLAIMER = "Informational only, not legal advice. Verify findings against the contract with a qualified professional."


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class HistoryMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=6000)


class DocumentRequest(StrictModel):
    doc_id: UUID


class ChatRequest(DocumentRequest):
    question: str = Field(min_length=1, max_length=2000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=6)


class Chunk(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    id: str
    text: str
    page: int | None
    section_id: str = "unsectioned"
    start: int = 0
    end: int = 0
    page_start: int = 0
    page_end: int = 0
    ocr: bool = False


class OcrWord(StrictModel):
    start: int
    end: int
    # Coordinates normalized to the rendered page, origin at top left.
    box: tuple[float, float, float, float]


class PageText(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    page: int | None
    text: str
    start: int = 0
    ocr: bool = False
    words: list[OcrWord] = Field(default_factory=list)


class DocumentMetadata(StrictModel):
    doc_id: UUID
    filename: str
    chars: int
    num_chunks: int
    created_at: float
    expires_at: float
    has_pdf: bool = False
    ocr_pages: int = 0
    chunking_strategy: str = "recursive"


class DocumentRecord(StrictModel):
    metadata: DocumentMetadata
    chunks: list[Chunk]
    pages: list[PageText] = Field(default_factory=list)
    version: int = 2


class Finding(StrictModel):
    party: str = Field(min_length=1, max_length=200)
    benefit: str = Field(min_length=1, max_length=600)
    kind: Literal["benefit", "obligation"]
    clause: str = Field(min_length=1, max_length=1000)
    score: int = Field(ge=1, le=10, strict=True)
    chunk_ids: list[str] = Field(min_length=1, max_length=600)


class MapResult(StrictModel):
    items: list[Finding] = Field(max_length=100)


class AnswerResult(StrictModel):
    answer: str = Field(min_length=1, max_length=6000)
    excerpt_ids: list[int] = Field(max_length=4)

    @field_validator("excerpt_ids")
    @classmethod
    def valid_excerpt_ids(cls, values: list[int]) -> list[int]:
        if any(v < 1 or v > 4 for v in values):
            raise ValueError("Invalid excerpt number")
        return list(dict.fromkeys(values))


class Source(StrictModel):
    excerpt: int
    chunk_id: str
    preview: str
    page: int | None
    distance: float | None
    section_id: str = "unsectioned"
    start: int = 0
    end: int = 0
    page_start: int = 0
    page_end: int = 0
    ocr: bool = False
    retrieval_score: float | None = None


class ChatResponse(StrictModel):
    answer: str
    sources: list[Source]
    disclaimer: str = DISCLAIMER
    strategy: str = "dense"


class BenefitsResponse(StrictModel):
    items: list[Finding]
    analyzed_chunks: int
    total_chunks: int
    disclaimer: str = DISCLAIMER
