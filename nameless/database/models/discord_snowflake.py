import discord
from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from nameless.database.models.base import Base

__all__ = ["DiscordObject"]


class DiscordObject(Base):
    """
    Represents anything using Discord ID (known as Snowflake).
    Everything related to a Discord entity MUST inherit from this class.
    """
    __abstract__ = True

    discord_id: Mapped[int] = mapped_column("DiscordId", BigInteger, primary_key=True)

    def __init__(self, entry: int | discord.User):
        self.discord_id = entry.id if isinstance(entry, discord.User) else entry
