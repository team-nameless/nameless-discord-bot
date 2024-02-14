import logging

import discord
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.util import IdentitySet

from nameless.commons import Utility
from nameless.customs import shared_variables

from .models import Base, DbGuild, DbUser

__all__ = ["CRUD"]

from nameless.commons import staticproperty


class CRUD:
    """
    Basic database CRUD operations.
    """

    (db_url, dialect, driver, host, port, username, password, db_name) = Utility.get_db_url()

    engine = create_engine(
        db_url,
        logging_name=db_name,
        hide_parameters=not shared_variables.nameless_debug_mode,
        isolation_level="AUTOCOMMIT",
    )

    _session = sessionmaker(bind=engine)
    session = _session()

    @staticmethod
    def init():
        Base.metadata.create_all(CRUD.engine)

    @staticmethod
    def in_case_of_getting_f_up():
        Base.metadata.drop_all(CRUD.engine)

    @staticproperty
    def dirty(self) -> IdentitySet:
        """The data that is modified, but not updated to database"""
        return self.session.dirty

    @staticproperty
    def new(self) -> IdentitySet:
        """The pending new data"""
        return self.session.new

    @staticmethod
    def is_new_record(model: sqlalchemy.Table, **kwargs) -> bool:
        """Check if the record is new one"""
        return CRUD.session.query(model).filter_by(**kwargs).one_or_none() is None

    @staticmethod
    def get_or_create_user_record(discord_user: discord.Member | discord.User | discord.Object) -> DbUser:
        """
        Get an existing discord_user record, create a new record if one doesn't exist
        :param discord_user: User entity of discord.
        :return: User record in database
        """
        u = CRUD.get_user_record(discord_user)

        if not u:
            return CRUD.create_user_record(discord_user)

        return u

    @staticmethod
    def get_or_create_guild_record(discord_guild: discord.Guild | discord.Object | None) -> DbGuild:
        """
        Get an existing guild record, create a new record if one doesn't exist
        :param discord_guild: Guild entity of discord
        :return: Guild record in database
        """
        if not discord_guild:
            raise ValueError("You are executing guild database query in a not-a-guild! This is invalid!")

        g = CRUD.get_guild_record(discord_guild)

        if not g:
            return CRUD.create_guild_record(discord_guild)

        return g

    @staticmethod
    def get_user_record(discord_user: discord.Member | discord.User | discord.Object) -> DbUser | None:
        """Get user record in database"""
        return CRUD.session.query(DbUser).filter_by(discord_id=discord_user.id).one_or_none()

    @staticmethod
    def get_guild_record(discord_guild: discord.Guild | discord.Object | None) -> DbGuild | None:
        """Get guild record in database"""
        if not discord_guild:
            raise ValueError("You are executing guild database query in a not-a-guild! This is invalid!")

        return CRUD.session.query(DbGuild).filter_by(discord_id=discord_guild.id).one_or_none()

    @staticmethod
    def create_user_record(discord_user: discord.Member | discord.User | discord.Object) -> DbUser:
        """Create a database entry for the Discord user and return one"""
        decoy_user = DbUser(discord_user.id)

        if not CRUD.session.query(DbUser).filter_by(discord_id=discord_user.id).one_or_none():  # noqa
            CRUD.session.add(decoy_user)

            return decoy_user

        return CRUD.session.query(DbUser).filter_by(discord_id=discord_user.id).one()

    @staticmethod
    def create_guild_record(discord_guild: discord.Guild | discord.Object | None) -> DbGuild:
        """Create a database entry for the Discord guild and return one"""
        if not discord_guild:
            raise ValueError("You are executing guild database query in a not-a-guild! This is invalid!")

        decoy_guild = DbGuild(discord_guild.id)

        if not CRUD.session.query(DbGuild).filter_by(discord_id=discord_guild.id).one_or_none():  # noqa
            CRUD.session.add(decoy_guild)

            return decoy_guild

        return CRUD.session.query(DbGuild).filter_by(discord_id=discord_guild.id).one()

    @staticmethod
    def delete_guild_record(guild_record: DbGuild | None) -> None:
        """
        Delete a guild record from the database
        :param guild_record: Guild record to delete
        """
        if guild_record is None:
            raise ValueError("You are deleting a null guild! Did you ensure that this is not a DM?")

        logging.info("Removing guild entry with ID %s from the database", guild_record.discord_id)

        try:
            CRUD.session.delete(guild_record)
        except InvalidRequestError:
            CRUD.session.expunge(guild_record)

    @staticmethod
    def delete_user_record(user_record: DbUser | None) -> None:
        """
        Delete a discord_user record from the database
        :param user_record: User record to delete
        """
        if user_record is None:
            raise ValueError("You are deleting a null user!")

        logging.info("Removing user entry with ID %s from the database", user_record.discord_id)

        try:
            CRUD.session.delete(user_record)
        except InvalidRequestError:
            CRUD.session.expunge(user_record)

    @staticmethod
    def rollback() -> None:
        """Revert changes made on current session"""
        CRUD.session.rollback()
        logging.info("Rolling back changes in databases")

    @staticmethod
    def save_changes() -> None:
        """Save changes made on current session"""
        CRUD.session.commit()
