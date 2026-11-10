import math
from typing import Annotated

from fastapi import BackgroundTasks, Depends, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError, RateLimitError
from app.core.rate_limit import auth_limiter
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models import User
from app.repositories.users import UserRepository
from app.schemas.common import MAX_PAGE, Pagination
from app.services.auth import AuthService
from app.services.comments import CommentService
from app.services.tasks import TaskService

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

# auto_error is off so that missing credentials produce the same error shape as every other 401.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().api_v1_prefix}/auth/login", auto_error=False
)


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: SessionDep,
    settings: SettingsDep,
) -> User:
    if token is None:
        raise AuthenticationError("Not authenticated", code="not_authenticated")
    user = await UserRepository(session).get(decode_access_token(token, settings))
    if user is None:
        raise AuthenticationError("The user no longer exists", code="invalid_token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def enforce_auth_rate_limit(request: Request, settings: SettingsDep) -> None:
    """Throttle registration and login attempts per client address."""
    if not settings.rate_limit_enabled:
        return
    key = request.client.host if request.client else "unknown"
    retry_after = auth_limiter.check(
        key, settings.auth_rate_limit_attempts, settings.auth_rate_limit_window_seconds
    )
    if retry_after is not None:
        raise RateLimitError(
            "Too many authentication attempts, try again later",
            retry_after=max(1, math.ceil(retry_after)),
        )


def get_pagination(
    page: Annotated[int, Query(ge=1, le=MAX_PAGE, description="Page number, starting from 1")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> Pagination:
    return Pagination(page=page, page_size=page_size)


PaginationDep = Annotated[Pagination, Depends(get_pagination)]


def get_auth_service(session: SessionDep, settings: SettingsDep) -> AuthService:
    return AuthService(session, settings)


def get_task_service(
    session: SessionDep, settings: SettingsDep, background_tasks: BackgroundTasks
) -> TaskService:
    return TaskService(session, settings, background_tasks)


def get_comment_service(session: SessionDep) -> CommentService:
    return CommentService(session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
CommentServiceDep = Annotated[CommentService, Depends(get_comment_service)]
