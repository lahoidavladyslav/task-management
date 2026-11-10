from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.repositories.users import UserRepository
from app.schemas.auth import Token
from app.schemas.user import MAX_PASSWORD_LENGTH, UserCreate


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._users = UserRepository(session)

    async def register(self, data: UserCreate) -> User:
        email = data.email.lower()
        if await self._users.get_by_email(email) is not None:
            raise self._email_taken()

        user = User(
            email=email,
            full_name=data.full_name,
            hashed_password=await hash_password(data.password),
        )
        try:
            await self._users.add(user)
            await self._session.commit()
        except IntegrityError:
            # Lost a race against a concurrent registration with the same e-mail.
            await self._session.rollback()
            raise self._email_taken() from None
        return user

    async def authenticate(self, email: str, password: str) -> User:
        if len(password) > MAX_PASSWORD_LENGTH:
            # Cannot match any stored password; skip the expensive hash computation.
            raise AuthenticationError("Incorrect e-mail or password", code="invalid_credentials")
        user = await self._users.get_by_email(email.strip().lower())
        password_ok = await verify_password(password, user.hashed_password if user else None)
        if user is None or not password_ok:
            raise AuthenticationError("Incorrect e-mail or password", code="invalid_credentials")
        return user

    def issue_token(self, user: User) -> Token:
        token, expires_in = create_access_token(user.id, self._settings)
        return Token(access_token=token, expires_in=expires_in)

    @staticmethod
    def _email_taken() -> ConflictError:
        return ConflictError("A user with this e-mail already exists", code="email_taken")
