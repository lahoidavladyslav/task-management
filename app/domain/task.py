"""Task vocabulary and the business rules that do not depend on the database."""

from enum import StrEnum


class TaskStatus(StrEnum):
    BACKLOG = "backlog"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


PRIORITY_RANK: dict[TaskPriority, int] = {
    TaskPriority.LOW: 1,
    TaskPriority.MEDIUM: 2,
    TaskPriority.HIGH: 3,
}

ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.BACKLOG: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.REVIEW, TaskStatus.CANCELLED}),
    TaskStatus.REVIEW: frozenset({TaskStatus.DONE, TaskStatus.CANCELLED}),
    TaskStatus.DONE: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

ACTIVE_STATUSES = frozenset({TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW})
FINAL_STATUSES = frozenset({TaskStatus.DONE, TaskStatus.CANCELLED})
ASSIGNEE_LOCKED_STATUSES = frozenset({TaskStatus.REVIEW, TaskStatus.DONE})
UNDELETABLE_STATUSES = frozenset({TaskStatus.IN_PROGRESS, TaskStatus.REVIEW})


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]
