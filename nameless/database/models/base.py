from sqlalchemy.orm import DeclarativeBase

__all__ = ["Base"]


class Base(DeclarativeBase):
    """
    One declarative base to rule them all.
    All future database models **MUST** inherit from this class.
    """
    ...
