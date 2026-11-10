import pytest

from app.core.exceptions import DomainValidationError
from app.domain.task import (
    ACTIVE_STATUSES,
    FINAL_STATUSES,
    TaskStatus,
    can_transition,
)
from app.schemas.task_query import SortField, parse_sort

S = TaskStatus


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.BACKLOG, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.REVIEW),
        (S.REVIEW, S.DONE),
        (S.BACKLOG, S.CANCELLED),
        (S.IN_PROGRESS, S.CANCELLED),
        (S.REVIEW, S.CANCELLED),
    ],
)
def test_allowed_transitions(current: TaskStatus, target: TaskStatus) -> None:
    assert can_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.BACKLOG, S.REVIEW),
        (S.BACKLOG, S.DONE),
        (S.BACKLOG, S.BACKLOG),
        (S.IN_PROGRESS, S.BACKLOG),
        (S.IN_PROGRESS, S.DONE),
        (S.REVIEW, S.IN_PROGRESS),
        (S.REVIEW, S.BACKLOG),
    ],
)
def test_forbidden_transitions(current: TaskStatus, target: TaskStatus) -> None:
    assert not can_transition(current, target)


@pytest.mark.parametrize("final", sorted(FINAL_STATUSES))
def test_final_statuses_are_terminal(final: TaskStatus) -> None:
    assert not any(can_transition(final, target) for target in TaskStatus)


def test_every_status_is_either_active_or_final() -> None:
    assert ACTIVE_STATUSES | FINAL_STATUSES == set(TaskStatus)
    assert not ACTIVE_STATUSES & FINAL_STATUSES


def test_parse_sort_handles_direction_and_order() -> None:
    specs = parse_sort("-priority, deadline")
    assert [(s.field, s.descending) for s in specs] == [
        (SortField.PRIORITY, True),
        (SortField.DEADLINE, False),
    ]


@pytest.mark.parametrize("raw", ["title", "priority,-priority", " , "])
def test_parse_sort_rejects_invalid_expressions(raw: str) -> None:
    with pytest.raises(DomainValidationError):
        parse_sort(raw)
