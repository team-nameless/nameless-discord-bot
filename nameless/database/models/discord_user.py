from sqlalchemy import UnicodeText
from sqlalchemy.orm import Mapped, mapped_column

from nameless.database.models.discord_snowflake import DiscordObject

__all__ = ["DbUser"]


class DbUser(DiscordObject):
    __tablename__ = "Users"

    osu_username: Mapped[str] = mapped_column("OsuUsername", UnicodeText, default="")
    osu_mode: Mapped[str] = mapped_column("OsuMode", default="")
