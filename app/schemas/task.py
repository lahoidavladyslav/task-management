from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    field_validator,
    model_validator,
)

from app.core.clock import ensure_utc, utcnow
from app.domain.task import ACTIVE_STATUSES, TaskPriority, TaskStatus
from app.schemas.common import MAX_ID
from app.schemas.user import UserShort

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10_000)]
AssigneeId = Annotated[int, Field(ge=1, le=MAX_ID)]


class TaskCreate(BaseModel):
    title: Title
    description: Description | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: AssigneeId | None = None
    deadline: datetime

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "title": "Prepare release notes",
                    "description": "Collect merged pull requests and group them by component.",
                    "priority": "high",
                    "assignee_id": 2,
                    "deadline": "2030-01-15T18:00:00Z",
                }
            ]
        }
    )

    @field_validator("deadline")
    @classmethod
    def _normalize_deadline(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class TaskUpdate(BaseModel):
    """Partial update: only the fields present in the payload are changed."""

    title: Title | None = None
    description: Description | None = None
    priority: TaskPriority | None = None
    assignee_id: AssigneeId | None = None
    deadline: datetime | None = None

    @field_validator("deadline")
    @classmethod
    def _normalize_deadline(cls, value: datetime | None) -> datetime | None:
        return None if value is None else ensure_utc(value)

    @model_validator(mode="after")
    def _required_fields_cannot_be_null(self) -> "TaskUpdate":
        for name in ("title", "priority", "deadline"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"'{name}' cannot be null")
        return self


class TaskStatusChange(BaseModel):
    status: TaskStatus


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    author_id: int
    assignee_id: int | None
    author: UserShort
    assignee: UserShort | None
    deadline: datetime
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def is_overdue(self) -> bool:
        return self.status in ACTIVE_STATUSES and self.deadline < utcnow()


class TaskStats(BaseModel):
    total: int
    by_status: dict[TaskStatus, int]
    by_priority: dict[TaskPriority, int]
    overdue: int
    active: int
