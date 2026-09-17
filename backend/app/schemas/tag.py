import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# Matches the frontend's zod rule in features/tags/schemas/tag.ts.
HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

NAME_FIELD = Field(..., min_length=1, max_length=50)
OPTIONAL_NAME_FIELD = Field(None, min_length=1, max_length=50)
COLOR_FIELD = Field(None, max_length=20)


def _clean_name(value: str) -> str:
    """Trim, and reject a name that is only whitespace.

    Without this " work " and "work" are two different tags that the
    case-insensitive unique index would happily allow side by side.
    """
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Tag name cannot be blank")
    return cleaned


def _clean_color(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not HEX_COLOR.match(cleaned):
        raise ValueError("Color must be a hex value such as #4f46e5")
    return cleaned.lower()


class TagCreate(BaseModel):
    name: str = NAME_FIELD
    color: str | None = COLOR_FIELD

    _validate_name = field_validator("name")(_clean_name)
    _validate_color = field_validator("color")(_clean_color)


class TagUpdate(BaseModel):
    name: str | None = OPTIONAL_NAME_FIELD
    color: str | None = COLOR_FIELD

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)

    _validate_color = field_validator("color")(_clean_color)


class TagResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    color: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TagListResponse(BaseModel):
    items: list[TagResponse]
    total: int


class TodoTagAttach(BaseModel):
    tag_id: uuid.UUID
