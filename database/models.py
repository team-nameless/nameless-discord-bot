import datetime

from sqlalchemy import *
from sqlalchemy.orm import declarative_base

__all__ = ["Base", "DbUser", "DbGuild"]

Base = declarative_base()


class Mongo:
    @staticmethod
    def from_dict(d: dict):
        pass

    def to_dict(self) -> dict:
        pass


class DbUser(Base, Mongo):
    @staticmethod
    def from_dict(d: dict):
        return DbUser(d["id"], d["warn_count"], d["osu_mode"], d["osu_username"])

    def __init__(
        self, _id: int, warn_count: int = 0, osu_mode: str = "", osu_username: str = ""
    ):
        super().__init__()
        self.id: int = _id
        self.warn_count: int = warn_count
        self.osu_mode: str = osu_mode
        self.osu_username: str = osu_username

    def to_dict(self):
        return {
            "id": self.id,
            "warn_count": self.warn_count,
            "osu_username": self.osu_username,
            "osu_mode": self.osu_mode,
        }

    __tablename__ = "Users"
    id: int = Column(BigInteger, name="Id", primary_key=True)
    warn_count: int = Column(SmallInteger, name="WarnCount", default=0)
    osu_username: str = Column(Text, name="OsuUsername", default="")
    osu_mode: str = Column(Text, name="OsuMode", default="")


class DbGuild(Base, Mongo):
    def __init__(
        self,
        _id: int,
        is_welcome_enabled: bool = False,
        is_goodbye_enabled: bool = False,
        welcome_channel_id: int = 0,
        goodbye_channel_id: int = 0,
        welcome_message: str = "",
        goodbye_message: str = "",
        radio_start_time: datetime.datetime = datetime.datetime.min,
    ):
        super().__init__()
        self.id: int = _id
        self.is_welcome_enabled: bool = is_welcome_enabled
        self.is_goodbye_enabled: bool = is_goodbye_enabled
        self.welcome_channel_id: int = welcome_channel_id
        self.goodbye_channel_id: int = goodbye_channel_id
        self.welcome_message: str = welcome_message
        self.goodbye_message: str = goodbye_message
        self.radio_start_time: datetime.datetime = radio_start_time

    @staticmethod
    def from_dict(d: dict):
        return DbGuild(
            d["id"],
            d["is_welcome_enabled"],
            d["is_goodbye_enabled"],
            d["welcome_channel_id"],
            d["goodbye_channel_id"],
            d["welcome_message"],
            d["welcome_message"],
            d["radio_start_time"],
        )

    def to_dict(self):
        return {
            "id": self.id,
            "is_welcome_enabled": self.is_welcome_enabled,
            "is_goodbye_enabled": self.is_goodbye_enabled,
            "welcome_channel_id": self.welcome_channel_id,
            "goodbye_channel_id": self.goodbye_channel_id,
            "welcome_message": self.welcome_message,
            "goodbye_message": self.goodbye_message,
            "radio_start_time": self.radio_start_time,
        }

    __tablename__ = "Guilds"
    id: int = Column(BigInteger, name="Id", primary_key=True)
    is_welcome_enabled: bool = Column(Boolean, name="IsWelcomeEnabled", default=False)
    is_goodbye_enabled: bool = Column(Boolean, name="IsGoodbyeEnabled", default=False)
    welcome_channel_id: int = Column(BigInteger, name="WelcomeChannelId", default=0)
    goodbye_channel_id: int = Column(BigInteger, name="GoodbyeChannelId", default=0)
    welcome_message: str = Column(UnicodeText, name="WelcomeMessage", default="")
    goodbye_message: str = Column(UnicodeText, name="GoodbyeMessage", default="")
    radio_start_time: datetime.datetime = Column(
        DateTime, name="RadioStartTime", default=datetime.datetime.min
    )
