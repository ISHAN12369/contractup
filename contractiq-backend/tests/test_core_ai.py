import json

import httpx
import pytest
from conftest import completion

from audit import run_audit, verify_candidates
from audit_schemas import CandidateClause, ClauseType, IndiaContext
from chunking import split_pages
from comparison import compare_audits
from india_rules import check_rules
from llm import GroqLLM
from locations import locate, quote_span
from privacy import RedactionVault
from retrieval import Retriever, bm25, rrf
from risk import assess
from schemas import ChatRequest, Chunk, PageText


def candidate(**updates):
    return CandidateClause.model_validate({
        "type": "Uncapped Liability", "quoted_text": "Liability is unlimited.",
        "chunk_id": "c00000", "party": "Tenant", "confidence": 0.8, **updates,
    })


def test_heading_chunking_offsets_fallback_and_repeated_text(settings):
    first = "Introduction\n1. Rent\nTenant pays rent.\nARTICLE II\nTenant pays rent.\n"
    pages = [PageText(page=1, text=first), PageText(page=2, text="Continuation\nSection 3\n" + "abc " * 800, start=len(first) + 2)]
    chunks = split_pages(pages, settings)
    assert {c.section_id for c in chunks} >= {"unsectioned", "1.", "ARTICLE II", "Section 3"}
    canonical = "\n\n".join(page.text for page in pages)
    for chunk in chunks:
        assert canonical[chunk.start:chunk.end] == chunk.text
        assert pages[chunk.page - 1].text[chunk.page_start:chunk.page_end] == chunk.text
    assert chunks[-1].section_id == "Section 3"
    recursive = split_pages(pages, settings.model_copy(update={"chunking_strategy": "recursive"}))
    assert all(chunk.section_id == "unsectioned" for chunk in recursive)
    assert quote_span("  STRAẞE\n  rent", "straße rent") == (2, 15)


def test_bm25_rrf_and_configurable_reranking(service, settings):
    chunks = [Chunk(id="a", text="rent rent rent", page=None), Chunk(id="b", text="zebra escrow", page=None), Chunk(id="c", text="general", page=None)]
    assert bm25(chunks, "zebra")[0][0] == "b"
    assert bm25(chunks, "absent") == []
    assert rrf([["a", "b"], ["b", "c"]])[0][0] == "b"
    doc = service.store.create("test.txt", 30, chunks)

    class Ranked:
        def score(self, question, texts):
            return [10.0 if "escrow" in text else 0.0 for text in texts]

    retriever = Retriever(settings, service.store, Ranked())
    assert retriever.search(str(doc.doc_id), "escrow", "dense")[0].chunk.id == "a"
    assert retriever.search(str(doc.doc_id), "escrow", "hybrid")[0].chunk.id == "b"
    assert retriever.search(str(doc.doc_id), "escrow", "hybrid_rerank")[0].chunk.id == "b"


def test_presidio_reversible_patterns_and_fail_closed(settings):
    vault = RedactionVault(settings)
    raw = 'Email sam@example.com, PAN ABCDE1234F; phone 9876543210.'
    redacted = vault.redact(raw)
    assert "sam@example.com" not in redacted
    assert "ABCDE1234F" not in redacted
    assert "9876543210" not in redacted
    assert vault.restore(redacted) == raw
    assert vault.redact(raw) == redacted
    with pytest.raises(Exception, match="PII redaction is unavailable"):
        RedactionVault(settings.model_copy(update={"pii_mode": "standard", "pii_model": "missing_local_model"})).redact(raw)


def test_standard_presidio_detects_person(settings):
    vault = RedactionVault(settings.model_copy(update={"pii_mode": "standard"}))
    text = "Martha Stewart signed the agreement. Contact martha@example.com."
    safe = vault.redact(text)
    assert "Martha Stewart" not in safe
    assert "martha@example.com" not in safe
    assert vault.restore(safe) == text


