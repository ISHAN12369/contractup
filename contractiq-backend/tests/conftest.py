import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from config import Settings
from llm import GroqLLM
from main import create_app
from rag_pipeline import RAGService
from schemas import Chunk
from storage import DocumentStore


class FakeIndex:
    def add(self, directory: Path, chunks: list[Chunk]) -> None:
        directory.mkdir()
        (directory / "ids.json").write_text(json.dumps([chunk.id for chunk in chunks]))

    def search(self, directory: Path, question: str, k: int) -> list[tuple[str, float]]:
        return [(key, 0.1) for key in json.loads((directory / "ids.json").read_text())[:k]]


def completion(value: object) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{
        "finish_reason": "stop", "message": {"content": json.dumps(value)},
    }]})


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, groq_api_key="test-secret", rate_limit_requests=1000,
                    retriever_strategy="dense", pii_mode="patterns", ocr_enabled=False)


@pytest.fixture
def service(settings):
    def provider(request):
        payload = json.loads(request.content)
        if payload["response_format"]["json_schema"]["name"] == "MapResult":
            return completion({"items": []})
        return completion({"answer": "The tenant pays rent. [Excerpt 1]", "excerpt_ids": [1]})

    llm = GroqLLM(settings, httpx.Client(transport=httpx.MockTransport(provider)))
    return RAGService(settings, DocumentStore(settings, FakeIndex()), llm)


@pytest.fixture
def client(settings, service):
    with TestClient(create_app(settings, service), raise_server_exceptions=False) as instance:
        yield instance
