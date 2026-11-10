import asyncio
import itertools
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://taskmanager:taskmanager@localhost:5432/taskmanager"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")
os.environ["OVERDUE_WORKER_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.clock import utcnow
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models import Task
from tests.helpers import API, in_days


def _test_database_url() -> URL:
    explicit = os.environ.get("TEST_DATABASE_URL")
    url = make_url(explicit or os.environ["DATABASE_URL"])
    if explicit is None:
        url = url.set(database=f"{url.database}_test")
    if "test" not in (url.database or ""):
        raise RuntimeError(
            f"Refusing to run tests against '{url.database}': the test database name "
            "must contain 'test' because the schema is dropped between tests."
        )
    return url


TEST_DATABASE_URL = _test_database_url()


async def _ensure_database_exists(url: URL) -> None:
    admin = create_async_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        async with admin.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        await admin.dispose()


@pytest.fixture(scope="session")
def _database() -> None:
    asyncio.run(_ensure_database_exists(TEST_DATABASE_URL))


@pytest_asyncio.fixture
async def engine(_database: None) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


@dataclass(frozen=True)
class Account:
    id: int
    email: str
    headers: dict[str, str]


@pytest_asyncio.fixture
async def make_account(client: AsyncClient) -> Callable[[], Awaitable[Account]]:
    counter = itertools.count(1)

    async def factory() -> Account:
        number = next(counter)
        email = f"user{number}@example.com"
        password = "Str0ngPassw0rd!"
        registered = await client.post(
            f"{API}/auth/register",
            json={"email": email, "password": password, "full_name": f"User {number}"},
        )
        assert registered.status_code == 201, registered.text
        login = await client.post(
            f"{API}/auth/login", data={"username": email, "password": password}
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        return Account(registered.json()["id"], email, {"Authorization": f"Bearer {token}"})

    return factory


@pytest_asyncio.fixture
async def alice(make_account: Callable[[], Awaitable[Account]]) -> Account:
    return await make_account()


@pytest_asyncio.fixture
async def bob(make_account: Callable[[], Awaitable[Account]]) -> Account:
    return await make_account()


@pytest_asyncio.fixture
async def create_task(client: AsyncClient) -> Callable[..., Awaitable[dict[str, Any]]]:
    async def factory(account: Account, **overrides: Any) -> dict[str, Any]:
        payload = {"title": "Write report", "priority": "medium", "deadline": in_days(7)}
        payload.update(overrides)
        response = await client.post(f"{API}/tasks", json=payload, headers=account.headers)
        assert response.status_code == 201, response.text
        return response.json()

    return factory


@pytest_asyncio.fixture
async def insert_task(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., Awaitable[int]]:
    """Insert a task straight into the database, bypassing API validation."""

    async def factory(author_id: int, **fields: Any) -> int:
        fields.setdefault("title", "Inserted directly")
        fields.setdefault("deadline", utcnow() + timedelta(days=1))
        async with session_factory() as session:
            task = Task(author_id=author_id, **fields)
            session.add(task)
            await session.commit()
            return task.id

    return factory
