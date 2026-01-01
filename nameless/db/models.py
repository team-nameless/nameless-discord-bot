from typing import Optional

from sqlmodel import Field, Relationship

from .base import BaseModel, BaseUUIDModel


class Guild(BaseModel, table=True):
    HoneypotChannelId: int = Field(default=0, nullable=False)

    HostedChats: list["CrossChatRoom"] = Relationship(back_populates="Guild")
    ConnectedChats: list["CrossChatConnection"] = Relationship(back_populates="Guild")
    PlayerSettings: Optional["PlayerSettings"] = Relationship(
        back_populates="Guild", sa_relationship_kwargs={"uselist": False}
    )


class User(BaseModel, table=True):
    MaimaiFriendCode: int = Field(default=0, nullable=False)


class CrossChatRoom(BaseUUIDModel, table=True):
    GuildId: int = Field(foreign_key="guild.Id")
    ChannelId: int
    IsPublic: bool = Field(default=True, nullable=False)

    Guild: Optional["Guild"] = Relationship(back_populates="HostedChats")
    CrossChatConnection: list["CrossChatConnection"] = Relationship(back_populates="Room")


class CrossChatConnection(BaseUUIDModel, table=True):
    SourceGuildId: int | None = Field(default=None, foreign_key="guild.Id")
    SourceChannelId: int
    TargetGuildId: int
    TargetChannelId: int
    RoomId: str = Field(foreign_key="crosschatroom.UUID")

    Guild: Optional["Guild"] = Relationship(back_populates="ConnectedChats")
    Room: CrossChatRoom = Relationship(back_populates="CrossChatConnection")
    Messages: list["CrossChatMessage"] = Relationship(back_populates="Connection")


class CrossChatMessage(BaseUUIDModel, table=True):
    ConnectionId: str | None = Field(default=None, foreign_key="crosschatconnection.UUID")
    OriginMessageId: int
    ClonedMessageId: int

    Connection: CrossChatConnection | None = Relationship(back_populates="Messages")


class PlayerSettings(BaseUUIDModel, table=True):
    GuildId: int = Field(foreign_key="guild.Id", unique=True)

    Guild: Optional["Guild"] = Relationship(back_populates="PlayerSettings")
