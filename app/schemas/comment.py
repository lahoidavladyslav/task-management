from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.schemas.user import UserShort

CommentBody = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]


class CommentCreate(BaseModel):
    body: CommentBody


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    body: str
    author: UserShort
    created_at: datetime
