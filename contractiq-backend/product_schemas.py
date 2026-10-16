"""Saved reports, capability links, and bounded multi-document questions."""
from uuid import UUID

from pydantic import Field, field_validator

from audit_schemas import AuditResponse
from schemas import DISCLAIMER, Source, StrictModel


class SavedAudit(StrictModel):
    audit: AuditResponse
    filename: str
    generated_at: float
    expires_at: float


class ShareRequest(StrictModel):
    ttl_seconds: int = Field(default=900, ge=60, le=86400)


class ShareToken(StrictModel):
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class ShareCreated(ShareToken):
    expires_at: float


class WorkspaceQuestion(StrictModel):
    doc_ids: list[UUID] = Field(min_length=2, max_length=5)
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("doc_ids")
    @classmethod
    def unique_documents(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != len(values):
            raise ValueError("Choose distinct documents")
        return values


class WorkspaceSource(Source):
    doc_id: UUID
    filename: str


class WorkspaceAnswer(StrictModel):
    answer: str
    sources: list[WorkspaceSource]
    disclaimer: str = DISCLAIMER


class WorkspaceResult(StrictModel):
    answer: str = Field(min_length=1, max_length=6000)
    excerpt_ids: list[int] = Field(max_length=10)

    @field_validator("excerpt_ids")
    @classmethod
    def valid_ids(cls, values: list[int]) -> list[int]:
        if any(value < 1 or value > 10 for value in values):
            raise ValueError("Invalid excerpt number")
        return list(dict.fromkeys(values))
