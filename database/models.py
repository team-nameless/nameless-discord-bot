from sqlalchemy.orm import declarative_base
from sqlalchemy import *

Base = declarative_base()


class DbUser(Base):
    __tablename__ = "Users"
    id: int = Column(BigInteger, name="Id", primary_key=True)
    warn_count: int = Column(SmallInteger, name="WarnCount")
    osu_username: str = Column(Text, name="OsuUsername")
    osu_mode: str = Column(Text, name="OsuMode")


class DbGuild(Base):
    __tablename__ = "Guilds"
    id: int = Column(BigInteger, name="Id", primary_key=True)
    is_welcome_enabled: bool = Column(Boolean, name="IsWelcomeEnabled")
    is_goodbye_enabled: bool = Column(Boolean, name="IsGoodbyeEnabled")
    welcome_channel_id: int = Column(BigInteger, name="WelcomeChannelId")
    goodbye_channel_id: int = Column(BigInteger, name="GoodbyeChannelId")
    welcome_message: str = Column(UnicodeText, name="WelcomeMessage")
    goodbye_message: str = Column(UnicodeText, name="GoodbyeMessage")
