"""Per-document Chroma directories and manifests, with TTL and physical deletion."""

import logging
import shutil
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID, uuid4

from config import Settings
from errors import MissingDocument, ServiceError
from schemas import Chunk, DocumentMetadata, DocumentRecord

logger = logging.getLogger(__name__)
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class VectorIndex(Protocol):
    def add(self, directory: Path, chunks: list[Chunk]) -> None: ...
    def search(self, directory: Path, question: str, k: int) -> list[tuple[str, float]]: ...


class ChromaIndex:
    """Open/close each client so deletion releases SQLite and HNSW handles."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self._embed: Callable[[list[str]], list[list[float]]] | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._embed is None:
            from fastembed import TextEmbedding

            model = TextEmbedding(EMBEDDING_MODEL, threads=1, cache_dir=str(self.cache_dir))
            self._embed = lambda values: [vector.tolist() for vector in model.embed(values, batch_size=16)]
        return self._embed(texts)

    def add(self, directory: Path, chunks: list[Chunk]) -> None:
        import chromadb
        from chromadb.api.client import Client
        from chromadb.config import Settings as ChromaSettings

        vectors: list[Sequence[float] | Sequence[int]] = list(self.embed([chunk.text for chunk in chunks]))
        client = cast(Client, chromadb.PersistentClient(
            path=str(directory), settings=ChromaSettings(anonymized_telemetry=False)
        ))
        try:
            collection = client.create_collection(
                "contract", embedding_function=None,
                configuration={"hnsw": {"space": "cosine", "num_threads": 1}},
            )
            collection.add(ids=[chunk.id for chunk in chunks], embeddings=vectors)
        finally:
            client.close()

    def search(self, directory: Path, question: str, k: int) -> list[tuple[str, float]]:
        import chromadb
        from chromadb.api.client import Client
        from chromadb.config import Settings as ChromaSettings

        vectors: list[Sequence[float] | Sequence[int]] = list(self.embed([question]))
        client = cast(Client, chromadb.PersistentClient(
            path=str(directory), settings=ChromaSettings(anonymized_telemetry=False)
        ))
        try:
            collection = client.get_collection("contract", embedding_function=None)
            result = collection.query(query_embeddings=vectors, n_results=k, include=["distances"])
            distances = result["distances"]
            if distances is None:
                return []
            return list(zip(result["ids"][0], distances[0], strict=True))
        finally:
            client.close()


class DocumentStore:
    def __init__(self, settings: Settings, index: VectorIndex, clock: Callable[[], float] = time.time):
        self.settings = settings
        self.index = index
        self.clock = clock
        self.root = (settings.data_dir / "documents").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def directory(self, doc_id: str) -> Path:
        try:
            normalized = str(UUID(doc_id))
        except ValueError as exc:
            raise MissingDocument() from exc
        return self.root / normalized

    def create(self, filename: str, chars: int, chunks: list[Chunk]) -> DocumentMetadata:
        with self.lock:
            self.cleanup()
            if len(list(self.root.iterdir())) >= self.settings.max_documents:
                raise ServiceError(503, "Document capacity reached. Delete an earlier upload or retry later.")
            doc_id = uuid4()
            directory = self.directory(str(doc_id))
            directory.mkdir()
            now = self.clock()
            metadata = DocumentMetadata(
                doc_id=doc_id, filename=filename, chars=chars, num_chunks=len(chunks),
                created_at=now, expires_at=now + self.settings.document_ttl_seconds,
            )
            record = DocumentRecord(metadata=metadata, chunks=chunks)
            try:
                self.index.add(directory / "vectors", chunks)
                (directory / "document.json").write_text(record.model_dump_json(), encoding="utf-8")
            except Exception:
                self._remove(directory)
                raise
            self.get(str(doc_id))
            return metadata

    def get(self, doc_id: str) -> DocumentRecord:
        with self.lock:
            directory = self.directory(doc_id)
            try:
                record = DocumentRecord.model_validate_json(
                    (directory / "document.json").read_text(encoding="utf-8")
                )
            except (OSError, ValueError) as exc:
                raise MissingDocument() from exc
            if record.metadata.expires_at <= self.clock():
                self._remove(directory)
                raise MissingDocument()
            return record

    def search(self, doc_id: str, question: str, k: int = 4) -> list[tuple[Chunk, float]]:
        with self.lock:
            record = self.get(doc_id)
            by_id = {chunk.id: chunk for chunk in record.chunks}
            hits = self.index.search(self.directory(doc_id) / "vectors", question, min(k, len(by_id)))
            return [(by_id[key], distance) for key, distance in hits if key in by_id]

    def delete(self, doc_id: str) -> None:
        with self.lock:
            directory = self.directory(doc_id)
            if not directory.exists():
                return
            # Tombstone before unlinking: failed physical deletion cannot leave readable content.
            (directory / "document.json").unlink(missing_ok=True)
            if not self._remove(directory):
                raise ServiceError(503, "Deletion is pending cleanup. Please retry shortly.")

    def _remove(self, directory: Path) -> bool:
        if directory.parent.resolve() != self.root or directory.is_symlink():
            raise RuntimeError("Refusing deletion outside the document store")
        try:
            if directory.exists():
                shutil.rmtree(directory)
            return True
        except OSError:
            logger.error("document_cleanup_failed")
            return False

    def cleanup(self) -> int:
        removed = 0
        with self.lock:
            for directory in self.root.iterdir():
                if not directory.is_dir() or directory.is_symlink():
                    continue
                try:
                    UUID(directory.name)
                except ValueError:
                    continue
                try:
                    record = DocumentRecord.model_validate_json(
                        (directory / "document.json").read_text(encoding="utf-8")
                    )
                    expired = record.metadata.expires_at <= self.clock()
                except (OSError, ValueError):
                    expired = True
                if expired and self._remove(directory):
                    removed += 1
        return removed
