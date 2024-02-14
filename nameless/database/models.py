from datetime import datetime, timedelta

import discord
from sqlalchemy import Column, ForeignKey
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship
from sqlalchemy.sql.sqltypes import *

__all__ = ["DbUser", "DbGuild"]


class PascalCaseDeclarativeMeta(DeclarativeMeta):
    def __init__(cls, name, bases, namespace):
        cls.rename_declared_columns(namespace)
        super().__init__(name, bases, namespace)

    def __setattr__(cls, key, value):
        if isinstance(value, Column):
            cls.undefer_column_name_only(key, value)
        super().__setattr__(key, value)

    def to_camelcase(cls, s):
        return ''.join([w.title() for w in s.split('_')])

    def undefer_column_name_only(cls, key, column):
        if column.name is None:
            column.name = cls.to_camelcase(key)

    def rename_declared_columns(cls, namespace):
        for key, attr in namespace.items():
            if isinstance(attr, Column):
                cls.undefer_column_name_only(key, attr)


Base = declarative_base(metaclass=PascalCaseDeclarativeMeta)


# https://docs.sqlalchemy.org/en/20/orm/inheritance.html#concrete-table-inheritance
class DiscordObject:
    __tablename__ = "Discord"
    __mapper_args__ = {"polymorphic_on": type, "polymorphic_identity": "Discord"}

    discord_id: Mapped[int] = Column(BigInteger, primary_key=True)

    def __init__(self, entry: int | discord.User):
        self.discord_id = entry.id if isinstance(entry, discord.User) else entry


class DbUser(DiscordObject, Base):
    __tablename__ = "Users"
    __mapper_args__ = {
        "polymorphic_identity": "Users",
        "concrete": True,
    }

    warn_count: int = Column(SmallInteger, default=0)
    osu_username: str = Column(Text, default="")
    osu_mode: str = Column(Text, default="")


class DbGuild(DiscordObject, Base):
    __tablename__ = "Guilds"
    __mapper_args__ = {
        "polymorphic_identity": "Guilds",
        "concrete": True,
    }

    is_welcome_enabled: bool = Column(Boolean, default=False)
    is_goodbye_enabled: bool = Column(Boolean, default=False)
    is_bot_greeting_enabled: bool = Column(Boolean, default=True)
    is_dm_preferred: bool = Column(Boolean, default=False)
    is_timeout_preferred: bool = Column(Boolean, default=True)
    welcome_channel_id: int = Column(BigInteger, default=0)
    goodbye_channel_id: int = Column(BigInteger, default=0)
    welcome_message: str = Column(UnicodeText, default="")
    goodbye_message: str = Column(UnicodeText, default="")
    max_warn_count: int = Column(BigInteger, default=3)
    mute_role_id: int = Column(BigInteger, default=0)
    audio_role_id: int = Column(BigInteger, name="AudioRoleId", default=0)
    radio_start_time: datetime = Column(DateTime, default=datetime.min)
    mute_timeout_interval: timedelta = Column(Interval, default=timedelta(days=7))
    voice_room_channel_id: int = Column(BigInteger, default=0)
