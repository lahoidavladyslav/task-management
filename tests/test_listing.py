from httpx import AsyncClient

from tests.helpers import API, change_status, in_days


async def titles(client: AsyncClient, account, **params) -> list[str]:
    response = await client.get(f"{API}/tasks", params=params, headers=account.headers)
    assert response.status_code == 200, response.text
    return [task["title"] for task in response.json()["items"]]


async def test_default_order_is_priority_then_nearest_deadline(
    client: AsyncClient, alice, create_task
) -> None:
    await create_task(alice, title="low-soon", priority="low", deadline=in_days(1))
    await create_task(alice, title="high-late", priority="high", deadline=in_days(5))
    await create_task(alice, title="medium", priority="medium", deadline=in_days(2))
    await create_task(alice, title="high-soon", priority="high", deadline=in_days(1))

    assert await titles(client, alice) == ["high-soon", "high-late", "medium", "low-soon"]


async def test_sorting_by_deadline_and_creation_date(
    client: AsyncClient, alice, create_task
) -> None:
    await create_task(alice, title="first", deadline=in_days(9))
    await create_task(alice, title="second", deadline=in_days(3))
    await create_task(alice, title="third", deadline=in_days(6))

    assert await titles(client, alice, sort="deadline") == ["second", "third", "first"]
    assert await titles(client, alice, sort="-deadline") == ["first", "third", "second"]
    assert await titles(client, alice, sort="created_at") == ["first", "second", "third"]
    assert await titles(client, alice, sort="-created_at") == ["third", "second", "first"]


async def test_sort_by_priority_ascending(client: AsyncClient, alice, create_task) -> None:
    await create_task(alice, title="high", priority="high")
    await create_task(alice, title="low", priority="low")
    await create_task(alice, title="medium", priority="medium")

    assert await titles(client, alice, sort="priority") == ["low", "medium", "high"]


async def test_invalid_sort_field_is_rejected(client: AsyncClient, alice) -> None:
    response = await client.get(f"{API}/tasks", params={"sort": "title"}, headers=alice.headers)

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_sort"


async def test_search_matches_title_and_description_case_insensitively(
    client: AsyncClient, alice, create_task
) -> None:
    await create_task(alice, title="Fix login bug")
    await create_task(alice, title="Infrastructure", description="Update the Kubernetes manifests")
    await create_task(alice, title="Unrelated")

    assert await titles(client, alice, search="LOGIN") == ["Fix login bug"]
    assert await titles(client, alice, search="kubernetes") == ["Infrastructure"]
    assert await titles(client, alice, search="nothing-matches") == []


async def test_search_treats_wildcards_literally(client: AsyncClient, alice, create_task) -> None:
    await create_task(alice, title="Reach 100% coverage")
    await create_task(alice, title="Reach 1000 coverage")
    await create_task(alice, title="snake_case rename")
    await create_task(alice, title="snakeXcase rename")

    assert await titles(client, alice, search="100%") == ["Reach 100% coverage"]
    assert await titles(client, alice, search="snake_case") == ["snake_case rename"]


async def test_filter_by_status_and_priority(client: AsyncClient, alice, bob, create_task) -> None:
    backlog = await create_task(alice, title="backlog", priority="low")
    started = await create_task(alice, title="started", priority="high", assignee_id=bob.id)
    cancelled = await create_task(alice, title="cancelled", priority="high")
    await change_status(client, alice, started["id"], "in_progress")
    await change_status(client, alice, cancelled["id"], "cancelled")

    assert await titles(client, alice, status="backlog") == ["backlog"]
    assert await titles(client, alice, status=["in_progress", "cancelled"]) == [
        "started",
        "cancelled",
    ]
    assert await titles(client, alice, priority="high") == ["started", "cancelled"]
    assert await titles(client, alice, priority="high", status="cancelled") == ["cancelled"]
    assert backlog["status"] == "backlog"


async def test_filter_by_assignee(client: AsyncClient, alice, bob, create_task) -> None:
    await create_task(alice, title="for bob", assignee_id=bob.id)
    await create_task(alice, title="for alice", assignee_id=alice.id)
    await create_task(alice, title="unassigned")

    assert await titles(client, alice, assignee_id=bob.id) == ["for bob"]
    assert await titles(client, alice, assignee_id=alice.id) == ["for alice"]


async def test_filter_by_deadline_range(client: AsyncClient, alice, create_task) -> None:
    await create_task(alice, title="in 1 day", deadline=in_days(1))
    await create_task(alice, title="in 5 days", deadline=in_days(5))
    await create_task(alice, title="in 10 days", deadline=in_days(10))

    assert await titles(client, alice, deadline_from=in_days(3), deadline_to=in_days(7)) == [
        "in 5 days"
    ]
    assert await titles(client, alice, deadline_from=in_days(3), sort="deadline") == [
        "in 5 days",
        "in 10 days",
    ]
    assert await titles(client, alice, deadline_to=in_days(3)) == ["in 1 day"]


async def test_inverted_deadline_range_is_rejected(client: AsyncClient, alice) -> None:
    response = await client.get(
        f"{API}/tasks",
        params={"deadline_from": in_days(5), "deadline_to": in_days(1)},
        headers=alice.headers,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_deadline_range"


async def test_pagination_metadata(client: AsyncClient, alice, create_task) -> None:
    for number in range(5):
        await create_task(alice, title=f"task {number}", deadline=in_days(number + 1))

    response = await client.get(
        f"{API}/tasks",
        params={"page": 3, "page_size": 2, "sort": "deadline"},
        headers=alice.headers,
    )

    body = response.json()
    assert [task["title"] for task in body["items"]] == ["task 4"]
    assert (body["total"], body["page"], body["page_size"], body["pages"]) == (5, 3, 2, 3)


async def test_pagination_bounds_are_validated(client: AsyncClient, alice) -> None:
    for params in ({"page": 0}, {"page_size": 0}, {"page_size": 101}):
        response = await client.get(f"{API}/tasks", params=params, headers=alice.headers)
        assert response.status_code == 422


async def test_page_number_beyond_the_supported_range_is_a_validation_error(
    client: AsyncClient, alice
) -> None:
    response = await client.get(f"{API}/tasks", params={"page": 10**20}, headers=alice.headers)

    assert response.status_code == 422
