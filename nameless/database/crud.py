import logging
from typing import Optional, Union

import discord
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.util import IdentitySet

from nameless.commons import Utility
from NamelessConfig import NamelessConfig

from .models import Base, DbGuild, DbUser


__all__ = ["CRUD"]


class CRUD:
    """
    Basic database CRUD operations.
    """

    def __init__(self):
        (
            self.db_url,
            self.dialect,
            self.driver,
            self.host,
            self.port,
            self.username,
            self.password,
            self.db_name,
        ) = Utility.get_db_url()
        self.engine = create_engine(
            self.db_url,
            logging_name=self.db_name,
            hide_parameters=not getattr(NamelessConfig, "DEV", False),
        )
        _session = sessionmaker(bind=self.engine)
        self.__session = _session()
        Base.metadata.create_all(self.engine)

    @property
    def session(self) -> Session:
        """Current session."""
        return self.__session

    @property
    def dirty(self) -> IdentitySet:
        """The data that is modified, but not updated to database"""
        return self.__session.dirty

    @property
    def new(self) -> IdentitySet:
        """The pending new data"""
        return self.__session.new

    def is_new_record(self, model: sqlalchemy.Table, **kwargs) -> bool:
        """Check if the record is new one"""
        return self.session.query(model).filter_by(**kwargs).one_or_none() is None

    def get_or_create_user_record(self, discord_user: Union[discord.Member, discord.User, discord.Object]) -> DbUser:
        """
        Get an existing discord_user record, create a new record if one doesn't exist
        :param discord_user: User entity of discord.
        :return: User record in database
        """
        u = self.get_user_record(discord_user)

        if not u:
            return self.create_user_record(discord_user)

        return u

    def get_or_create_guild_record(self, discord_guild: Optional[Union[discord.Guild, discord.Object]]) -> DbGuild:
        """
        Get an existing guild record, create a new record if one doesn't exist
        :param discord_guild: Guild entity of discord
        :return: Guild record in database
        """
        if not discord_guild:
            raise ValueError("You are executing guild database query in a not-a-guild! This is invalid!")

        g = self.get_guild_record(discord_guild)

        if not g:
            return self.create_guild_record(discord_guild)

        return g

    def get_user_record(self, discord_user: Union[discord.Member, discord.User, discord.Object]) -> Optional[DbUser]:
        """Get user record in database"""
        return self.session.query(DbUser).filter_by(discord_id=discord_user.id).one_or_none()

    def get_guild_record(self, discord_guild: Optional[Union[discord.Guild, discord.Object]]) -> Optional[DbGuild]:
        """Get guild record in database"""
        if not discord_guild:
            raise ValueError("You are executing guild database query in a not-a-guild! This is invalid!")

        return self.session.query(DbGuild).filter_by(discord_id=discord_guild.id).one_or_none()

    def create_user_record(self, discord_user: Union[discord.Member, discord.User, discord.Object]) -> DbUser:
        """Create a database entry for the Discord user and return one"""
        decoy_user = DbUser(discord_user.id)

        if not self.session.query(DbUser).filter_by(discord_id=discord_user.id).one_or_none():  # noqa
            self.session.add(decoy_user)
            self.save_changes()
            return decoy_user

        return self.session.query(DbUser).filter_by(discord_id=discord_user.id).one()

    def create_guild_record(self, discord_guild: Optional[Union[discord.Guild, discord.Object]]) -> DbGuild:
        """Create a database entry for the Discord guild and return one"""
        if not discord_guild:
            raise ValueError("You are executing guild database query in a not-a-guild! This is invalid!")

        decoy_guild = DbGuild(discord_guild.id)

        if not self.session.query(DbGuild).filter_by(discord_id=discord_guild.id).one_or_none():  # noqa
            self.session.add(decoy_guild)
            self.save_changes()
            return decoy_guild

        return self.session.query(DbGuild).filter_by(discord_id=discord_guild.id).one()

    def delete_guild_record(self, guild_record: Optional[DbGuild]) -> None:
        """
        Delete a guild record from the database
        :param guild_record: Guild record to delete
        """
        if guild_record is None:
            raise ValueError("You are deleting a null guild! Did you ensure that this is not a DM?")

        logging.info("Removing guild entry with ID %s from the database", guild_record.discord_id)
        self.session.delete(guild_record)

    def delete_user_record(self, user_record: Optional[DbUser]) -> None:
        """
        Delete a discord_user record from the database
        :param user_record: User record to delete
        """
        if user_record is None:
            raise ValueError("You are deleting a null user!")

        logging.info("Removing user entry with ID %s from the database", user_record.discord_id)
        self.session.delete(user_record)

    def rollback(self) -> None:
        """Revert changes made on current session"""
        self.session.rollback()
        logging.info("Rolling back changes in databases")

    def save_changes(self) -> None:
        """Save changes made on current session"""
        self.session.commit()
