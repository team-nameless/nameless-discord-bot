from typing import Optional, Tuple

import discord
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.util import IdentitySet

from config import Config
from customs import Utility
from .models import Base, DbUser, DbGuild

__all__ = ["CRUD"]


class CRUD:
    """
    Basic database CRUD operations.
    """

    def __init__(self, config_cls=None):
        if not config_cls:
            config_cls = Config

        self.db_url: str = Utility.get_db_url(config_cls)
        self.engine = create_engine(
            self.db_url, logging_name=config_cls.DATABASE["db_name"]
        )
        _session = sessionmaker(bind=self.engine)
        self.session = _session()
        Base.metadata.create_all(self.engine)

    @property
    def current_session(self) -> Session:
        """Current session."""
        return self.session

    @property
    def dirty(self) -> IdentitySet:
        """The data that is modified, but not updated to database."""
        return self.session.dirty

    @property
    def new(self) -> IdentitySet:
        """The PENDING new data."""
        return self.session.new

    def get_or_create_user_record(
        self, discord_user: discord.User
    ) -> Tuple[DbUser, bool]:
        """
        Get an existing discord_user record, create a new record if one doesn't exist.
        :param discord_user: User entity of discord.
        :return: User record in database, True if the record is new.
        """
        u = self.get_user_record(discord_user)
        if not u:
            return self.create_user_record(discord_user), True

        return u, False

    def get_or_create_guild_record(
        self, discord_guild: discord.Guild
    ) -> Tuple[DbGuild, bool]:
        """
        Get an existing guild record, create a new record if one doesn't exist.
        :param discord_guild: Guild entity of discord.
        :return: Guild record in database, True if the record is new.
        """
        g = self.get_guild_record(discord_guild)

        if not g:
            return self.create_guild_record(discord_guild), True

        return g, False

    def get_user_record(self, discord_user: discord.User) -> Optional[DbUser]:
        """Get user record in database, None if nothing."""
        return (
            self.session.query(DbUser)
            .filter_by(discord_id=discord_user.id)
            .one_or_none()
        )

    def get_guild_record(self, discord_guild: discord.Guild) -> Optional[DbGuild]:
        """Get guild record in database, None if nothing."""
        return (
            self.session.query(DbGuild)
            .filter_by(discord_id=discord_guild.id)
            .one_or_none()
        )

    def create_user_record(self, discord_user: discord.User) -> DbUser:
        """Create a database row for the Discord user and return one."""
        decoy_user = DbUser(discord_user.id)

        if (
            not self.session.query(DbUser)
            .filter_by(discord_id=discord_user.id)
            .one_or_none()
        ):
            self.session.add(decoy_user)
            self.save_changes()
            return decoy_user

        return self.session.query(DbUser).filter_by(discord_id=discord_user.id).one()

    def create_guild_record(self, discord_guild: discord.Guild) -> DbGuild:
        """Create a database row for the Discord guild and return one."""
        decoy_guild = DbGuild(discord_guild.id)

        if (
            not self.session.query(DbGuild)
            .filter_by(discord_id=discord_guild.id)
            .one_or_none()
        ):
            self.session.add(decoy_guild)
            self.save_changes()
            return decoy_guild

        return self.session.query(DbGuild).filter_by(discord_id=discord_guild.id).one()

    def delete_guild_record(self, guild_record: DbGuild) -> None:
        """
        Delete a guild record from the database.
        :param guild_record: Guild record to delete.
        """
        self.session.delete(guild_record)

    def delete_user_record(self, user_record: DbUser) -> None:
        """
        Delete a discord_user record from the database.
        :param user_record: User record to delete.
        """
        self.session.delete(user_record)

    def rollback(self) -> None:
        """
        Revert ALL changes made on current session.
        """
        self.session.rollback()

    def save_changes(self) -> None:
        """
        Save changes made on current session. Clears rollback() queue if any.
        """
        self.session.commit()
