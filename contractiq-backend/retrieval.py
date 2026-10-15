"""Configurable dense/BM25/RRF retrieval, with optional local ONNX cross-encoding."""

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from config import Settings
from errors import ServiceError
from postgres_store import PostgresStore
from schemas import Chunk
from storage import DocumentStore


def tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def bm25(chunks: list[Chunk], query: str) -> list[tuple[str, float]]:
    terms = [Counter(tokens(chunk.text)) for chunk in chunks]
    lengths = [sum(counts.values()) for counts in terms]
    average = sum(lengths) / max(len(lengths), 1) or 1
    document_frequency = Counter(term for counts in terms for term in counts)
    scores: list[tuple[str, float]] = []
    for chunk, counts, length in zip(chunks, terms, lengths, strict=True):
        score = 0.0
        for term in set(tokens(query)):
            frequency = counts[term]
            if not frequency:
                continue
            inverse = math.log(1 + (len(chunks) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
            score += inverse * frequency * 2.5 / (frequency + 1.5 * (0.25 + 0.75 * length / average))
        if score > 0:
            scores.append((chunk.id, score))
    return sorted(scores, key=lambda item: (-item[1], item[0]))


def rrf(rankings: list[list[str]], constant: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(dict.fromkeys(ranking), 1):
            scores[key] = scores.get(key, 0.0) + 1 / (constant + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


class Reranker(Protocol):
    def score(self, query: str, texts: list[str]) -> list[float]: ...


class OnnxReranker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._score: Reranker | None = None

    def score(self, query: str, texts: list[str]) -> list[float]:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        # A retained bound callable avoids loading a second model per request.
        if not hasattr(self, "_model"):
            self._model = TextCrossEncoder(
                model_name=self.settings.reranker_model, threads=1, cuda=False,
                cache_dir=str(self.settings.model_cache_dir),
            )
        return [float(value) for value in self._model.rerank(query, texts, batch_size=4)]


@dataclass
class Hit:
    chunk: Chunk
    score: float
    distance: float | None


class Retriever:
    def __init__(self, settings: Settings, store: DocumentStore | PostgresStore, reranker: Reranker | None = None):
        self.settings, self.store = settings, store
        self.reranker = reranker or OnnxReranker(settings)

    def search(self, doc_id: str, question: str, strategy: str | None = None) -> list[Hit]:
        strategy = strategy or self.settings.retriever_strategy
        if strategy not in {"dense", "hybrid", "hybrid_rerank"}:
            raise ValueError("Unsupported retrieval strategy")
        record = self.store.get(doc_id)
        count = 4 if strategy == "dense" else self.settings.retrieval_candidates
        dense = self.store.search(doc_id, question, count)
        distances = {chunk.id: distance for chunk, distance in dense}
        by_id = {chunk.id: chunk for chunk in record.chunks}
        if strategy == "dense":
            return [Hit(chunk, 1 - distance, distance) for chunk, distance in dense]
        fused = rrf([
            [chunk.id for chunk, _ in dense],
            [key for key, _ in bm25(record.chunks, question)[:count]],
        ])[:count]
        if strategy == "hybrid_rerank":
            try:
                scores = self.reranker.score(question, [by_id[key].text for key, _ in fused])
                if len(scores) != len(fused) or not all(math.isfinite(score) for score in scores):
                    raise ValueError("Invalid reranker scores")
                fused = sorted(zip([key for key, _ in fused], scores, strict=True), key=lambda item: (-item[1], item[0]))
            except Exception as exc:
                raise ServiceError(503, "The local reranker is unavailable. Preload its model or configure hybrid retrieval.") from exc
        return [Hit(by_id[key], score, distances.get(key)) for key, score in fused[:4]]
