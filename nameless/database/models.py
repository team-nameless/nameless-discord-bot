from datetime import datetime, timedelta

import discord
from sqlalchemy import Column
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql.sqltypes import *

__all__ = ["Base", "DbUser", "DbGuild"]

Base = declarative_base()


class DbUser(Base):
    def __init__(self, _id: discord.User | int):
        super().__init__()
        self.discord_id = _id.id if isinstance(_id, discord.User) else _id

    __tablename__ = "Users"
    discord_id: int = Column(BigInteger, name="Id", primary_key=True)  # type: ignore
    warn_count: int = Column(SmallInteger, name="WarnCount", default=0)  # type: ignore
    osu_username: str = Column(Text, name="OsuUsername", default="")  # type: ignore
    osu_mode: str = Column(Text, name="OsuMode", default="")  # type: ignore


class DbGuild(Base):
    def __init__(self, _id: discord.Guild | int):
        super().__init__()
        self.discord_id = _id.id if isinstance(_id, discord.Guild) else _id

    __tablename__ = "Guilds"
    discord_id: int = Column(BigInteger, name="Id", primary_key=True)  # type: ignore
    is_welcome_enabled: bool = Column(Boolean, name="IsWelcomeEnabled", default=False)  # type: ignore
    is_goodbye_enabled: bool = Column(Boolean, name="IsGoodbyeEnabled", default=False)  # type: ignore
    is_bot_greeting_enabled: bool = Column(Boolean, name="IsBotGreetingEnabled", default=True)  # type: ignore
    is_dm_preferred: bool = Column(Boolean, name="IsDmPreferred", default=False)  # type: ignore
    is_timeout_preferred: bool = Column(Boolean, name="IsTimeoutPreferred", default=True)  # type: ignore
    welcome_channel_id: int = Column(BigInteger, name="WelcomeChannelId", default=0)  # type: ignore
    goodbye_channel_id: int = Column(BigInteger, name="GoodbyeChannelId", default=0)  # type: ignore
    welcome_message: str = Column(UnicodeText, name="WelcomeMessage", default="")  # type: ignore
    goodbye_message: str = Column(UnicodeText, name="GoodbyeMessage", default="")  # type: ignore
    max_warn_count: int = Column(BigInteger, name="MaxWarnCount", default=3)  # type: ignore
    mute_role_id: int = Column(BigInteger, name="MuteRoleId", default=0)  # type: ignore
    radio_start_time: datetime = Column(DateTime, name="RadioStartTime", default=datetime.min)  # type: ignore
    mute_timeout_interval: timedelta = Column(Interval, name="MuteTimeoutInterval", default=timedelta(days=7))  # type: ignore
