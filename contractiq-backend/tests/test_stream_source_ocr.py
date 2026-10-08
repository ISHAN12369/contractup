import io
import json
import shutil
import time
from threading import Event

import httpx
import pytest
from pypdf import PdfWriter

from audit_schemas import ClauseType, IndiaContext
from llm import GroqLLM
from ocr import recognize_page
from parsing import extract_document
from schemas import AnswerResult, OcrWord, PageText
from streaming import answer_prefix


def pdf_bytes():
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_ocr_runs_only_on_empty_page_and_retains_locations(settings, monkeypatch):
    calls = []

    def ocr(content, number, options):
        calls.append(number)
        return PageText(page=number, text="Scanned lease", ocr=True, words=[OcrWord(start=0, end=7, box=(0.1, 0.1, 0.3, 0.1))])

    monkeypatch.setattr("parsing.recognize_page", ocr)
    pages = extract_document("scan.pdf", pdf_bytes(), settings)
    assert calls == [1] and pages[0].ocr and pages[0].words[0].start == 0
    assert extract_document("plain.txt", b"Plain lease", settings)[0].ocr is False
    assert calls == [1]


def test_ocr_page_limit(settings, monkeypatch):
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.add_blank_page(100, 100)
    data = io.BytesIO()
    writer.write(data)
    monkeypatch.setattr("parsing.recognize_page", lambda content, number, options: PageText(page=number, text="scan", ocr=True))
    with pytest.raises(Exception, match="OCR page limit"):
        extract_document("scan.pdf", data.getvalue(), settings.model_copy(update={"max_ocr_pages": 1}))


def test_real_pdfium_renderer_with_ocr_word_coordinates(settings, monkeypatch):
    import pytesseract

    def recognize(image, **options):
        assert image.size == (200, 200)
        assert options["timeout"] == settings.ocr_timeout_seconds
        return {"text": ["Tenant", "pays"], "block_num": [1, 1], "par_num": [1, 1], "line_num": [1, 1],
                "left": [20, 80], "top": [20, 20], "width": [50, 40], "height": [20, 20]}

    monkeypatch.setattr(pytesseract, "image_to_data", recognize)
    result = recognize_page(pdf_bytes(), 1, settings.model_copy(update={"ocr_enabled": True}))
    assert result.text == "Tenant pays"
    assert result.words[1].start == 7
    assert result.words[0].box == (0.1, 0.1, 0.25, 0.1)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Native Tesseract executable is not installed")
def test_native_tesseract_on_image_only_pdf(settings):
    from PIL import Image, ImageDraw, ImageFont

    with Image.new("RGB", (1000, 300), "white") as image:
        ImageDraw.Draw(image).text((40, 80), "Tenant pays rent", fill="black", font=ImageFont.load_default(size=44))
        data = io.BytesIO()
        image.save(data, format="PDF")
    result = extract_document("scan.pdf", data.getvalue(), settings.model_copy(update={"ocr_enabled": True}))
    assert result[0].ocr and result[0].words
    assert "tenant" in result[0].text.lower() and "rent" in result[0].text.lower()


def test_source_pdf_ttl_and_deletion_cover_original_bytes(client, service, monkeypatch):
    monkeypatch.setattr("parsing.recognize_page", lambda content, number, options: PageText(page=number, text="Scanned lease", ocr=True))
    data = pdf_bytes()
    response = client.post("/upload", files={"file": ("scan.pdf", data)})
    assert response.status_code == 200
    metadata = response.json()
    assert metadata["has_pdf"] and metadata["ocr_pages"] == 1
    doc_id = metadata["doc_id"]
    source = client.get(f"/document/{doc_id}/source")
    assert source.json()["pages"][0]["text"] == "Scanned lease"
    original = client.get(f"/document/{doc_id}/file")
    assert original.content == data and original.headers["cache-control"] == "no-store"
    service.store.clock = lambda: metadata["expires_at"] + 1
    assert client.get(f"/document/{doc_id}/file").status_code == 404
    assert not service.store.directory(doc_id).exists()


