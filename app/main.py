import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.api.routes import health
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import SessionFactory, engine
from app.workers.overdue import OverdueTaskWorker

DESCRIPTION = """
REST API for a team task tracker: tasks with a strict status workflow, comments,
search / filtering / sorting, reporting endpoints and a background job that
cancels tasks that missed their deadline.

Authenticate with **POST /api/v1/auth/register** and **POST /api/v1/auth/login**,
then use the *Authorize* button with the e-mail as the username.
"""

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.uses_placeholder_secret:
        logger.warning(
            "SECRET_KEY is a placeholder value. This is acceptable for local development "
            "only: anyone who knows it can forge tokens. Set ENVIRONMENT=production and "
            "a real SECRET_KEY before deploying."
        )

    worker: OverdueTaskWorker | None = None
    if settings.overdue_worker_enabled:
        worker = OverdueTaskWorker(SessionFactory, settings.overdue_check_interval_seconds)
        worker.start()

    yield

    if worker is not None:
        await worker.stop()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
