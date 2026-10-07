"""Single-worker FastAPI application. Blocking parsing/model work runs off-loop."""

import asyncio
import logging
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from typing import Annotated, TypeVar
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from config import Settings
from errors import ServiceError
from llm import GroqLLM
from rag_pipeline import RAGService
from schemas import BenefitsResponse, ChatRequest, ChatResponse, DocumentMetadata, DocumentRequest
from security import SecurityMiddleware
from storage import ChromaIndex, DocumentStore

logger = logging.getLogger(__name__)
T = TypeVar("T")


def create_app(settings: Settings | None = None, service: RAGService | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    owned_llm: GroqLLM | None = None
    if service is None:
        store = DocumentStore(settings, ChromaIndex(settings.model_cache_dir))
        owned_llm = GroqLLM(settings)
        service = RAGService(settings, store, owned_llm)
    active_service = service
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

    app = FastAPI(title="ContractIQ RAG Backend", version="0.2.0", lifespan=lifespan)
    app.state.service = active_service
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"], expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(SecurityMiddleware, settings=settings)

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
        response = error_response(request, 500, "An internal error occurred. Please retry.")
        response.headers.update({"X-Request-ID": request_id, "Cache-Control": "no-store"})
        origin = request.headers.get("origin")
        if origin in settings.cors_origins:
            response.headers.update({"Access-Control-Allow-Origin": origin, "Vary": "Origin"})
        return response

    @app.post("/upload", response_model=DocumentMetadata)
    async def upload(file: Annotated[UploadFile, File()]) -> DocumentMetadata:
        try:
            content = await file.read(settings.max_upload_bytes + 1)
            filename = (file.filename or "document").replace("\\", "/").rsplit("/", 1)[-1]
            filename = "".join(char for char in filename if char.isprintable())[:200]
            return await run_in_threadpool(bounded, lambda: active_service.ingest_document(filename, content))
        finally:
            await file.close()

    @app.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        return await run_in_threadpool(bounded, lambda: active_service.get_answer(request))

    @app.post("/benefits", response_model=BenefitsResponse)
    async def benefits(request: DocumentRequest) -> BenefitsResponse:
        return await run_in_threadpool(bounded, lambda: active_service.analyze_benefits(str(request.doc_id)))

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

    return app


load_dotenv()
app = create_app()
