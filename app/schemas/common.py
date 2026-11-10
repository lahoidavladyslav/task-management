import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")

# Upper bound of a 32-bit SERIAL column; larger ids can never exist and
# would make the database driver raise instead of returning a clean 404.
MAX_ID = 2**31 - 1

# Keeps OFFSET far below the bigint range; deeper pages are never useful in practice.
MAX_PAGE = 1_000_000


@dataclass(frozen=True, slots=True)
class Pagination:
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


def build_page(items: Sequence[Any], total: int, pagination: Pagination) -> dict[str, Any]:
    """Raw payload for `Page[...]`; FastAPI validates ORM objects against the response model."""
    return {
        "items": items,
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "pages": math.ceil(total / pagination.page_size),
    }
