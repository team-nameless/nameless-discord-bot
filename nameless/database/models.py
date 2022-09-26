import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, SmallInteger, Text, UnicodeText
from sqlalchemy.orm import declarative_base


__all__ = ["Base", "DbUser", "DbGuild"]

Base = declarative_base()


class DbUser(Base):
    def __init__(
        self,
        _id: int,
        _warn_count: int = 0,
        _osu_username: str = "",
        _osu_mode: str = "",
    ):
        super().__init__()
        self.discord_id = _id
        self.warn_count = _warn_count
        self.osu_username = _osu_username
        self.osu_mode = _osu_mode

    __tablename__ = "Users"
    discord_id: int = Column(BigInteger, name="Id", primary_key=True)  # type: ignore
    warn_count: int = Column(SmallInteger, name="WarnCount", default=0)  # type: ignore
    osu_username: str = Column(Text, name="OsuUsername", default="")  # type: ignore
    osu_mode: str = Column(Text, name="OsuMode", default="")  # type: ignore


class DbGuild(Base):
    def __init__(
        self,
        _id: int,
        _is_welcome_enabled: bool = False,
        _is_goodbye_enabled: bool = False,
        _welcome_channel_id: int = 0,
        _goodbye_channel_id: int = 0,
        _welcome_message: str = "",
        _goodbye_message: str = "",
        _radio_start_time: datetime.datetime = datetime.datetime.min,
    ):
        super().__init__()
        self.discord_id = _id
        self.is_welcome_enabled = _is_welcome_enabled
        self.is_goodbye_enabled = _is_goodbye_enabled
        self.welcome_channel_id = _welcome_channel_id
        self.goodbye_channel_id = _goodbye_channel_id
        self.welcome_message = _welcome_message
        self.goodbye_message = _goodbye_message
        self.radio_start_time = _radio_start_time

    __tablename__ = "Guilds"
    discord_id: int = Column(BigInteger, name="Id", primary_key=True)  # pyright: ignore
    is_welcome_enabled: bool = Column(Boolean, name="IsWelcomeEnabled", default=False)  # pyright: ignore
    is_goodbye_enabled: bool = Column(Boolean, name="IsGoodbyeEnabled", default=False)  # pyright: ignore
    welcome_channel_id: int = Column(BigInteger, name="WelcomeChannelId", default=0)  # pyright: ignore
    goodbye_channel_id: int = Column(BigInteger, name="GoodbyeChannelId", default=0)  # pyright: ignore
    welcome_message: str = Column(UnicodeText, name="WelcomeMessage", default="")  # pyright: ignore
    goodbye_message: str = Column(UnicodeText, name="GoodbyeMessage", default="")  # pyright: ignore
    radio_start_time: datetime.datetime = Column(
        DateTime,
        name="RadioStartTime",
        default=datetime.datetime.min,
    )  # pyright: ignore
