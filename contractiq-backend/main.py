"""Single-worker FastAPI application. Blocking parsing/model work runs off-loop."""

import asyncio
import json
import logging
import queue
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from typing import Annotated, TypeVar
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from audit_schemas import AuditRequest, AuditResponse, CompareRequest, CompareResponse
from auth import AuthMiddleware, SupabaseVerifier, Verifier
from config import Settings
from errors import ServiceError
from ingestion import Ingestion, production_store, redis_client
from postgres_store import PostgresStore
from providers import ProviderChain, create_provider
from rag_pipeline import RAGService
from redis_services import RedisLimiter
from schemas import (
    BenefitsResponse,
    ChatRequest,
    ChatResponse,
    DocumentMetadata,
    DocumentRecord,
    DocumentRequest,
)
from security import SecurityMiddleware
from storage import ChromaIndex, DocumentStore
from telemetry import configure_telemetry, flush_telemetry, report_error

logger = logging.getLogger(__name__)
T = TypeVar("T")


def create_app(settings: Settings | None = None, service: RAGService | None = None, *,
               verifier: Verifier | None = None, ingestion: Ingestion | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    owned_llm: ProviderChain | None = None
    configure_telemetry(settings)
    if service is None:
        store = production_store(settings) if settings.app_mode == "production" else DocumentStore(settings, ChromaIndex(settings.model_cache_dir))
        owned_llm = create_provider(settings)
        service = RAGService(settings, store, owned_llm)
    active_service = service
    distributed = redis_client(settings) if settings.app_mode == "production" else None
    if settings.app_mode == "production" and ingestion is None:
        if not isinstance(active_service.store, PostgresStore):
            raise ValueError("Production requires tenant-filtered Postgres storage")
        ingestion = Ingestion(settings, active_service.store)
    operation_lock = threading.Lock()

    def bounded(operation: Callable[[], T]) -> T:
        if not operation_lock.acquire(blocking=False):
            raise ServiceError(503, "The server is processing another document. Please retry shortly.")
        try:
            return operation()
        finally:
            operation_lock.release()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await run_in_threadpool(active_service.store.cleanup)

        async def sweep() -> None:
            while True:
                await asyncio.sleep(settings.cleanup_interval_seconds)
                try:
                    await run_in_threadpool(active_service.store.cleanup)
                except Exception:
                    logger.error("cleanup_sweep_failed")

        task = asyncio.create_task(sweep())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        if owned_llm:
            owned_llm.close()
        if distributed:
            distributed.close()
        await run_in_threadpool(flush_telemetry)

    app = FastAPI(title="ContractIQ RAG Backend", version="0.3.0", lifespan=lifespan)
    app.state.service = active_service
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"], expose_headers=["X-Request-ID", "Retry-After"],
    )
    if distributed is not None:
        app.add_middleware(AuthMiddleware, verifier=verifier or SupabaseVerifier(settings),
                           limiter=RedisLimiter(distributed, settings.rate_limit_requests, settings.rate_limit_window_seconds))
    app.add_middleware(SecurityMiddleware, settings=settings,
                       limiter=RedisLimiter(distributed, max(120, settings.rate_limit_requests * 4), settings.rate_limit_window_seconds) if distributed is not None else None)

    def error_response(request: Request, status: int, detail: str) -> JSONResponse:
        return JSONResponse(
            {"detail": detail, "request_id": getattr(request.state, "request_id", "unavailable")},
            status_code=status,
        )

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        return error_response(request, exc.status, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(request, 422, "Invalid request fields.")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error_response(request, exc.status_code, "Request could not be processed.")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unavailable")
        logger.error("request_failed request_id=%s error_type=%s", request_id, type(exc).__name__)
        report_error(type(exc).__name__, request_id)
        response = error_response(request, 500, "An internal error occurred. Please retry.")
        response.headers.update({"X-Request-ID": request_id, "Cache-Control": "no-store"})
        origin = request.headers.get("origin")
        if origin in settings.cors_origins:
            response.headers.update({"Access-Control-Allow-Origin": origin, "Vary": "Origin"})
        return response

    @app.post("/upload", response_model=None)
    async def upload(file: Annotated[UploadFile, File()]) -> DocumentMetadata | JSONResponse:
        try:
            content = await file.read(settings.max_upload_bytes + 1)
            filename = (file.filename or "document").replace("\\", "/").rsplit("/", 1)[-1]
            filename = "".join(char for char in filename if char.isprintable())[:200]
            if len(content) > settings.max_upload_bytes:
                raise ServiceError(413, "Upload exceeds the configured size limit.")
            if ingestion is not None:
                ticket = await run_in_threadpool(ingestion.submit, filename, content)
                return JSONResponse(ticket, status_code=202)
            return await run_in_threadpool(bounded, lambda: active_service.ingest_document(filename, content))
        finally:
            await file.close()

    @app.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        return await run_in_threadpool(bounded, lambda: active_service.get_answer(request))

    @app.post("/benefits", response_model=BenefitsResponse)
    async def benefits(request: DocumentRequest) -> BenefitsResponse:
        return await run_in_threadpool(bounded, lambda: active_service.analyze_benefits(str(request.doc_id)))

    @app.post("/audit", response_model=AuditResponse)
    async def audit(request: AuditRequest) -> AuditResponse:
        return await run_in_threadpool(bounded, lambda: active_service.audit(str(request.doc_id), request.india))

    @app.post("/compare", response_model=CompareResponse)
    async def compare(request: CompareRequest) -> CompareResponse:
        return await run_in_threadpool(bounded, lambda: active_service.compare(str(request.before_id), str(request.after_id)))

    @app.post("/chat/stream")
    async def stream_chat(body: ChatRequest, request: Request) -> StreamingResponse:
        await run_in_threadpool(active_service.store.get, str(body.doc_id))
        cancelled = threading.Event()
        messages: queue.Queue[tuple[str, object] | None] = queue.Queue(maxsize=32)
        request_id = request.state.request_id

        def send(value: tuple[str, object] | None) -> None:
            while not cancelled.is_set():
                try:
                    messages.put(value, timeout=0.1)
                    return
                except queue.Full:
                    continue

        def produce() -> None:
            def consume() -> None:
                for event in active_service.stream_answer(body, cancelled):
                    if cancelled.is_set():
                        break
                    send(event)
            try:
                bounded(consume)
            except ServiceError as exc:
                send(("error", {"detail": exc.message, "status": exc.status, "request_id": request_id}))
            except Exception as exc:
                logger.error("stream_failed request_id=%s error_type=%s", request_id, type(exc).__name__)
                send(("error", {"detail": "The streamed answer could not be completed.", "status": 500, "request_id": request_id}))
            finally:
                send(None)

        async def events() -> AsyncIterator[str]:
            worker = asyncio.create_task(run_in_threadpool(produce))
            heartbeat = 0
            try:
                while True:
                    try:
                        value = messages.get_nowait()
                    except queue.Empty:
                        await asyncio.sleep(0.1)
                        heartbeat += 1
                        if heartbeat >= 100:
                            heartbeat = 0
                            yield ": keepalive\n\n"
                        continue
                    if value is None:
                        break
                    kind, payload = value
                    yield f"event: {kind}\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"
            finally:
                cancelled.set()
                # Provider read timeout bounds shutdown if a disconnect happens mid-read.
                worker.add_done_callback(lambda finished: finished.exception() if not finished.cancelled() else None)

        return StreamingResponse(events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @app.get("/document/{doc_id}/source", response_model=DocumentRecord)
    def source(doc_id: UUID) -> DocumentRecord:
        record = active_service.store.get(str(doc_id))
        if not record.pages:
            raise ServiceError(409, "Re-upload this older document to enable source locations.")
        return record

    @app.get("/document/{doc_id}/file")
    def source_file(doc_id: UUID) -> Response:
        return Response(active_service.store.pdf(str(doc_id)), media_type="application/pdf", headers={
            "Content-Disposition": 'attachment; filename="contract.pdf"',
        })

    @app.get("/document/{doc_id}", response_model=DocumentMetadata)
    def document(doc_id: UUID) -> DocumentMetadata:
        return active_service.store.get(str(doc_id)).metadata

    @app.delete("/document/{doc_id}")
    def remove_document(doc_id: UUID) -> dict[str, str]:
        active_service.store.delete(str(doc_id))
        return {"deleted": str(doc_id)}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ingestion/{doc_id}")
    def ingestion_status(doc_id: UUID) -> dict[str, object]:
        if not isinstance(active_service.store, PostgresStore):
            raise ServiceError(404, "Background ingestion is unavailable in local mode.")
        return active_service.store.status(str(doc_id))

    @app.get("/document/{doc_id}/download")
    def signed_download(doc_id: UUID) -> dict[str, object]:
        if not isinstance(active_service.store, PostgresStore):
            raise ServiceError(404, "Signed downloads are unavailable in local mode.")
        return active_service.store.download(str(doc_id))

    @app.get("/ready")
    def ready() -> dict[str, str]:
        if isinstance(active_service.store, PostgresStore):
            try:
                with active_service.store.connection() as conn:
                    conn.execute("SELECT 1 FROM documents LIMIT 1")
                assert distributed is not None
                distributed.ping()
                active_service.store.objects.client.head_bucket(Bucket=settings.s3_bucket)
            except Exception as exc:
                raise ServiceError(503, "A required infrastructure service is unavailable.") from exc
        return {"status": "ready", "mode": settings.app_mode}

    return app


load_dotenv()
app = create_app()
