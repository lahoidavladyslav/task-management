from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

MAX_PASSWORD_LENGTH = 128
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=MAX_PASSWORD_LENGTH)
    full_name: FullName

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "olena.kovalenko@example.com",
                    "password": "Str0ngPassw0rd!",
                    "full_name": "Olena Kovalenko",
                }
            ]
        }
    )


class UserShort(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str


class UserRead(UserShort):
    email: str
    created_at: datetime
