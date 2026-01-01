import uuid

from sqlmodel import Field, SQLModel

metadata = SQLModel.metadata


def _gen_id() -> str:
    """Generate UUID for string primary keys."""
    return uuid.uuid4().hex


class BaseModel(SQLModel):
    """Base model with integer ID (for Discord entities)."""

    Id: int = Field(primary_key=True, index=True)


class BaseUUIDModel(BaseModel):
    """Base model with UUID string ID (for internal entities)."""

    UUID: str = Field(default_factory=_gen_id, index=True, unique=True)


__all__ = ["BaseModel", "BaseUUIDModel", "SQLModel", "metadata"]
