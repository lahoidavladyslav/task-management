from datetime import timedelta

import pytest_asyncio
from httpx import AsyncClient

from app.core.clock import utcnow
from app.domain.task import TaskPriority, TaskStatus
from app.services.overdue import cancel_overdue_tasks
from tests.helpers import API

DAY = timedelta(days=1)


@pytest_asyncio.fixture
async def seeded(alice, insert_task) -> dict[str, int]:
    """Six tasks: two are overdue and still active, two are finished."""
    now = utcnow()
    return {
        "backlog_high": await insert_task(
            alice.id, status=TaskStatus.BACKLOG, priority=TaskPriority.HIGH, deadline=now + DAY
        ),
        "in_progress_medium": await insert_task(
            alice.id,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.MEDIUM,
            deadline=now + DAY,
        ),
        "review_low_overdue": await insert_task(
            alice.id, status=TaskStatus.REVIEW, priority=TaskPriority.LOW, deadline=now - 2 * DAY
        ),
        "done_high": await insert_task(
            alice.id, status=TaskStatus.DONE, priority=TaskPriority.HIGH, deadline=now - 3 * DAY
        ),
        "cancelled_low": await insert_task(
            alice.id, status=TaskStatus.CANCELLED, priority=TaskPriority.LOW, deadline=now - DAY
        ),
        "backlog_medium_overdue": await insert_task(
            alice.id, status=TaskStatus.BACKLOG, priority=TaskPriority.MEDIUM, deadline=now - DAY
        ),
    }


async def test_stats(client: AsyncClient, alice, seeded) -> None:
    response = await client.get(f"{API}/tasks/stats", headers=alice.headers)

    assert response.status_code == 200
    assert response.json() == {
        "total": 6,
        "by_status": {"backlog": 2, "in_progress": 1, "review": 1, "done": 1, "cancelled": 1},
        "by_priority": {"low": 2, "medium": 2, "high": 2},
        "overdue": 2,
        "active": 4,
    }


async def test_stats_for_an_empty_system(client: AsyncClient, alice) -> None:
    response = await client.get(f"{API}/tasks/stats", headers=alice.headers)

    body = response.json()
    assert body["total"] == body["overdue"] == body["active"] == 0
    assert set(body["by_status"]) == {"backlog", "in_progress", "review", "done", "cancelled"}
    assert set(body["by_priority"]) == {"low", "medium", "high"}


async def test_overdue_endpoint_lists_only_unfinished_late_tasks(
    client: AsyncClient, alice, seeded
) -> None:
    response = await client.get(f"{API}/tasks/overdue", headers=alice.headers)

    assert response.status_code == 200
    body = response.json()
    assert [task["id"] for task in body["items"]] == [
        seeded["review_low_overdue"],
        seeded["backlog_medium_overdue"],
    ]
    assert all(task["is_overdue"] for task in body["items"])
    assert body["total"] == 2


async def test_worker_cancels_only_overdue_active_tasks(
    client: AsyncClient, session_factory, alice, seeded
) -> None:
    assert await cancel_overdue_tasks(session_factory) == 2

    async def status_of(name: str) -> str:
        response = await client.get(f"{API}/tasks/{seeded[name]}", headers=alice.headers)
        return response.json()["status"]

    assert await status_of("review_low_overdue") == "cancelled"
    assert await status_of("backlog_medium_overdue") == "cancelled"
    assert await status_of("backlog_high") == "backlog"
    assert await status_of("in_progress_medium") == "in_progress"
    assert await status_of("done_high") == "done"

    overdue = await client.get(f"{API}/tasks/overdue", headers=alice.headers)
    assert overdue.json()["total"] == 0


async def test_worker_is_idempotent(session_factory, alice, seeded) -> None:
    assert await cancel_overdue_tasks(session_factory) == 2
    assert await cancel_overdue_tasks(session_factory) == 0
