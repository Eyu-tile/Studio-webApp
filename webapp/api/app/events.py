"""Live events (job progress, new assets, versions) over Redis pub/sub, streamed to the browser as SSE.
Publishing is best effort: if Redis is down, the database still holds the truth and the page polls."""
import json
import logging
from functools import lru_cache

import redis

from .config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def _redis():
    return redis.Redis.from_url(get_settings().redis_url, socket_timeout=2)


def channel(project_id) -> str:
    return f"studio:project:{project_id}"


def publish(project_id, kind: str, data: dict) -> None:
    try:
        _redis().publish(channel(project_id), json.dumps({"type": kind, **data}, default=str))
    except redis.RedisError as e:  # pragma: no cover - depends on infra
        log.warning("event publish failed: %s", e)
