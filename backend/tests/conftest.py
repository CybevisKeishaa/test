import fnmatch
import os
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Use SQLite for tests before app modules initialize their default engine.
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.api.deps import get_redis  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_maker = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class FakeRedis:
    """In-memory stand-in with the same surface as ``RedisClient``.

    A MagicMock whose ``get`` always returns ``None`` can never fail a caching
    test, because a stale read is exactly what it cannot reproduce. This stores
    values for real so cache hits, scoping and invalidation are all observable.
    """

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)

    async def delete_pattern(self, pattern: str) -> int:
        matched = [key for key in self.store if fnmatch.fnmatch(key, pattern)]
        for key in matched:
            del self.store[key]
        return len(matched)

    async def exists(self, key: str) -> bool:
        return key in self.store


fake_redis = FakeRedis()


@pytest.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fake_redis.store.clear()
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def override_get_redis() -> FakeRedis:
    return fake_redis


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_redis] = override_get_redis


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
def redis() -> FakeRedis:
    return fake_redis


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_maker() as session:
        yield session


async def register_user(
    client: AsyncClient, email: str, password: str = "password123"
) -> dict:
    """Register a user and return the raw token payload."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def auth_header_for(
    client: AsyncClient, email: str, password: str = "password123"
) -> dict[str, str]:
    """Register a user and return an Authorization header for them."""
    tokens = await register_user(client, email, password)
    return {"Authorization": f"Bearer {tokens['access_token']}"}
