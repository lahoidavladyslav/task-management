from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.base import Base
from app.domain.task import TaskPriority, TaskStatus
from app.models.user import User


def _enum_values(enum_cls: type[PyEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_assignee_id_status", "assignee_id", "status"),
        Index("ix_tasks_status_deadline", "status", "deadline"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="task_status",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=_enum_values,
        ),
        default=TaskStatus.BACKLOG,
        server_default=TaskStatus.BACKLOG.value,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(
            TaskPriority,
            name="task_priority",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=_enum_values,
        ),
        default=TaskPriority.MEDIUM,
        server_default=TaskPriority.MEDIUM.value,
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now()
    )

    author: Mapped[User] = relationship(foreign_keys=[author_id], lazy="selectin")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id], lazy="selectin")
