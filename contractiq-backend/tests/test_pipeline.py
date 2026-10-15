import json
import time

import httpx
import pytest
from conftest import completion

from errors import ModelFailure, ServiceError
from llm import GroqLLM
from rag_pipeline import batches, merge_findings, validate_findings
from schemas import AnswerResult, Chunk, Finding, MapResult


def finding(**updates):
    return Finding.model_validate({
        "party": "Tenant", "benefit": "May renew", "kind": "benefit",
        "clause": "Tenant may renew.", "score": 6, "chunk_ids": ["c0"], **updates,
    })


def test_map_visits_every_chunk_including_late_clauses(service):
    chunks = [Chunk(id=f"c{i}", text=f"Tenant receives benefit {i}. " + "x" * 900, page=i + 1) for i in range(19)]
    metadata = service.store.create("long.txt", 18000, chunks)
    visited = []

    def provider(request):
        payload = json.loads(request.content)
        batch = json.loads(payload["messages"][1]["content"].split("<untrusted_contract_data>\n", 1)[1].split("\n</untrusted_contract_data>", 1)[0])
        visited.extend(chunk["id"] for chunk in batch)
        return completion({"items": [finding(
            clause=chunk["text"].split(". ")[0] + ".", chunk_ids=[chunk["id"]],
        ).model_dump() for chunk in batch]})

    service.llm = GroqLLM(service.settings, httpx.Client(transport=httpx.MockTransport(provider)))
    result = service.analyze_benefits(str(metadata.doc_id))
    assert visited == [chunk.id for chunk in chunks]
    assert result.analyzed_chunks == result.total_chunks == 19
    assert any(item.clause == "Tenant receives benefit 18." for item in result.items)


def test_partition_does_not_drop_boundary_chunk():
    chunks = [Chunk(id=str(i), text="x" * 700, page=None) for i in range(8)]
    groups = batches(chunks, 1000)
    assert [item for group in groups for item in group] == chunks


def test_reduce_merges_overlap_and_keeps_distinct_obligations():
    result = merge_findings([
        finding(), finding(party=" tenant ", clause="Tenant   may renew.", score=8, chunk_ids=["c1"]),
        finding(kind="obligation"), finding(party="Landlord"),
    ])
    assert len(result) == 3
    assert result[0].chunk_ids == ["c0", "c1"]
    assert result[0].score == 8


@pytest.mark.parametrize("item", [finding(clause="Unsupported quote"), finding(chunk_ids=["missing"])])
def test_unsupported_map_claim_rejected(item):
    with pytest.raises(ValueError):
        validate_findings(MapResult(items=[item]), [Chunk(id="c0", text="Tenant may renew.", page=None)])


def test_provider_native_schema_and_retry(settings):
    calls = []

    def provider(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return completion({"items": [{"score": "invalid"}]})
        return completion({"items": []})

    llm = GroqLLM(settings, httpx.Client(transport=httpx.MockTransport(provider)))
    assert llm.generate(MapResult, "extract", deadline=time.monotonic() + 30).items == []
    assert len(calls) == 2
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[0]["response_format"]["json_schema"]["strict"] is True


@pytest.mark.parametrize("payload", [
    {"choices": [{"finish_reason": "stop", "message": {"content": "```json\n{}\n```"}}]},
    {"choices": [{"finish_reason": "length", "message": {"content": '{"items": []}'}}]},
    {"choices": []},
])
def test_invalid_provider_output_has_bounded_retries(settings, payload):
    calls = []

    def provider(request):
        calls.append(request)
        return httpx.Response(200, json=payload)

    llm = GroqLLM(settings, httpx.Client(transport=httpx.MockTransport(provider)))
    with pytest.raises(ModelFailure):
        llm.generate(MapResult, "extract", deadline=time.monotonic() + 30)
    assert len(calls) == settings.structured_retries + 1


def test_json_object_mode_is_explicit(settings):
    def provider(request):
        assert json.loads(request.content)["response_format"] == {"type": "json_object"}
        return completion({"items": []})

    llm = GroqLLM(settings.model_copy(update={"structured_mode": "json_object"}), httpx.Client(transport=httpx.MockTransport(provider)))
    assert llm.generate(MapResult, "extract", deadline=time.monotonic() + 30).items == []


def test_deadline_and_provider_errors(settings):
    llm = GroqLLM(settings, httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(429))))
    with pytest.raises(ServiceError) as error:
        llm.generate(MapResult, "extract", deadline=time.monotonic() - 1)
    assert error.value.status == 504
    with pytest.raises(ServiceError) as error:
        llm.generate(MapResult, "extract", deadline=time.monotonic() + 20)
    assert error.value.status == 503


def test_partial_map_failure_never_returns_partial_analysis(service):
    chunks = [Chunk(id=str(i), text="x" * 900, page=None) for i in range(14)]
    metadata = service.store.create("long.txt", 12600, chunks)
    calls = []

    def provider(request):
        calls.append(request)
        return completion({"items": []}) if len(calls) == 1 else httpx.Response(503)

    service.llm = GroqLLM(service.settings, httpx.Client(transport=httpx.MockTransport(provider)))
    with pytest.raises(ServiceError) as error:
        service.analyze_benefits(str(metadata.doc_id))
    assert error.value.status == 503
    assert len(calls) == 1 + service.settings.structured_retries + 1


def test_schema_rejects_out_of_range_scores_and_extra_keys():
    with pytest.raises(ValueError):
        finding(score=11)
    with pytest.raises(ValueError):
        finding(secret="bad")
    with pytest.raises(ValueError):
        AnswerResult(answer="test", excerpt_ids=[5])
