import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import app
from app.repositories.tasks import TaskRepository
from tests.helpers import API

DATABASE_URL = "postgresql+asyncpg://u:p@localhost:5432/db"


async def test_unexpected_errors_use_the_standard_error_envelope(
    alice, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(self, task_id, *, for_update=False):
        raise RuntimeError("database exploded")

    monkeypatch.setattr(TaskRepository, "get", boom)
    transport = ASGITransport(app=app, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get(f"{API}/tasks/1", headers=alice.headers)

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error", "code": "internal_error"}


def test_production_rejects_a_placeholder_secret() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        Settings(
            _env_file=None,
            environment="production",
            database_url=DATABASE_URL,
            secret_key="change-me-in-production-please",
        )


def test_production_accepts_a_real_secret_and_development_accepts_a_placeholder() -> None:
    real = Settings(
        _env_file=None,
        environment="production",
        database_url=DATABASE_URL,
        secret_key="k3v9-Zq1x7Lm0Pw5Rt8Yb2Nc4Hd6Jf",
    )
    dev = Settings(
        _env_file=None,
        environment="development",
        database_url=DATABASE_URL,
        secret_key="change-me-in-production-please",
    )

    assert not real.uses_placeholder_secret
    assert dev.uses_placeholder_secret
