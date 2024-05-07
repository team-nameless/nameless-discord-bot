import discord
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.sqltypes import *

__all__ = ["Base", "DiscordObject", "DbUser", "DbGuild"]


class Base(DeclarativeBase):
    ...


class DiscordObject(Base):
    __abstract__ = True

    discord_id: Mapped[int] = mapped_column("DiscordId", BigInteger, primary_key=True)

    def __init__(self, entry: int | discord.User):
        self.discord_id = entry.id if isinstance(entry, discord.User) else entry


class DbUser(DiscordObject):
    __tablename__ = "Users"

    osu_username: Mapped[str] = mapped_column("OsuUsername", UnicodeText, default="")
    osu_mode: Mapped[str] = mapped_column("OsuMode", default="")


class DbGuild(DiscordObject):
    __tablename__ = "Guilds"

    is_welcome_enabled: Mapped[bool] = mapped_column("IsWelcomeEnabled", default=True)
    is_goodbye_enabled: Mapped[bool] = mapped_column("IsGoodbyeEnabled", default=True)
    is_bot_greeting_enabled: Mapped[bool] = mapped_column("IsBotGreetingEnabled", default=True)
    is_dm_preferred: Mapped[bool] = mapped_column("IsDmPreferred", default=False)
    welcome_channel_id: Mapped[int] = mapped_column("WelcomeChannelId", BigInteger, default=0)
    goodbye_channel_id: Mapped[int] = mapped_column("GoodbyeChannelId", BigInteger, default=0)
    welcome_message: Mapped[str] = mapped_column("WelcomeMessage", UnicodeText, default="")
    goodbye_message: Mapped[str] = mapped_column("GoodbyeMessage", UnicodeText, default="")
    audio_role_id: Mapped[int] = mapped_column("AudioRoleId", BigInteger, default=0)
    voice_room_channel_id: Mapped[int] = mapped_column("VoiceRoomChannelId", BigInteger, default=0)
