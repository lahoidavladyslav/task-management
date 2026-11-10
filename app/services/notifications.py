import logging

logger = logging.getLogger(__name__)


async def notify_assignee(task_id: int, title: str, assignee_email: str) -> None:
    """Hook for delivering assignment notifications (e-mail, webhook, chat).

    Runs as a FastAPI background task, after the response has been sent.
    Currently it only logs the event.
    """
    # The address is intentionally not logged (personal data); a real delivery
    # implementation would use `assignee_email` here.
    logger.info("Task #%s %r was assigned; notification queued", task_id, title)
