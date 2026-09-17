"""Cache keys and invalidation for the todo list.

Kept out of the service layer because two routers need it -- todos (writes to
todos and tag links) and tags (a rename or delete changes what a cached page
renders, even though no todo row moved).
"""

import hashlib
import uuid

from app.core.redis import RedisClient
from app.services.todo_service import TodoFilters

CACHE_PREFIX = "todos:list"
CACHE_TTL = 300  # 5 minutes


def todo_list_cache_key(
    user_id: uuid.UUID, page: int, size: int, filters: TodoFilters
) -> str:
    """Cache key for one page of one user's todo list, under one filter set.

    The owner, the pagination window and *every* filter go into the key. A
    single shared key served one user's todos to all the others; a key that
    ignored a filter would serve the wrong rows to the same user. The
    fingerprint is hashed only to bound the key length -- it comes from the
    same TodoFilters object the query is built from, so the two cannot drift
    apart.
    """
    fingerprint = {"page": str(page), "size": str(size), **filters.cache_fingerprint()}
    raw = "&".join(f"{key}={value}" for key, value in sorted(fingerprint.items()))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{CACHE_PREFIX}:{user_id}:{digest}"


async def invalidate_todo_list_cache(redis: RedisClient, user_id: uuid.UUID) -> None:
    """Drop every cached page, under every filter, for this user.

    SCAN-based, so it never blocks the Redis event loop, and scoped to the one
    user so nobody else's cached pages are thrown away.
    """
    await redis.delete_pattern(f"{CACHE_PREFIX}:{user_id}:*")
