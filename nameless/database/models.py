# pyright: reportGeneralTypeIssues=false, reportWildcardImportFromLibrary=false
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
    discord_id: int = Column(BigInteger, name="Id", primary_key=True)
    warn_count: int = Column(SmallInteger, name="WarnCount", default=0)
    osu_username: str = Column(Text, name="OsuUsername", default="")
    osu_mode: str = Column(Text, name="OsuMode", default="")


class DbGuild(Base):
    def __init__(self, _id: discord.Guild | int):
        super().__init__()
        self.discord_id = _id.id if isinstance(_id, discord.Guild) else _id

    __tablename__ = "Guilds"
    discord_id: int = Column(BigInteger, name="Id", primary_key=True)
    is_welcome_enabled: bool = Column(Boolean, name="IsWelcomeEnabled", default=False)
    is_goodbye_enabled: bool = Column(Boolean, name="IsGoodbyeEnabled", default=False)
    is_bot_greeting_enabled: bool = Column(Boolean, name="IsBotGreetingEnabled", default=True)
    is_dm_preferred: bool = Column(Boolean, name="IsDmPreferred", default=False)
    is_timeout_preferred: bool = Column(Boolean, name="IsTimeoutPreferred", default=True)
    welcome_channel_id: int = Column(BigInteger, name="WelcomeChannelId", default=0)
    goodbye_channel_id: int = Column(BigInteger, name="GoodbyeChannelId", default=0)
    welcome_message: str = Column(UnicodeText, name="WelcomeMessage", default="")
    goodbye_message: str = Column(UnicodeText, name="GoodbyeMessage", default="")
    max_warn_count: int = Column(BigInteger, name="MaxWarnCount", default=3)
    mute_role_id: int = Column(BigInteger, name="MuteRoleId", default=0)
    audio_role_id: int = Column(BigInteger, name="AudioRoleId", default=0)
    radio_start_time: datetime = Column(DateTime, name="RadioStartTime", default=datetime.min)
    mute_timeout_interval: timedelta = Column(Interval, name="MuteTimeoutInterval", default=timedelta(days=7))
