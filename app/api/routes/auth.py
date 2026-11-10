from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import AuthServiceDep, enforce_auth_rate_limit
from app.models import User
from app.schemas.auth import Token
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(enforce_auth_rate_limit)])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, service: AuthServiceDep) -> User:
    return await service.register(payload)


@router.post(
    "/login",
    response_model=Token,
    summary="Obtain an access token",
    description="OAuth2 password flow: send the e-mail in the `username` form field.",
)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], service: AuthServiceDep
) -> Token:
    user = await service.authenticate(form.username, form.password)
    return service.issue_token(user)
