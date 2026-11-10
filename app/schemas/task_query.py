from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.core.exceptions import DomainValidationError
from app.domain.task import TaskPriority, TaskStatus


class SortField(StrEnum):
    CREATED_AT = "created_at"
    DEADLINE = "deadline"
    PRIORITY = "priority"


@dataclass(frozen=True, slots=True)
class SortSpec:
    field: SortField
    descending: bool = False


@dataclass(frozen=True, slots=True)
class TaskFilters:
    search: str | None = None
    statuses: tuple[TaskStatus, ...] = ()
    priorities: tuple[TaskPriority, ...] = ()
    assignee_id: int | None = None
    deadline_from: datetime | None = None
    deadline_to: datetime | None = None


DEFAULT_SORT = "-priority,deadline"


def parse_sort(raw: str) -> list[SortSpec]:
    """Parse `-priority,deadline` style expressions; a leading `-` means descending."""
    allowed = ", ".join(field.value for field in SortField)
    specs: list[SortSpec] = []
    seen: set[SortField] = set()

    for token in (part.strip() for part in raw.split(",")):
        if not token:
            continue
        descending = token.startswith("-")
        name = token.removeprefix("-")
        try:
            field = SortField(name)
        except ValueError:
            raise DomainValidationError(
                f"Unsupported sort field '{name}'. Allowed fields: {allowed}", code="invalid_sort"
            ) from None
        if field in seen:
            raise DomainValidationError(
                f"Sort field '{name}' is specified more than once", code="invalid_sort"
            )
        seen.add(field)
        specs.append(SortSpec(field, descending))

    if not specs:
        raise DomainValidationError("Sort expression is empty", code="invalid_sort")
    return specs
