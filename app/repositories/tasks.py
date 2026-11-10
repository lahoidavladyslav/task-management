from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.task import (
    ACTIVE_STATUSES,
    PRIORITY_RANK,
    TaskPriority,
    TaskStatus,
)
from app.models import Task
from app.schemas.common import Pagination
from app.schemas.task_query import SortField, SortSpec, TaskFilters

_ACTIVE = tuple(ACTIVE_STATUSES)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _priority_rank() -> ColumnElement[int]:
    return case(*[(Task.priority == p, rank) for p, rank in PRIORITY_RANK.items()], else_=0)


def _sort_expression(spec: SortSpec) -> ColumnElement:
    column = {
        SortField.CREATED_AT: Task.created_at,
        SortField.DEADLINE: Task.deadline,
        SortField.PRIORITY: _priority_rank(),
    }[spec.field]
    return column.desc() if spec.descending else column.asc()


def _filter_conditions(filters: TaskFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.search:
        pattern = f"%{_escape_like(filters.search)}%"
        conditions.append(
            or_(
                Task.title.ilike(pattern, escape="\\"),
                Task.description.ilike(pattern, escape="\\"),
            )
        )
    if filters.statuses:
        conditions.append(Task.status.in_(filters.statuses))
    if filters.priorities:
        conditions.append(Task.priority.in_(filters.priorities))
    if filters.assignee_id is not None:
        conditions.append(Task.assignee_id == filters.assignee_id)
    if filters.deadline_from is not None:
        conditions.append(Task.deadline >= filters.deadline_from)
    if filters.deadline_to is not None:
        conditions.append(Task.deadline <= filters.deadline_to)
    return conditions


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, task_id: int, *, for_update: bool = False) -> Task | None:
        stmt = select(Task).where(Task.id == task_id)
        if for_update:
            stmt = stmt.with_for_update(key_share=True)
        return await self._session.scalar(stmt)

    async def exists(self, task_id: int) -> bool:
        return await self._session.scalar(select(Task.id).where(Task.id == task_id)) is not None

    async def add(self, task: Task) -> None:
        self._session.add(task)
        await self._session.flush()

    async def delete(self, task: Task) -> None:
        await self._session.delete(task)
        await self._session.flush()

    async def count_active_for_user(self, user_id: int) -> int:
        stmt = select(func.count(Task.id)).where(
            Task.assignee_id == user_id, Task.status.in_(_ACTIVE)
        )
        return await self._session.scalar(stmt) or 0

    async def search(
        self, filters: TaskFilters, sort: Sequence[SortSpec], pagination: Pagination
    ) -> tuple[list[Task], int]:
        conditions = _filter_conditions(filters)
        total = await self._session.scalar(select(func.count(Task.id)).where(*conditions)) or 0
        stmt = (
            select(Task)
            .where(*conditions)
            .order_by(*(_sort_expression(spec) for spec in sort), Task.id.asc())
            .limit(pagination.page_size)
            .offset(pagination.offset)
        )
        items = list((await self._session.scalars(stmt)).all())
        return items, total

    async def list_overdue(self, now: datetime, pagination: Pagination) -> tuple[list[Task], int]:
        conditions = [Task.deadline < now, Task.status.in_(_ACTIVE)]
        total = await self._session.scalar(select(func.count(Task.id)).where(*conditions)) or 0
        stmt = (
            select(Task)
            .where(*conditions)
            .order_by(Task.deadline.asc(), Task.id.asc())
            .limit(pagination.page_size)
            .offset(pagination.offset)
        )
        items = list((await self._session.scalars(stmt)).all())
        return items, total

    async def count_by_status_and_priority(
        self, now: datetime
    ) -> list[tuple[TaskStatus, TaskPriority, int, int]]:
        """Rows of (status, priority, tasks, overdue tasks)."""
        overdue = and_(Task.deadline < now, Task.status.in_(_ACTIVE))
        stmt = select(
            Task.status,
            Task.priority,
            func.count(Task.id),
            func.count(Task.id).filter(overdue),
        ).group_by(Task.status, Task.priority)
        result = await self._session.execute(stmt)
        return [(row[0], row[1], row[2], row[3]) for row in result.all()]

    async def cancel_overdue(self, now: datetime) -> list[int]:
        """Cancel every active task past its deadline in a single statement."""
        stmt = (
            update(Task)
            .where(Task.deadline < now, Task.status.in_(_ACTIVE))
            .values(status=TaskStatus.CANCELLED, updated_at=now)
            .returning(Task.id)
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
