from datetime import datetime

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

    osu_username: Mapped[str] = mapped_column("OsuUsername")
    osu_mode: Mapped[str] = mapped_column("OsuMode")


class DbGuild(DiscordObject):
    __tablename__ = "Guilds"

    is_welcome_enabled: Mapped[bool] = mapped_column("IsWelcomeEnabled")
    is_goodbye_enabled: Mapped[bool] = mapped_column("IsGoodbyeEnabled")
    is_bot_greeting_enabled: Mapped[bool] = mapped_column("IsBotGreetingEnabled", default=True)
    is_dm_preferred: Mapped[bool] = mapped_column("IsDmPreferred")
    welcome_channel_id: Mapped[int] = mapped_column("WelcomeChannelId", BigInteger)
    goodbye_channel_id: Mapped[int] = mapped_column("GoodbyeChannelId", BigInteger)
    welcome_message: Mapped[str] = mapped_column("WelcomeMessage", UnicodeText)
    goodbye_message: Mapped[str] = mapped_column("GoodbyeMessage", UnicodeText)
    audio_role_id: Mapped[int] = mapped_column("AudioRoleId", BigInteger)
    radio_start_time: Mapped[datetime] = mapped_column("RadioStartTime")
    voice_room_channel_id: Mapped[int] = mapped_column("VoiceRoomChannelId", BigInteger)
