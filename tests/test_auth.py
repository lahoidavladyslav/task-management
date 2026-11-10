from httpx import AsyncClient

from tests.conftest import Account
from tests.helpers import API

PASSWORD = "Str0ngPassw0rd!"


async def test_register_returns_public_profile(client: AsyncClient) -> None:
    response = await client.post(
        f"{API}/auth/register",
        json={"email": "Jane.Doe@Example.com", "password": PASSWORD, "full_name": "Jane Doe"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "jane.doe@example.com"
    assert body["full_name"] == "Jane Doe"
    assert "password" not in body
    assert "hashed_password" not in body


async def test_register_rejects_duplicate_email_ignoring_case(client: AsyncClient) -> None:
    payload = {"email": "jane@example.com", "password": PASSWORD, "full_name": "Jane"}
    assert (await client.post(f"{API}/auth/register", json=payload)).status_code == 201

    duplicate = await client.post(
        f"{API}/auth/register", json={**payload, "email": "JANE@example.com"}
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "email_taken"


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post(
        f"{API}/auth/register",
        json={"email": "jane@example.com", "password": "short", "full_name": "Jane"},
    )
    assert response.status_code == 422


async def test_login_returns_bearer_token(client: AsyncClient, alice: Account) -> None:
    response = await client.post(
        f"{API}/auth/login", data={"username": alice.email, "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] > 0


async def test_login_with_wrong_password_is_rejected(client: AsyncClient, alice: Account) -> None:
    response = await client.post(
        f"{API}/auth/login", data={"username": alice.email, "password": "wrong-password"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


async def test_login_with_unknown_email_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        f"{API}/auth/login", data={"username": "nobody@example.com", "password": PASSWORD}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


async def test_current_user_requires_valid_token(client: AsyncClient, alice: Account) -> None:
    me = await client.get(f"{API}/users/me", headers=alice.headers)
    assert me.status_code == 200
    assert me.json()["email"] == alice.email

    missing = await client.get(f"{API}/users/me")
    assert missing.status_code == 401
    assert missing.json()["code"] == "not_authenticated"

    garbage = await client.get(f"{API}/users/me", headers={"Authorization": "Bearer garbage"})
    assert garbage.status_code == 401
    assert garbage.json()["code"] == "invalid_token"


async def test_task_endpoints_are_protected(client: AsyncClient) -> None:
    assert (await client.get(f"{API}/tasks")).status_code == 401
    assert (await client.get(f"{API}/tasks/stats")).status_code == 401


async def test_login_with_an_oversized_password_is_rejected_as_invalid_credentials(
    client: AsyncClient, alice: Account
) -> None:
    response = await client.post(
        f"{API}/auth/login", data={"username": alice.email, "password": "x" * 5000}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