def stream_response(answer='{"answer":"Tenant pays rent. [Excerpt 1]","excerpt_ids":[1]}', stop=True):
    frames = ["data: " + json.dumps({"choices": [{"delta": {"content": answer[index:index + 5]}}]}) + "\n\n" for index in range(0, len(answer), 5)]
    if stop:
        frames.append('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n')
    frames.append("data: [DONE]\n\n")
    return httpx.Response(200, content="".join(frames).encode(), headers={"content-type": "text/event-stream"})


def test_chat_sse_drafts_then_validated_completion(client, service, settings):
    doc_id = client.post("/upload", files={"file": ("lease.txt", b"Tenant pays rent.")}).json()["doc_id"]

    def provider(request):
        payload = json.loads(request.content)
        assert payload["stream"] and payload["response_format"] == {"type": "json_object"}
        return stream_response()

    service.llm = GroqLLM(settings, httpx.Client(transport=httpx.MockTransport(provider)))
    response = client.post("/chat/stream", json={"doc_id": doc_id, "question": "Who pays?"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-request-id"] and response.headers["x-accel-buffering"] == "no"
    assert response.text.index("event: draft") < response.text.index("event: complete")
    assert "not legal advice" in response.text and '"page_start"' in response.text


def test_chat_sse_invalid_output_retries_then_safe_error(client, service, settings):
    doc_id = client.post("/upload", files={"file": ("lease.txt", b"Tenant pays rent.")}).json()["doc_id"]
    calls = []

    def provider(request):
        calls.append(request)
        return stream_response('{"answer":"invented [Excerpt 9]","excerpt_ids":[9]}')

    service.llm = GroqLLM(settings, httpx.Client(transport=httpx.MockTransport(provider)))
    response = client.post("/chat/stream", json={"doc_id": doc_id, "question": "Who pays?"})
    assert len(calls) == settings.structured_retries + 1
    assert "event: error" in response.text and "event: complete" not in response.text


def test_provider_stream_cancellation_and_truncation(settings):
    llm = GroqLLM(settings, httpx.Client(transport=httpx.MockTransport(lambda _: stream_response(stop=False))))
    cancelled = Event()
    cancelled.set()
    assert list(llm.stream_json(AnswerResult, "test", deadline=time.monotonic() + 10, cancelled=cancelled)) == []
    with pytest.raises(ValueError, match="before completion"):
        list(llm.stream_json(AnswerResult, "test", deadline=time.monotonic() + 10, cancelled=Event()))


def test_answer_prefix_never_renders_other_fields_and_handles_escapes():
    assert answer_prefix('{"reasoning":"private","answer":"text"}') == ""
    assert answer_prefix('{"answer":"a\\nquoted \\"word') == 'a\nquoted "word'
    assert answer_prefix('{"answer":"a\\u00') == 'a'
    assert answer_prefix('{"answer":"done","excerpt_ids":[') == 'done'


def test_api_audit_and_compare_validation(client, service, monkeypatch):
    from conftest import completion

    metadata = client.post("/upload", files={"file": ("lease.txt", b"Liability is unlimited.")}).json()

    def provider(request):
        body = json.loads(request.content)
        if body["response_format"]["json_schema"]["name"] == "ContractClassification":
            return completion({"contract_type": "lease", "evidence": "Liability is unlimited.", "chunk_id": "c00000"})
        return completion({"clauses": [{"type": ClauseType.UNCAPPED_LIABILITY.value, "quoted_text": "Liability is unlimited.", "chunk_id": "c00000", "party": "Unspecified", "confidence": 0.7}]})

    service.llm = GroqLLM(service.settings, httpx.Client(transport=httpx.MockTransport(provider)))
    response = client.post("/audit", json={"doc_id": metadata["doc_id"], "india": IndiaContext(enabled=True).model_dump()})
    assert response.status_code == 200
    assert response.json()["overall_risk"]["level"] == "high"
    assert len(response.json()["rule_checks"]) == 7
    assert client.post("/audit", json={"doc_id": metadata["doc_id"], "india": {"enabled_rules": ["invented"]}}).status_code == 422
    assert client.post("/compare", json={"before_id": metadata["doc_id"], "after_id": metadata["doc_id"]}).status_code == 422
