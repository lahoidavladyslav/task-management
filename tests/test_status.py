from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core.clock import utcnow
from app.models import Task
from tests.helpers import change_status


async def test_task_moves_through_the_whole_workflow(
    client: AsyncClient, alice, bob, create_task
) -> None:
    task = await create_task(alice, assignee_id=bob.id)

    for target in ("in_progress", "review", "done"):
        response = await change_status(client, alice, task["id"], target)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target


async def test_assignee_can_change_status(client: AsyncClient, alice, bob, create_task) -> None:
    task = await create_task(alice, assignee_id=bob.id)

    response = await change_status(client, bob, task["id"], "in_progress")

    assert response.status_code == 200


async def test_unrelated_user_cannot_change_status(
    client: AsyncClient, alice, bob, make_account, create_task
) -> None:
    task = await create_task(alice, assignee_id=bob.id)
    stranger = await make_account()

    response = await change_status(client, stranger, task["id"], "in_progress")

    assert response.status_code == 403
    assert response.json()["code"] == "not_task_participant"


@pytest.mark.parametrize(
    ("path", "target"),
    [
        ([], "review"),
        ([], "done"),
        ([], "backlog"),
        (["in_progress"], "backlog"),
        (["in_progress"], "done"),
        (["in_progress", "review"], "in_progress"),
        (["in_progress", "review"], "backlog"),
        (["in_progress", "review", "done"], "cancelled"),
        (["cancelled"], "in_progress"),
    ],
)
async def test_invalid_transitions_are_rejected(
    client: AsyncClient, alice, bob, create_task, path, target
) -> None:
    task = await create_task(alice, assignee_id=bob.id)
    for status in path:
        assert (await change_status(client, alice, task["id"], status)).status_code == 200

    response = await change_status(client, alice, task["id"], target)

    assert response.status_code == 409
    assert response.json()["code"] == "invalid_status_transition"


async def test_task_without_assignee_cannot_be_completed(
    client: AsyncClient, alice, create_task
) -> None:
    task = await create_task(alice)
    await change_status(client, alice, task["id"], "in_progress")
    await change_status(client, alice, task["id"], "review")

    response = await change_status(client, alice, task["id"], "done")

    assert response.status_code == 409
    assert response.json()["code"] == "assignee_required"


async def test_task_past_its_deadline_cannot_be_completed(
    client: AsyncClient, session_factory, alice, bob, create_task
) -> None:
    task = await create_task(alice, assignee_id=bob.id)
    await change_status(client, alice, task["id"], "in_progress")
    await change_status(client, alice, task["id"], "review")
    async with session_factory() as session:
        await session.execute(
            update(Task).where(Task.id == task["id"]).values(deadline=utcnow() - timedelta(hours=1))
        )
        await session.commit()

    response = await change_status(client, alice, task["id"], "done")

    assert response.status_code == 409
    assert response.json()["code"] == "deadline_passed"


async def test_unknown_status_value_is_rejected(client: AsyncClient, alice, create_task) -> None:
    task = await create_task(alice)

    response = await change_status(client, alice, task["id"], "archived")

    assert response.status_code == 422


async def test_status_change_on_missing_task(client: AsyncClient, alice) -> None:
    response = await change_status(client, alice, 424242, "in_progress")

    assert response.status_code == 404
