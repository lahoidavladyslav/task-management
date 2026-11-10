from httpx import AsyncClient

from tests.helpers import API, change_status


async def test_comments_are_listed_oldest_first_with_authors(
    client: AsyncClient, alice, bob, create_task
) -> None:
    task = await create_task(alice, assignee_id=bob.id)
    url = f"{API}/tasks/{task['id']}/comments"

    first = await client.post(url, json={"body": "Starting on this"}, headers=bob.headers)
    second = await client.post(url, json={"body": "Thanks!"}, headers=alice.headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["author"]["id"] == bob.id

    listing = await client.get(url, headers=alice.headers)

    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 2
    assert [c["body"] for c in body["items"]] == ["Starting on this", "Thanks!"]
    assert [c["author"]["id"] for c in body["items"]] == [bob.id, alice.id]


async def test_comments_are_paginated(client: AsyncClient, alice, create_task) -> None:
    task = await create_task(alice)
    url = f"{API}/tasks/{task['id']}/comments"
    for number in range(3):
        await client.post(url, json={"body": f"Comment {number}"}, headers=alice.headers)

    page = await client.get(url, params={"page": 2, "page_size": 2}, headers=alice.headers)

    body = page.json()
    assert [c["body"] for c in body["items"]] == ["Comment 2"]
    assert (body["total"], body["pages"]) == (3, 2)


async def test_comment_on_missing_task_returns_404(client: AsyncClient, alice) -> None:
    created = await client.post(
        f"{API}/tasks/424242/comments", json={"body": "Hello?"}, headers=alice.headers
    )
    listed = await client.get(f"{API}/tasks/424242/comments", headers=alice.headers)

    assert created.status_code == listed.status_code == 404


async def test_blank_comment_is_rejected(client: AsyncClient, alice, create_task) -> None:
    task = await create_task(alice)

    response = await client.post(
        f"{API}/tasks/{task['id']}/comments", json={"body": "   "}, headers=alice.headers
    )

    assert response.status_code == 422


async def test_cancelled_task_still_accepts_comments(
    client: AsyncClient, alice, create_task
) -> None:
    task = await create_task(alice)
    await change_status(client, alice, task["id"], "cancelled")

    response = await client.post(
        f"{API}/tasks/{task['id']}/comments",
        json={"body": "Cancelled because of the new scope"},
        headers=alice.headers,
    )

    assert response.status_code == 201
