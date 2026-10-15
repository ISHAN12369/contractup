"""Atomic distributed admission and short-lived, tenant-keyed retrieval caches."""
import hashlib
import json
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from errors import ServiceError

LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
return count <= tonumber(ARGV[1]) and 1 or 0
"""


class RedisLimiter:
    def __init__(self, redis: Redis, limit: int, window: int):
        self.redis, self.limit, self.window = redis, limit, window

    def allow(self, key: str) -> bool:
        identifier = hashlib.sha256(key.encode()).hexdigest()
        try:
            return bool(self.redis.eval(LIMIT_SCRIPT, 1, "ciq:limit:" + identifier, self.limit, self.window))
        except RedisError as exc:
            raise ServiceError(503, "Request admission is temporarily unavailable.") from exc


class RetrievalCache:
    def __init__(self, redis: Redis):
        self.redis = redis

    @staticmethod
    def key(owner: str, doc: str, question: str, k: int) -> str:
        data = json.dumps([owner, doc, question, k, "all-MiniLM-L6-v2:cosine:v1"])
        return "ciq:retrieval:" + hashlib.sha256(data.encode()).hexdigest()

    def get(self, key: str) -> Any:
        try:
            raw = self.redis.get(key)
            return json.loads(raw) if raw else None
        except (RedisError, ValueError, TypeError):
            return None

    def put(self, key: str, hits: list[tuple[str, float]], ttl: int) -> None:
        try:
            self.redis.setex(key, max(1, ttl), json.dumps(hits, allow_nan=False))
        except RedisError:
            pass  # Cache misses fall back to the tenant-filtered database, never bypass authorization.
