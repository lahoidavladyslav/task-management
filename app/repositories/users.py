from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas.common import Pagination


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int, *, for_update: bool = False) -> User | None:
        stmt = select(User).where(User.id == user_id)
        if for_update:
            # FOR NO KEY UPDATE: serializes concurrent assignments to the same user
            # without blocking unrelated foreign-key checks that reference the row.
            stmt = stmt.with_for_update(key_share=True)
        return await self._session.scalar(stmt)

    async def get_by_email(self, email: str) -> User | None:
        return await self._session.scalar(select(User).where(User.email == email))

    async def add(self, user: User) -> None:
        self._session.add(user)
        await self._session.flush()

    async def list_users(self, pagination: Pagination) -> tuple[list[User], int]:
        total = await self._session.scalar(select(func.count(User.id))) or 0
        stmt = select(User).order_by(User.id).limit(pagination.page_size).offset(pagination.offset)
        items = list((await self._session.scalars(stmt)).all())
        return items, total
