from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, status

from app.api.deps import CommentServiceDep, CurrentUser, PaginationDep, get_current_user
from app.models import Comment
from app.schemas.comment import CommentCreate, CommentRead
from app.schemas.common import MAX_ID, Page, build_page

router = APIRouter(
    prefix="/tasks/{task_id}/comments", tags=["comments"], dependencies=[Depends(get_current_user)]
)

TaskId = Annotated[int, Path(ge=1, le=MAX_ID, description="Task id")]


@router.post("", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
async def add_comment(
    task_id: TaskId,
    payload: CommentCreate,
    current_user: CurrentUser,
    service: CommentServiceDep,
) -> Comment:
    return await service.add(task_id, current_user, payload)


@router.get("", response_model=Page[CommentRead], summary="List comments, oldest first")
async def list_comments(
    task_id: TaskId, pagination: PaginationDep, service: CommentServiceDep
) -> dict[str, Any]:
    comments, total = await service.list(task_id, pagination)
    return build_page(comments, total, pagination)
