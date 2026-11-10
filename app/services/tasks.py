from datetime import datetime

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.config import Settings
from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.domain.task import (
    ACTIVE_STATUSES,
    ASSIGNEE_LOCKED_STATUSES,
    FINAL_STATUSES,
    UNDELETABLE_STATUSES,
    TaskPriority,
    TaskStatus,
    can_transition,
)
from app.models import Task, User
from app.repositories.tasks import TaskRepository
from app.repositories.users import UserRepository
from app.schemas.common import Pagination
from app.schemas.task import TaskCreate, TaskStats, TaskUpdate
from app.schemas.task_query import SortSpec, TaskFilters
from app.services.notifications import notify_assignee


class TaskService:
    def __init__(
        self, session: AsyncSession, settings: Settings, background_tasks: BackgroundTasks
    ) -> None:
        self._session = session
        self._settings = settings
        self._background = background_tasks
        self._tasks = TaskRepository(session)
        self._users = UserRepository(session)

    async def create(self, author: User, data: TaskCreate) -> Task:
        self._ensure_deadline_not_in_past(data.deadline)
        assignee = await self._acquire_assignee(data.assignee_id)

        task = Task(
            title=data.title,
            description=data.description,
            priority=data.priority,
            status=TaskStatus.BACKLOG,
            deadline=data.deadline,
            author=author,
            assignee=assignee,
        )
        await self._tasks.add(task)
        await self._session.commit()

        self._notify_assigned(task)
        return task

    async def get(self, task_id: int) -> Task:
        task = await self._tasks.get(task_id)
        if task is None:
            raise self._not_found(task_id)
        return task

    async def update(self, task_id: int, actor: User, data: TaskUpdate) -> Task:
        task = await self._get_locked(task_id)
        self._ensure_author(task, actor)
        if task.status in FINAL_STATUSES:
            raise ConflictError(
                "Tasks in the Done or Cancelled status cannot be edited",
                code="task_not_editable",
            )

        changes = data.model_dump(exclude_unset=True)

        new_deadline = changes.get("deadline")
        if new_deadline is not None and new_deadline != task.deadline:
            self._ensure_deadline_not_in_past(new_deadline)

        reassigned = "assignee_id" in changes and changes["assignee_id"] != task.assignee_id
        new_assignee: User | None = None
        if reassigned:
            if task.status in ASSIGNEE_LOCKED_STATUSES:
                raise ConflictError(
                    f"The assignee cannot be changed once the task is in {task.status.value}",
                    code="assignee_locked",
                )
            # Resolved before any attribute is touched, so the capacity count
            # is not skewed by autoflushing a half-applied change.
            new_assignee = await self._acquire_assignee(changes["assignee_id"])

        for field in ("title", "description", "priority", "deadline"):
            if field in changes:
                setattr(task, field, changes[field])
        if reassigned:
            task.assignee = new_assignee

        await self._session.commit()

        if reassigned:
            self._notify_assigned(task)
        return task

    async def change_status(self, task_id: int, actor: User, target: TaskStatus) -> Task:
        task = await self._get_locked(task_id)
        if actor.id not in (task.author_id, task.assignee_id):
            raise PermissionDeniedError(
                "Only the author or the assignee can change the task status",
                code="not_task_participant",
            )

        if not can_transition(task.status, target):
            raise ConflictError(
                f"Transition from '{task.status.value}' to '{target.value}' is not allowed",
                code="invalid_status_transition",
            )

        if target == TaskStatus.DONE:
            if task.assignee_id is None:
                raise ConflictError(
                    "A task without an assignee cannot be marked as done", code="assignee_required"
                )
            if task.deadline < utcnow():
                raise ConflictError(
                    "A task whose deadline has passed cannot be marked as done",
                    code="deadline_passed",
                )

        task.status = target
        await self._session.commit()
        return task

    async def delete(self, task_id: int, actor: User) -> None:
        task = await self._get_locked(task_id)
        self._ensure_author(task, actor)
        if task.status in UNDELETABLE_STATUSES:
            raise ConflictError(
                f"A task in '{task.status.value}' cannot be deleted; cancel or complete it first",
                code="task_not_deletable",
            )
        await self._tasks.delete(task)
        await self._session.commit()

    async def list_tasks(
        self, filters: TaskFilters, sort: list[SortSpec], pagination: Pagination
    ) -> tuple[list[Task], int]:
        return await self._tasks.search(filters, sort, pagination)

    async def list_overdue(self, pagination: Pagination) -> tuple[list[Task], int]:
        return await self._tasks.list_overdue(utcnow(), pagination)

    async def stats(self) -> TaskStats:
        rows = await self._tasks.count_by_status_and_priority(utcnow())

        by_status = dict.fromkeys(TaskStatus, 0)
        by_priority = dict.fromkeys(TaskPriority, 0)
        total = active = overdue = 0
        for status, priority, count, overdue_count in rows:
            by_status[status] += count
            by_priority[priority] += count
            total += count
            overdue += overdue_count
            if status in ACTIVE_STATUSES:
                active += count

        return TaskStats(
            total=total,
            by_status=by_status,
            by_priority=by_priority,
            overdue=overdue,
            active=active,
        )

    async def _get_locked(self, task_id: int) -> Task:
        task = await self._tasks.get(task_id, for_update=True)
        if task is None:
            raise self._not_found(task_id)
        return task

    async def _acquire_assignee(self, user_id: int | None) -> User | None:
        """Lock the assignee row and make sure they can take one more active task.

        Locking serializes concurrent assignments to the same user, so the limit
        cannot be bypassed by parallel requests.
        """
        if user_id is None:
            return None

        assignee = await self._users.get(user_id, for_update=True)
        if assignee is None:
            raise DomainValidationError(
                f"Assignee with id {user_id} does not exist", code="assignee_not_found"
            )

        limit = self._settings.max_active_tasks_per_user
        active = await self._tasks.count_active_for_user(assignee.id)
        if active >= limit:
            raise ConflictError(
                f"User {assignee.id} already has {active} active tasks (limit: {limit})",
                code="active_tasks_limit_exceeded",
            )
        return assignee

    def _notify_assigned(self, task: Task) -> None:
        if task.assignee is not None:
            self._background.add_task(notify_assignee, task.id, task.title, task.assignee.email)

    @staticmethod
    def _ensure_deadline_not_in_past(deadline: datetime) -> None:
        if deadline < utcnow():
            raise DomainValidationError(
                "The deadline cannot be in the past", code="deadline_in_past"
            )

    @staticmethod
    def _ensure_author(task: Task, actor: User) -> None:
        if task.author_id != actor.id:
            raise PermissionDeniedError(
                "Only the task author can edit or delete the task", code="not_task_author"
            )

    @staticmethod
    def _not_found(task_id: int) -> NotFoundError:
        return NotFoundError(f"Task {task_id} not found", code="task_not_found")
