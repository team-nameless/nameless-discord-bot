import datetime

from sqlalchemy import *
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# Migration cheat code:
# alembic revision --autogenerate -m "Message here"
# alembic upgrade head
# In case of fire: https://www.learndatasci.com/tutorials/using-databases-python-postgres-sqlalchemy-and-alembic/


class DbUser(Base):
    __tablename__ = "Users"
    id: int = Column(BigInteger, name="Id", primary_key=True)
    warn_count: int = Column(SmallInteger, name="WarnCount", default=0)
    osu_username: str = Column(Text, name="OsuUsername", default="")
    osu_mode: str = Column(Text, name="OsuMode", default="")


class DbGuild(Base):
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
