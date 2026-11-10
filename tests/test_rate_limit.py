from httpx import AsyncClient

from app.core.config import get_settings
from app.core.rate_limit import SlidingWindowRateLimiter, auth_limiter
from app.main import app
from tests.helpers import API


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limiter_blocks_after_the_limit_and_reports_retry_delay() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(clock)

    assert limiter.check("ip", limit=2, window_seconds=60) is None
    clock.now += 10
    assert limiter.check("ip", limit=2, window_seconds=60) is None
    clock.now += 10

    retry_after = limiter.check("ip", limit=2, window_seconds=60)
    assert retry_after is not None
    assert round(retry_after) == 40


def test_limiter_allows_again_once_the_window_has_passed() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(clock)
    limiter.check("ip", limit=1, window_seconds=60)
    assert limiter.check("ip", limit=1, window_seconds=60) is not None

    clock.now += 61

    assert limiter.check("ip", limit=1, window_seconds=60) is None


def test_limiter_counts_each_key_separately() -> None:
    limiter = SlidingWindowRateLimiter(FakeClock())
    limiter.check("a", limit=1, window_seconds=60)

    assert limiter.check("a", limit=1, window_seconds=60) is not None
    assert limiter.check("b", limit=1, window_seconds=60) is None


async def test_auth_endpoints_return_429_with_retry_after(client: AsyncClient) -> None:
    limited = get_settings().model_copy(
        update={"rate_limit_enabled": True, "auth_rate_limit_attempts": 2}
    )
    app.dependency_overrides[get_settings] = lambda: limited
    auth_limiter.reset()
    try:
        credentials = {"username": "nobody@example.com", "password": "wrong-password"}
        first = await client.post(f"{API}/auth/login", data=credentials)
        second = await client.post(f"{API}/auth/login", data=credentials)
        third = await client.post(f"{API}/auth/login", data=credentials)
    finally:
        auth_limiter.reset()

    assert (first.status_code, second.status_code) == (401, 401)
    assert third.status_code == 429
    assert third.json()["code"] == "rate_limit_exceeded"
    assert int(third.headers["Retry-After"]) >= 1
