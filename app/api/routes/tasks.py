from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.api.deps import CurrentUser, PaginationDep, TaskServiceDep, get_current_user
from app.core.clock import ensure_utc
from app.core.exceptions import DomainValidationError
from app.domain.task import TaskPriority, TaskStatus
from app.models import Task
from app.schemas.common import MAX_ID, Page, build_page
from app.schemas.task import TaskCreate, TaskRead, TaskStats, TaskStatusChange, TaskUpdate
from app.schemas.task_query import DEFAULT_SORT, SortSpec, TaskFilters, parse_sort

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(get_current_user)])

TaskId = Annotated[int, Path(ge=1, le=MAX_ID, description="Task id")]


def get_task_filters(
    search: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=200,
            description="Case-insensitive match in title or description",
        ),
    ] = None,
    status: Annotated[
        list[TaskStatus] | None, Query(description="Repeat the parameter to match several statuses")
    ] = None,
    priority: Annotated[
        list[TaskPriority] | None,
        Query(description="Repeat the parameter to match several priorities"),
    ] = None,
    assignee_id: Annotated[int | None, Query(ge=1, le=MAX_ID)] = None,
    deadline_from: Annotated[datetime | None, Query(description="Deadline >= value")] = None,
    deadline_to: Annotated[datetime | None, Query(description="Deadline <= value")] = None,
) -> TaskFilters:
    deadline_from = ensure_utc(deadline_from) if deadline_from else None
    deadline_to = ensure_utc(deadline_to) if deadline_to else None
    if deadline_from and deadline_to and deadline_from > deadline_to:
        raise DomainValidationError(
            "'deadline_from' must not be later than 'deadline_to'", code="invalid_deadline_range"
        )
    return TaskFilters(
        search=search.strip() if search else None,
        statuses=tuple(status or ()),
        priorities=tuple(priority or ()),
        assignee_id=assignee_id,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
    )


def get_task_sort(
    sort: Annotated[
        str,
        Query(
            description=(
                "Comma-separated sort fields: `created_at`, `deadline`, `priority`. "
                "Prefix a field with `-` for descending order. "
                "Default: highest priority first, then the nearest deadline."
            ),
            examples=["-priority,deadline"],
        ),
    ] = DEFAULT_SORT,
) -> list[SortSpec]:
    return parse_sort(sort)


TaskFiltersDep = Annotated[TaskFilters, Depends(get_task_filters)]
TaskSortDep = Annotated[list[SortSpec], Depends(get_task_sort)]


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate, current_user: CurrentUser, service: TaskServiceDep
) -> Task:
    return await service.create(current_user, payload)


@router.get("", response_model=Page[TaskRead], summary="Search, filter, sort and paginate tasks")
async def list_tasks(
    service: TaskServiceDep,
    pagination: PaginationDep,
    filters: TaskFiltersDep,
    sort: TaskSortDep,
) -> dict[str, Any]:
    tasks, total = await service.list_tasks(filters, sort, pagination)
    return build_page(tasks, total, pagination)


# Static paths must be declared before "/{task_id}".
@router.get(
    "/overdue",
    response_model=Page[TaskRead],
    summary="Tasks past their deadline that are neither done nor cancelled",
)
async def list_overdue_tasks(service: TaskServiceDep, pagination: PaginationDep) -> dict[str, Any]:
    tasks, total = await service.list_overdue(pagination)
    return build_page(tasks, total, pagination)


@router.get("/stats", response_model=TaskStats, summary="Task statistics")
async def task_stats(service: TaskServiceDep) -> TaskStats:
    return await service.stats()


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: TaskId, service: TaskServiceDep) -> Task:
    return await service.get(task_id)


@router.patch("/{task_id}", response_model=TaskRead, summary="Update task fields")
async def update_task(
    task_id: TaskId, payload: TaskUpdate, current_user: CurrentUser, service: TaskServiceDep
) -> Task:
    return await service.update(task_id, current_user, payload)


@router.patch("/{task_id}/status", response_model=TaskRead, summary="Change task status")
async def change_task_status(
    task_id: TaskId,
    payload: TaskStatusChange,
    current_user: CurrentUser,
    service: TaskServiceDep,
) -> Task:
    return await service.change_status(task_id, current_user, payload.status)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: TaskId, current_user: CurrentUser, service: TaskServiceDep
) -> Response:
    await service.delete(task_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
