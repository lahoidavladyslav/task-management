from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import Comment, User
from app.repositories.comments import CommentRepository
from app.repositories.tasks import TaskRepository
from app.schemas.comment import CommentCreate
from app.schemas.common import Pagination


class CommentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tasks = TaskRepository(session)
        self._comments = CommentRepository(session)

    async def add(self, task_id: int, author: User, data: CommentCreate) -> Comment:
        await self._ensure_task_exists(task_id)
        comment = Comment(task_id=task_id, author=author, body=data.body)
        await self._comments.add(comment)
        await self._session.commit()
        return comment

    async def list_for_task(
        self, task_id: int, pagination: Pagination
    ) -> tuple[list[Comment], int]:

    async def _ensure_task_exists(self, task_id: int) -> None:
        if not await self._tasks.exists(task_id):
            raise NotFoundError(f"Task {task_id} not found", code="task_not_found")