def test_verified_quotes_risk_redlines_and_41_labels():
    assert len(ClauseType) == 41
    chunk = Chunk(id="c00000", text="Liability is unlimited.", page=2, start=80, end=103, page_start=10, page_end=33)
    accepted, dropped = verify_candidates([candidate(), candidate(), candidate(quoted_text="Invented words")], [chunk])
    assert len(accepted) == 1 and dropped == 1
    assert accepted[0].location.start == 80
    assert accepted[0].risk.level == "high"
    assert accepted[0].redline.original == chunk.text
    assert "not legal advice" in accepted[0].redline.disclaimer
    assert assess(ClauseType.PARTIES, "The parties are listed.").level == "low"
    assert locate(chunk, "not in text") is None


def audit_fixture(settings, service, text="Liability is unlimited."):
    metadata = service.ingest_document("lease.txt", text.encode())
    record = service.store.get(str(metadata.doc_id))
    calls = []

    def provider(request):
        body = json.loads(request.content)
        calls.append(body)
        name = body["response_format"]["json_schema"]["name"]
        if name == "ContractClassification":
            return completion({"contract_type": "lease", "evidence": text, "chunk_id": "c00000"})
        return completion({"clauses": [candidate(quoted_text=text).model_dump(), candidate(quoted_text="Invented").model_dump()]})

    llm = GroqLLM(settings, httpx.Client(transport=httpx.MockTransport(provider)))
    return run_audit(record, settings, llm, IndiaContext()), calls


def test_langgraph_workflow_drops_unsupported_and_summarizes(settings, service):
    result, calls = audit_fixture(settings, service)
    assert result.steps == ["classify", "checklist", "extract", "verify", "summarize"]
    assert result.analyzed_chunks == result.total_chunks
    assert result.dropped_claims == 1 and len(result.clauses) == 1
    assert result.overall_risk.score == 80
    assert len(calls) == 2


def test_india_rules_need_context_and_never_claim_nationwide_compliance():
    chunks = [Chunk(id="a", text="The security deposit is payable. Notice is required.", page=None)]
    context = IndiaContext(enabled=True)
    checks = check_rules(chunks, context)
    assert len(checks) == 7
    assert next(c for c in checks if c.id == "deposit").status == "context_needed"
    assert all(c.source_url.startswith("https://") and c.disclaimer for c in checks)
    context = IndiaContext(enabled=True, state="User-specified state", premises="residential", model_act_applicable=True, monthly_rent=10000, deposit=30000, enabled_rules=["deposit"])
    check = check_rules(chunks, context)[0]
    assert check.status == "attention" and "unverified" in check.detail


def test_comparison_aligns_semantic_changes_without_reusing_clauses(settings, service):
    before, _ = audit_fixture(settings, service)
    after, _ = audit_fixture(settings, service, "Liability has no monetary ceiling.")
    result = compare_audits(before, after, lambda texts: [[1.0, 0.0] for _ in texts])
    assert len(result.changes) == 1 and result.changes[0].kind == "changed"
    assert result.changes[0].risk_delta == 0
    empty = after.model_copy(update={"clauses": [], "overall_risk": None})
    removed = compare_audits(before, empty, lambda _: [])
    assert removed.changes[0].kind == "removed" and removed.overall_risk_delta is None
    assert compare_audits(before, before, lambda _: []).unchanged == 1


def test_chat_provider_payload_is_redacted(service, settings):
    metadata = service.ingest_document("lease.txt", b"Email tenant@example.com for notices.")

    def provider(request):
        payload = request.content.decode()
        assert "tenant@example.com" not in payload
        assert "question@example.com" not in payload
        assert "history@example.com" not in payload
        return completion({"answer": "See the notice clause. [Excerpt 1]", "excerpt_ids": [1]})

    service.llm = GroqLLM(settings, httpx.Client(transport=httpx.MockTransport(provider)))
    result = service.get_answer(ChatRequest(doc_id=metadata.doc_id, question="Is question@example.com listed?", history=[{"role": "user", "content": "history@example.com"}]))
    assert result.sources[0].preview == "Email tenant@example.com for notices."
