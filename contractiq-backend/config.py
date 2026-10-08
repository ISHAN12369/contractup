"""Validated, explicit limits for the single-worker Phase 0 service."""

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_dir: Path = Path("data")
    model_cache_dir: Path = Path("model-cache")
    cors_origins: list[str] = ["http://localhost:3000"]
    groq_api_key: str = Field(default="", repr=False)
    groq_model: str = "openai/gpt-oss-20b"
    structured_mode: str = "json_schema"
    max_upload_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    max_text_chars: int = Field(default=100_000, ge=1000, le=500_000)
    max_chunks: int = Field(default=120, ge=1, le=600)
    max_documents: int = Field(default=20, ge=1, le=1000)
    document_ttl_seconds: int = Field(default=3600, ge=1)
    cleanup_interval_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_requests: int = Field(default=30, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    llm_timeout_seconds: int = Field(default=45, ge=1, le=120)
    analysis_timeout_seconds: int = Field(default=240, ge=1, le=1800)
    structured_retries: int = Field(default=1, ge=0, le=2)
    map_batch_chars: int = Field(default=6000, ge=1000, le=12000)
    chunking_strategy: Literal["recursive", "clause"] = "clause"
    retriever_strategy: Literal["dense", "hybrid", "hybrid_rerank"] = "hybrid_rerank"
    retrieval_candidates: int = Field(default=12, ge=4, le=40)
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    pii_mode: Literal["standard", "patterns"] = "standard"
    pii_model: str = "en_core_web_sm"
    ocr_enabled: bool = True
    ocr_language: str = "eng"
    max_ocr_pages: int = Field(default=10, ge=1, le=30)
    ocr_timeout_seconds: int = Field(default=20, ge=1, le=60)
    india_rule_pack: bool = True
    audit_max_clauses: int = Field(default=200, ge=1, le=600)

    @field_validator("cors_origins")
    @classmethod
    def explicit_origins(cls, origins: list[str]) -> list[str]:
        if not origins:
            raise ValueError("CORS_ORIGINS must contain at least one explicit origin")
        for origin in origins:
            parts = urlsplit(origin)
            if (
                "*" in origin or parts.scheme not in {"http", "https"}
                or not parts.netloc or parts.path or parts.query or parts.fragment
                or parts.username or parts.password
            ):
                raise ValueError("CORS_ORIGINS must contain exact http(s) origins without paths")
        return origins

    @field_validator("structured_mode")
    @classmethod
    def supported_mode(cls, mode: str) -> str:
        if mode not in {"json_schema", "json_object"}:
            raise ValueError("STRUCTURED_MODE must be json_schema or json_object")
        return mode

    @classmethod
    def from_env(cls) -> "Settings":
        values: dict[str, object] = {}
        for name in cls.model_fields:
            value = os.getenv(name.upper())
            if value is not None:
                values[name] = value
        if "cors_origins" in values:
            values["cors_origins"] = [
                v.strip() for v in str(values["cors_origins"]).split(",") if v.strip()
            ]
        return cls.model_validate(values)
