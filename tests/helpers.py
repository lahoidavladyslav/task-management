from datetime import timedelta

from app.core.clock import utcnow

API = "/api/v1"


def in_days(days: float) -> str:
    """ISO timestamp relative to now; negative values point to the past."""
    return (utcnow() + timedelta(days=days)).isoformat()


async def change_status(client, account, task_id: int, status: str):
    return await client.patch(
        f"{API}/tasks/{task_id}/status", json={"status": status}, headers=account.headers
    )
