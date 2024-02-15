from datetime import datetime, timedelta

import discord
from sqlalchemy import Column, ForeignKey
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.orm import Mapped, declarative_base, relationship, mapped_column
from sqlalchemy.sql.sqltypes import *

__all__ = ["Base", "DiscordObject", "DbUser", "DbGuild", "CrosschatAssociation", "CrosschatChannel"]


class PascalCaseDeclarativeMeta(DeclarativeMeta):
    def __init__(cls, name, bases, namespace):
        cls.rename_declared_columns(namespace)
        super().__init__(name, bases, namespace)

    def __setattr__(cls, key, value):
        if isinstance(value, Column):
            cls.undefer_column_name_only(key, value)
        super().__setattr__(key, value)

    def to_camelcase(cls, s):
        return "".join([w.title() for w in s.split("_")])

    def undefer_column_name_only(cls, key, column):
        if column.name is None:
            column.name = cls.to_camelcase(key)

    def rename_declared_columns(cls, namespace):
        for key, attr in namespace.items():
            if isinstance(attr, Column):
                cls.undefer_column_name_only(key, attr)


Base = declarative_base(metaclass=PascalCaseDeclarativeMeta)


class DiscordObject(Base):
    __abstract__ = True

    discord_id: Mapped[int] = Column(BigInteger, primary_key=True)

    def __init__(self, entry: int | discord.User):
        self.discord_id = entry.id if isinstance(entry, discord.User) else entry


class DbUser(DiscordObject):
    __tablename__ = "Users"

    warn_count: int = Column(SmallInteger, default=0)
    osu_username: str = Column(Text, default="")
    osu_mode: str = Column(Text, default="")


class DbGuild(DiscordObject):
    __tablename__ = "Guilds"

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
    audio_role_id: int = Column(BigInteger, default=0)
    radio_start_time: datetime = Column(DateTime, default=datetime.min)
    mute_timeout_interval: timedelta = Column(Interval, default=timedelta(days=7))
    voice_room_channel_id: int = Column(BigInteger, default=0)

    crosschat_channels: Mapped[List["CrosschatChannel"]] = relationship(
        secondary="CrosschatAssociations",
        back_populates="guilds"
    )

    crosschat_channels_associations: Mapped[List["CrosschatAssociation"]] = relationship(
        back_populates="guild"
    )


class CrosschatChannel(DiscordObject):
    __tablename__ = "CrosschatChannels"

    target_channel_id: Mapped[int] = Column(BigInteger, default=0)
    target_guild_id: Mapped[int] = Column(BigInteger, default=0)

    # many-to-many relationship to Parent, bypassing the `Association` class
    guilds: Mapped[List["DbGuild"]] = relationship(
        secondary="CrosschatAssociations",
        back_populates="crosschat_channels"
    )

    # association between Child -> Association -> Parent
    guilds_associations: Mapped[List["CrosschatAssociation"]] = relationship(
        back_populates="channel"
    )


class CrosschatAssociation(Base):
    __tablename__ = "CrosschatAssociations"

    guild_id: Mapped[int] = mapped_column(ForeignKey(DbGuild.discord_id), primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey(CrosschatChannel.discord_id), primary_key=True)

    channel: Mapped["CrosschatChannel"] = relationship(back_populates="guilds_associations")
    guild: Mapped["DbGuild"] = relationship(back_populates="crosschat_channels_associations")

