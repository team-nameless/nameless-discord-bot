from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import nextcord
from typing import Optional

from sqlalchemy.util import IdentitySet
from sqlalchemy.orm.session import close_all_sessions

from customs import Utility
from config import Config
from .models import Base, DbUser, DbGuild


class CRUD:
    def __init__(self):
        self.engine = create_engine(Utility.get_db_url(), logging_name=Config.POSTGRES["db_name"])
        _session = sessionmaker(bind=self.engine)
        self.session = _session()

    @property
    def current_session(self) -> sessionmaker():
        """
        Current session
        """
        return self.session

    @property
    def dirty(self) -> IdentitySet:
        """
        The data that is modified, but not updated.
        """
        return self.session.dirty

    @property
    def new(self) -> IdentitySet:
        """
        The PENDING new data.
        """
        return self.session.new

    def init(self) -> None:
        Base.metadata.create_all(self.engine)

    def get_user_record(self, user: nextcord.User) -> Optional[DbUser]:
        return self.session.query(DbUser).filter_by(id=user.id).one_or_none()

    def get_guild_record(self, guild: nextcord.Guild) -> Optional[DbGuild]:
        return self.session.query(DbGuild).filter_by(id=guild.id).one_or_none()

    def create_user_record(self, user_record: DbUser) -> DbUser:
        if not self.session.query(DbUser).filter_by(id=user_record.id).one_or_none():
            self.session.add(user_record)

        return user_record

    def create_guild_record(self, guild_record: DbGuild) -> DbGuild:
        if not self.session.query(DbGuild).filter_by(id=guild_record.id).one_or_none():
            self.session.add(guild_record)

        return guild_record

    def delete_guild_record(self, guild_record: DbGuild) -> None:
        self.session.delete(guild_record)

    def delete_user_record(self, user_record: DbUser) -> None:
        self.session.delete(user_record)

    def rollback(self) -> None:
        """
        Revert ALL changes made on current session. If you use this after save_changes(), congrats, you did nothing!
        """
        self.session.rollback()

    def save_changes(self) -> None:
        """
        Save changes made on current session. In some cases, this will clear the pending queue of rollback().

        "Mom, but it works in my codes!"
                    - Swyrin
        """
        self.session.commit()

    def close_all_sessions(self) -> None:
        close_all_sessions()
