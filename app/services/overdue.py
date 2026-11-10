import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import utcnow
from app.repositories.tasks import TaskRepository

logger = logging.getLogger(__name__)


async def cancel_overdue_tasks(
    session_factory: async_sessionmaker[AsyncSession], now: datetime | None = None
) -> int:
    """Cancel every unfinished task whose deadline has passed; returns how many were cancelled.

    A single UPDATE statement, so it is atomic and safe to run from several
    processes at once: a task can only be cancelled one time.
    """
    async with session_factory() as session:
        cancelled_ids = await TaskRepository(session).cancel_overdue(now or utcnow())
        await session.commit()

    if cancelled_ids:
        logger.info("Cancelled %d overdue task(s): %s", len(cancelled_ids), cancelled_ids)
    return len(cancelled_ids)
