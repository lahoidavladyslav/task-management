import asyncio
from datetime import datetime

import pytest
from httpx import AsyncClient

from tests.conftest import Account
from tests.helpers import API, change_status, in_days


async def test_create_task_applies_defaults(client, alice, bob, create_task) -> None:
    task = await create_task(
        alice,
        title="  Prepare demo  ",
        description="Slides and speaker notes",
        priority="high",
        assignee_id=bob.id,
    )

    assert task["title"] == "Prepare demo"
    assert task["status"] == "backlog"
    assert task["priority"] == "high"
    assert task["author_id"] == alice.id
    assert task["assignee"]["id"] == bob.id
    assert task["is_overdue"] is False
    assert task["created_at"] and task["updated_at"]


async def test_create_task_without_assignee_is_allowed(client, alice, create_task) -> None:
    task = await create_task(alice)

    assert task["assignee_id"] is None
    assert task["assignee"] is None


async def test_create_task_rejects_deadline_in_the_past(client: AsyncClient, alice) -> None:
    response = await client.post(
        f"{API}/tasks",
        json={"title": "Too late", "deadline": in_days(-1)},
        headers=alice.headers,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "deadline_in_past"


async def test_create_task_rejects_unknown_assignee(client: AsyncClient, alice) -> None:
    response = await client.post(
        f"{API}/tasks",
        json={"title": "Orphan", "deadline": in_days(1), "assignee_id": 9999},
        headers=alice.headers,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "assignee_not_found"


async def test_create_task_rejects_blank_title(client: AsyncClient, alice) -> None:
    response = await client.post(
        f"{API}/tasks", json={"title": "   ", "deadline": in_days(1)}, headers=alice.headers
    )
    assert response.status_code == 422


async def test_get_task_and_missing_task(client: AsyncClient, alice, create_task) -> None:
    task = await create_task(alice)

    found = await client.get(f"{API}/tasks/{task['id']}", headers=alice.headers)
    assert found.status_code == 200
    assert found.json()["id"] == task["id"]

    missing = await client.get(f"{API}/tasks/424242", headers=alice.headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "task_not_found"


async def test_author_can_update_task(client: AsyncClient, alice, create_task) -> None:
    task = await create_task(alice, priority="low")

    response = await client.patch(
        f"{API}/tasks/{task['id']}",
        json={"title": "Renamed", "priority": "high", "deadline": in_days(14)},
        headers=alice.headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Renamed"
    assert body["priority"] == "high"
    assert datetime.fromisoformat(body["updated_at"]) > datetime.fromisoformat(task["updated_at"])


async def test_only_author_can_update_task(client: AsyncClient, alice, bob, create_task) -> None:
    task = await create_task(alice, assignee_id=bob.id)

    response = await client.patch(
        f"{API}/tasks/{task['id']}", json={"title": "Hijacked"}, headers=bob.headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "not_task_author"


async def test_update_rejects_deadline_in_the_past(client: AsyncClient, alice, create_task) -> None:
    task = await create_task(alice)

    response = await client.patch(
        f"{API}/tasks/{task['id']}", json={"deadline": in_days(-2)}, headers=alice.headers
    )

    assert response.status_code == 422
    assert response.json()["code"] == "deadline_in_past"


async def test_update_rejects_null_for_required_fields(
    client: AsyncClient, alice, create_task
) -> None:
    task = await create_task(alice)

    response = await client.patch(
        f"{API}/tasks/{task['id']}", json={"title": None}, headers=alice.headers
    )

    assert response.status_code == 422


async def test_untouched_past_deadline_does_not_block_other_edits(
    client: AsyncClient, alice, insert_task
) -> None:
    task_id = await insert_task(alice.id, deadline=datetime.fromisoformat(in_days(-3)))

    response = await client.patch(
        f"{API}/tasks/{task_id}", json={"title": "Still editable"}, headers=alice.headers
    )

    assert response.status_code == 200
    assert response.json()["is_overdue"] is True


@pytest.mark.parametrize("final_path", [["cancelled"], ["in_progress", "review", "done"]])
async def test_finished_tasks_cannot_be_edited(
    client: AsyncClient, alice, bob, create_task, final_path
) -> None:
    task = await create_task(alice, assignee_id=bob.id)
    for status in final_path:
        assert (await change_status(client, alice, task["id"], status)).status_code == 200

    response = await client.patch(
        f"{API}/tasks/{task['id']}", json={"title": "Too late"}, headers=alice.headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "task_not_editable"


async def test_assignee_is_locked_once_task_is_in_review(
    client: AsyncClient, alice, bob, create_task
) -> None:
    task = await create_task(alice, assignee_id=bob.id)
    await change_status(client, alice, task["id"], "in_progress")
    await change_status(client, alice, task["id"], "review")

    reassign = await client.patch(
        f"{API}/tasks/{task['id']}", json={"assignee_id": alice.id}, headers=alice.headers
    )
    assert reassign.status_code == 409
    assert reassign.json()["code"] == "assignee_locked"

    rename = await client.patch(
        f"{API}/tasks/{task['id']}", json={"title": "Review notes"}, headers=alice.headers
    )
    assert rename.status_code == 200


async def test_assignee_can_be_changed_and_cleared_before_review(
    client: AsyncClient, alice, bob, create_task
) -> None:
    task = await create_task(alice)

    assigned = await client.patch(
        f"{API}/tasks/{task['id']}", json={"assignee_id": bob.id}, headers=alice.headers
    )
    assert assigned.json()["assignee_id"] == bob.id

    cleared = await client.patch(
        f"{API}/tasks/{task['id']}", json={"assignee_id": None}, headers=alice.headers
    )
    assert cleared.status_code == 200
    assert cleared.json()["assignee"] is None


async def test_backlog_task_can_be_deleted(client: AsyncClient, alice, create_task) -> None:
    task = await create_task(alice)

    deleted = await client.delete(f"{API}/tasks/{task['id']}", headers=alice.headers)
    assert deleted.status_code == 204

    assert (await client.get(f"{API}/tasks/{task['id']}", headers=alice.headers)).status_code == 404


@pytest.mark.parametrize("path", [["in_progress"], ["in_progress", "review"]])
async def test_task_in_progress_or_review_cannot_be_deleted(
    client: AsyncClient, alice, bob, create_task, path
) -> None:
    task = await create_task(alice, assignee_id=bob.id)
    for status in path:
        await change_status(client, alice, task["id"], status)

    blocked = await client.delete(f"{API}/tasks/{task['id']}", headers=alice.headers)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "task_not_deletable"

    await change_status(client, alice, task["id"], "cancelled")
    deleted = await client.delete(f"{API}/tasks/{task['id']}", headers=alice.headers)
    assert deleted.status_code == 204


async def test_completed_task_can_be_deleted(client: AsyncClient, alice, bob, create_task) -> None:
    task = await create_task(alice, assignee_id=bob.id)
    for status in ("in_progress", "review", "done"):
        await change_status(client, alice, task["id"], status)

    deleted = await client.delete(f"{API}/tasks/{task['id']}", headers=alice.headers)
    assert deleted.status_code == 204


async def test_only_author_can_delete_task(client: AsyncClient, alice, bob, create_task) -> None:
    task = await create_task(alice, assignee_id=bob.id)

    response = await client.delete(f"{API}/tasks/{task['id']}", headers=bob.headers)

    assert response.status_code == 403


async def test_user_cannot_hold_more_than_ten_active_tasks(
    client: AsyncClient, alice: Account, bob: Account, create_task
) -> None:
    created = [await create_task(alice, title=f"Task {n}", assignee_id=bob.id) for n in range(10)]
    payload = {"title": "One too many", "deadline": in_days(3), "assignee_id": bob.id}

    rejected = await client.post(f"{API}/tasks", json=payload, headers=alice.headers)
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "active_tasks_limit_exceeded"

    # Cancelling a task frees a slot.
    await change_status(client, alice, created[0]["id"], "cancelled")
    accepted = await client.post(f"{API}/tasks", json=payload, headers=alice.headers)
    assert accepted.status_code == 201


async def test_reassigning_to_a_user_at_the_limit_is_rejected(
    client: AsyncClient, alice: Account, bob: Account, create_task
) -> None:
    for number in range(10):
        await create_task(alice, title=f"Task {number}", assignee_id=bob.id)
    unassigned = await create_task(alice, title="Floating")

    response = await client.patch(
        f"{API}/tasks/{unassigned['id']}", json={"assignee_id": bob.id}, headers=alice.headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "active_tasks_limit_exceeded"


async def test_parallel_assignments_cannot_exceed_the_active_limit(
    client: AsyncClient, alice: Account, bob: Account, insert_task
) -> None:
    for _ in range(9):
        await insert_task(alice.id, assignee_id=bob.id)
    payload = {"title": "Race", "deadline": in_days(3), "assignee_id": bob.id}

    responses = await asyncio.gather(
        *(client.post(f"{API}/tasks", json=payload, headers=alice.headers) for _ in range(5))
    )

    codes = sorted(response.status_code for response in responses)
    assert codes == [201, 409, 409, 409, 409]
