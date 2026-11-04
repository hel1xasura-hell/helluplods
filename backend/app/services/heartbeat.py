"""Worker heartbeats in Redis so the dashboard can show real worker status."""
import time

import redis

from app.core.config import get_settings

KEY = "hell:workers"
TTL_SECONDS = 90


def _client() -> "redis.Redis":
    return redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1)


def beat(worker_name: str, client=None) -> None:
    (client or _client()).zadd(KEY, {worker_name: time.time()})


def online_workers(client=None, now: float | None = None) -> list[str]:
    """Empty list when Redis is unreachable (reported as 'not connected', never as online)."""
    try:
        c = client or _client()
        cutoff = (now or time.time()) - TTL_SECONDS
        return [w.decode() if isinstance(w, bytes) else w for w in c.zrangebyscore(KEY, cutoff, "+inf")]
    except Exception:
        return []
