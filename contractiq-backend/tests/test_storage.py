from uuid import uuid4

import pytest
from conftest import FakeIndex

from errors import MissingDocument, ServiceError
from schemas import Chunk
from storage import ChromaIndex, DocumentStore


def test_expiry_deletes_text_and_vectors_and_survives_restart(settings):
    clock = [1000.0]
    store = DocumentStore(settings, FakeIndex(), lambda: clock[0])
    metadata = store.create("test.txt", 10, [Chunk(id="c0", text="private", page=None)])
    directory = store.directory(str(metadata.doc_id))
    assert (directory / "vectors" / "ids.json").exists()
    clock[0] = metadata.expires_at
    restarted = DocumentStore(settings, FakeIndex(), lambda: clock[0])
    with pytest.raises(MissingDocument):
        restarted.get(str(metadata.doc_id))
    assert not directory.exists()


def test_cleanup_removes_crash_leftovers_but_never_unrelated_paths(service):
    orphan = service.store.root / str(uuid4())
    orphan.mkdir()
    unrelated = service.store.root / "not-a-document"
    unrelated.mkdir()
    assert service.store.cleanup() == 1
    assert not orphan.exists()
    assert unrelated.exists()
    with pytest.raises(MissingDocument):
        service.store.directory("../../etc/passwd")


def test_failed_indexing_cleans_partial_data(settings):
    class BrokenIndex(FakeIndex):
        def add(self, directory, chunks):
            super().add(directory, chunks)
            raise RuntimeError("ingestion failed")

    store = DocumentStore(settings, BrokenIndex())
    with pytest.raises(RuntimeError):
        store.create("bad.txt", 10, [Chunk(id="c0", text="x", page=None)])
    assert list(store.root.iterdir()) == []


def test_delete_is_idempotent_and_store_is_bounded(service):
    metadata = service.ingest_document("test.txt", b"Tenant pays rent.")
    service.store.delete(str(metadata.doc_id))
    service.store.delete(str(metadata.doc_id))
    with pytest.raises(MissingDocument):
        service.store.get(str(metadata.doc_id))
    service.store.settings = service.settings.model_copy(update={"max_documents": 1})
    service.ingest_document("first.txt", b"First agreement.")
    with pytest.raises(ServiceError) as error:
        service.ingest_document("second.txt", b"Second agreement.")
    assert error.value.status == 503


def test_real_chroma_persists_queries_closes_and_deletes(settings):
    # Real Chroma, deterministic vectors: checks the integration without downloading models.
    index = ChromaIndex(settings.data_dir / "cache")
    index._embed = lambda texts: [[1.0, 0.0, 0.0] if "rent" in text else [0.0, 1.0, 0.0] for text in texts]
    store = DocumentStore(settings, index)
    metadata = store.create("contract.txt", 40, [
        Chunk(id="rent", text="Tenant pays rent.", page=1),
        Chunk(id="notice", text="Thirty days notice.", page=2),
    ])
    hits = store.search(str(metadata.doc_id), "rent", k=1)
    assert hits[0][0].id == "rent"
    assert hits[0][1] == pytest.approx(0.0)
    store.delete(str(metadata.doc_id))
    assert not store.directory(str(metadata.doc_id)).exists()
