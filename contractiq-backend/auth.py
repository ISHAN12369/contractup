"""Supabase asymmetric JWT verification and request-scoped ownership."""
from contextvars import ContextVar
from typing import Any, Protocol
from uuid import UUID

import jwt
from jwt import PyJWKClient
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from config import Settings
from errors import ServiceError

current_owner: ContextVar[str | None] = ContextVar("contractiq_owner", default=None)


def owner_id() -> str:
    value = current_owner.get()
    if value is None:
        raise ServiceError(401, "Sign in to access your documents.")
    return value


class Verifier(Protocol):
    def verify(self, token: str) -> str: ...


class SupabaseVerifier:
    def __init__(self, settings: Settings):
        self.issuer = settings.supabase_url.rstrip("/") + "/auth/v1"
        self.keys = PyJWKClient(self.issuer + "/.well-known/jwks.json", cache_jwk_set=True,
                                lifespan=300, timeout=5)

    def verify(self, token: str) -> str:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in {"RS256", "ES256"} or not isinstance(header.get("kid"), str):
                raise ValueError("Unsupported signing method")
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256", "ES256"], audience="authenticated",
                                issuer=self.issuer, leeway=10,
                                options={"require": ["exp", "iat", "sub", "aud", "iss"]})
            if claims.get("role") != "authenticated":
                raise ValueError("Not an authenticated user")
            return str(UUID(claims["sub"]))
        except jwt.PyJWKClientConnectionError as exc:
            raise ServiceError(503, "Sign-in verification is temporarily unavailable.") from exc
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise ServiceError(401, "Your sign-in session is invalid or expired.") from exc


class AuthMiddleware:
    def __init__(self, app: ASGIApp, verifier: Verifier, limiter: Any):
        self.app, self.verifier, self.limiter = app, verifier, limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] != "http" or scope["path"] in {"/health", "/ready"} or scope["method"] == "OPTIONS"
                or (scope["path"] == "/share/read" and scope["method"] == "POST")):
            await self.app(scope, receive, send)
            return
        try:
            header = dict(scope.get("headers", [])).get(b"authorization", b"").decode("latin-1")
            if not header.startswith("Bearer ") or len(header) > 16384:
                raise ServiceError(401, "Sign in to access your documents.")
            owner = await run_in_threadpool(self.verifier.verify, header[7:])
            if not await run_in_threadpool(self.limiter.allow, "user:" + owner):
                raise ServiceError(429, "Too many requests. Please try later.")
        except ServiceError as exc:
            response = JSONResponse({"detail": exc.message, "request_id": scope.get("state", {}).get("request_id")},
                                    status_code=exc.status, headers={"Retry-After": str(self.limiter.window)} if exc.status == 429 else {})
            await response(scope, receive, send)
            return
        token = current_owner.set(owner)
        try:
            await self.app(scope, receive, send)
        finally:
            current_owner.reset(token)
