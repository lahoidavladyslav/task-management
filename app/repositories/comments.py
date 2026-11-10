from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Comment
from app.schemas.common import Pagination


class CommentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, comment: Comment) -> None:
        self._session.add(comment)
        await self._session.flush()

    async def list_for_task(
        self, task_id: int, pagination: Pagination
    ) -> tuple[list[Comment], int]:
        total = (
            await self._session.scalar(
                select(func.count(Comment.id)).where(Comment.task_id == task_id)
            )
            or 0
        )
        stmt = (
            select(Comment)
            .where(Comment.task_id == task_id)
            .order_by(Comment.created_at, Comment.id)
            .limit(pagination.page_size)
            .offset(pagination.offset)
        )
        items = list((await self._session.scalars(stmt)).all())
        return items, total
