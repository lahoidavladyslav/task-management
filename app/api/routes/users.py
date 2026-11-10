from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, PaginationDep, SessionDep, get_current_user
from app.models import User
from app.repositories.users import UserRepository
from app.schemas.common import Page, build_page
from app.schemas.user import UserRead

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(get_current_user)])


@router.get("/me", response_model=UserRead, summary="Current user")
async def read_current_user(current_user: CurrentUser) -> User:
    return current_user


@router.get("", response_model=Page[UserRead], summary="List users")
async def list_users(session: SessionDep, pagination: PaginationDep) -> dict[str, Any]:
    users, total = await UserRepository(session).list(pagination)
    return build_page(users, total, pagination)
