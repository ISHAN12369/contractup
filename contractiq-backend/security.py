"""ASGI guard runs before multipart parsing; rejects oversized streamed bodies."""

import time
from collections.abc import Callable
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config import Settings


class RateLimiter:
    def __init__(self, limit: int, window: int, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.buckets: dict[str, tuple[float, int]] = {}

    def allow(self, key: str) -> bool:
        now = self.clock()
        self.buckets = {k: v for k, v in self.buckets.items() if v[0] > now}
        expiry, count = self.buckets.get(key, (now + self.window, 0))
        if count >= self.limit or (key not in self.buckets and len(self.buckets) >= 10_000):
            return False
        self.buckets[key] = (expiry, count + 1)
        return True


class SecurityMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings):
        self.app, self.settings = app, settings
        self.limiter = RateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def tagged_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"x-request-id", request_id.encode()),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ])
                if origin in self.settings.cors_origins and not any(
                    name == b"access-control-allow-origin" for name, _ in headers
                ):
                    headers.extend([
                        (b"access-control-allow-origin", origin.encode("latin-1")),
                        (b"access-control-expose-headers", b"X-Request-ID, Retry-After"),
                        (b"vary", b"Origin"),
                    ])
                message["headers"] = headers
            await send(message)

        async def reject(status: int, detail: str, retry: bool = False) -> None:
            response = JSONResponse(
                {"detail": detail, "request_id": request_id}, status_code=status,
                headers={"Retry-After": str(self.settings.rate_limit_window_seconds)} if retry else {},
            )
            await response(scope, receive, tagged_send)

        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode("latin-1")
        if origin and origin not in self.settings.cors_origins:
            await reject(403, "Origin is not allowed.")
            return
        if scope["path"] != "/health" and scope["method"] != "OPTIONS":
            peer = scope.get("client")
            if not self.limiter.allow(peer[0] if peer else "unknown"):
                await reject(429, "Too many requests. Please try later.", retry=True)
                return
        limit = self.settings.max_upload_bytes + 65536 if scope["path"] == "/upload" else 65536
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            await reject(400, "Invalid content length.")
            return
        if declared < 0 or declared > limit:
            await reject(413, "Request exceeds the configured size limit.")
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > limit:
                await reject(413, "Request exceeds the configured size limit.")
                return
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, tagged_send)
