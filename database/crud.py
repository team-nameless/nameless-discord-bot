from typing import Optional

import nextcord
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import close_all_sessions
from sqlalchemy.util import IdentitySet

from config import Config
from customs import Utility
from .models import Base, DbUser, DbGuild


class CRUD:
    """
    Basic PostgreSQL CRUD operations required to make this project work.
    """

    def __init__(self):
        self.engine = create_engine(
            Utility.get_db_url(), logging_name=Config.DATABASE["db_name"]
        )
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
        The data that is modified, but not updated to database.
        """
        return self.session.dirty

    @property
    def new(self) -> IdentitySet:
        """
        The PENDING new data.
        """
        return self.session.new

    def init(self) -> None:
        """
        Normally you don't need to care about this.
        """
        Base.metadata.create_all(self.engine)

    def get_or_create_user_record(self, user: nextcord.User) -> tuple[DbUser, bool]:
        """
        Get an existing user record, create a new record if one doesn't exist.
        :param user: User entity of nextcord.
        :return: User record in database. True if the returned record is the new one, False otherwise.
        """
        u = self.__get_user_record(user)
        if not u:
            return self.__create_user_record(user), True
        else:
            return u, False

    def get_or_create_guild_record(self, guild: nextcord.Guild) -> tuple[DbGuild, bool]:
        """
        Get an existing guild record, create a new record if one doesn't exist.
        :param guild: Guild entity of nextcord.
        :return: Guild record in database. True if the returned record is the new one, False otherwise.
        """
        g = self.__get_guild_record(guild)
        if not g:
            return self.__create_guild_record(guild), True
        else:
            return g, False

    def __get_user_record(self, user: nextcord.User) -> Optional[DbUser]:
        return self.session.query(DbUser).filter_by(id=user.id).one_or_none()

    def __get_guild_record(self, guild: nextcord.Guild) -> Optional[DbGuild]:
        return self.session.query(DbGuild).filter_by(id=guild.id).one_or_none()

    def __create_user_record(self, user: nextcord.User) -> DbUser:
        decoy_user = DbUser(id=user.id)

        if not self.session.query(DbUser).filter_by(id=user.id).one_or_none():
            self.session.add(decoy_user)
            self.save_changes()
            return decoy_user
        else:
            return self.session.query(DbUser).filter_by(id=user.id).one()

    def __create_guild_record(self, guild: nextcord.Guild) -> DbGuild:
        decoy_guild = DbGuild(id=guild.id)

        if not self.session.query(DbGuild).filter_by(id=guild.id).one_or_none():
            self.session.add(decoy_guild)
            self.save_changes()
            return decoy_guild
        else:
            return self.session.query(DbGuild).filter_by(id=guild.id).one()

    def delete_guild_record(self, guild_record: DbGuild) -> None:
        """
        Delete a guild record from the database.
        :param guild_record: Guild record to delete.
        """
        self.session.delete(guild_record)

    def delete_user_record(self, user_record: DbUser) -> None:
        """
        Delete a user record from the database.
        :param user_record: User record to delete.
        """
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

    @staticmethod
    def close_all_sessions() -> None:
        close_all_sessions()
