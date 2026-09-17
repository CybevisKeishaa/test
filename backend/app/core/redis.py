import redis.asyncio as aioredis

from app.core.config import settings


class RedisClient:
    def __init__(self):
        self._redis = None

    async def initialize(self):
        self._redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )

    async def close(self):
        if self._redis:
            await self._redis.aclose()

    @property
    def client(self):
        return self._redis

    async def get(self, key: str) -> str | None:
        return await self._redis.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        await self._redis.set(key, value, ex=ex)

    async def delete(self, key: str):
        await self._redis.delete(key)

    async def delete_pattern(self, pattern: str) -> int:
        """Delete every key matching ``pattern``.

        Uses SCAN rather than KEYS so invalidation never blocks the Redis event
        loop on a large keyspace.
        """
        keys = [key async for key in self._redis.scan_iter(match=pattern, count=500)]
        if not keys:
            return 0
        await self._redis.delete(*keys)
        return len(keys)

    async def exists(self, key: str) -> bool:
        return bool(await self._redis.exists(key))


redis_client = RedisClient()
