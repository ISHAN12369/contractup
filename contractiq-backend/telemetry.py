"""Opt-in metadata-only telemetry. Never export contract text, tokens or exceptions."""
import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from config import Settings

_langfuse: Any = None
_sentry_enabled = False
current_request_id: ContextVar[str] = ContextVar("request_id", default="")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = str(record.msg).split(" ", 1)[0]
        if event not in {"request_completed", "request_failed", "stream_failed", "cleanup_sweep_failed",
                         "document_cleanup_failed", "object_cleanup_pending", "provider_call", "telemetry_unavailable"}:
            event = "library_event"
        fields = {k: getattr(record, k) for k in ("request_id", "route", "status", "duration_ms") if hasattr(record, k)}
        return json.dumps({"time": datetime.now(UTC).isoformat(), "level": record.levelname, "event": event, **fields}, allow_nan=False)


def scrub_event(event: Any, hint: Any) -> dict[str, Any]:
    # Reconstruct an allowlist rather than trying to remove every possible SDK context.
    return {"event_id": event.get("event_id"), "level": "error", "message": "ContractIQ operation failed",
            "tags": {k: v for k, v in event.get("tags", {}).items() if k in {"error_type", "request_id"}}}


def configure_telemetry(settings: Settings) -> None:
    global _langfuse, _sentry_enabled
    logger = logging.getLogger()
    if not any(getattr(handler, "contractiq", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler.contractiq = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "rq.worker"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
    if not settings.telemetry_enabled:
        return
    if settings.sentry_dsn:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.sentry_dsn, send_default_pii=False, default_integrations=False,
                        auto_enabling_integrations=False, traces_sample_rate=0,
                        max_request_body_size="never", before_send=scrub_event)
        _sentry_enabled = True
    if settings.langfuse_public_key and settings.langfuse_secret_key and _langfuse is None:
        from langfuse import Langfuse
        _langfuse = Langfuse(public_key=settings.langfuse_public_key, secret_key=settings.langfuse_secret_key,
                            base_url=settings.langfuse_base_url, timeout=5)


def report_error(error_type: str, request_id: str) -> None:
    if _sentry_enabled:
        import sentry_sdk
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("error_type", error_type)
            scope.set_tag("request_id", request_id)
            sentry_sdk.capture_message("ContractIQ operation failed", level="error")


@contextmanager
def provider_span(provider: str, model: str) -> Iterator[dict[str, int]]:
    usage: dict[str, int] = {}
    manager: Any = None
    observation: Any = None
    success, started = False, time.monotonic()
    if _langfuse is not None:
        try:
            request_id = current_request_id.get()
            manager = _langfuse.start_as_current_observation(name="provider-call", as_type="generation",
                        model=model, metadata={"provider": provider, "request_id": request_id},
                        trace_context={"trace_id": sha256(request_id.encode()).hexdigest()[:32]} if request_id else None)
            observation = manager.__enter__()
        except Exception:
            manager = None
    try:
        yield usage
        success = True
    finally:
        logging.getLogger(__name__).info("provider_call", extra={"request_id": current_request_id.get(), "duration_ms": round((time.monotonic() - started) * 1000, 2), "status": "ok" if success else "failed"})
        if manager is not None:
            try:
                observation.update(usage_details=usage or None, level="DEFAULT" if success else "ERROR",
                                   metadata={"provider": provider, "success": success, "request_id": current_request_id.get()})
                manager.__exit__(None, None, None)  # Do not attach exception messages/stack locals.
            except Exception:
                logging.getLogger(__name__).warning("telemetry_unavailable")


def flush_telemetry() -> None:
    try:
        if _langfuse is not None:
            _langfuse.flush()
        if _sentry_enabled:
            import sentry_sdk
            sentry_sdk.flush(timeout=5)
    except Exception:
        logging.getLogger(__name__).warning("telemetry_unavailable")
