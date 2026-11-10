import asyncio
import contextlib
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.overdue import cancel_overdue_tasks

logger = logging.getLogger(__name__)


class OverdueTaskWorker:
    """Periodically cancels overdue tasks; lives for the lifetime of the application."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], interval_seconds: float
    ) -> None:
        self._session_factory = session_factory
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="overdue-task-worker")
            logger.info("Overdue task worker started (interval: %ss)", self._interval)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("Overdue task worker stopped")

    async def _run(self) -> None:
        while True:
            try:
                await cancel_overdue_tasks(self._session_factory)
            except Exception:
                # A failed sweep (e.g. the database restarting) must not kill the loop.
                logger.exception("Overdue task sweep failed")
            await asyncio.sleep(self._interval)
