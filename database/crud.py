from typing import Optional, Tuple, Union, Type

import discord
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.util import IdentitySet

import config
from customs import Utility
from .models import Base, DbUser, DbGuild

__all__ = ["CRUD"]


class CRUD:
    """
    Basic database CRUD operations.
    """

    def __init__(self, config_cls: Type[config.Config] = config.Config):
        self.db_url: str = Utility.get_db_url(config_cls)
        self.engine = create_engine(
            self.db_url, logging_name=config_cls.DATABASE["db_name"]
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

    def get_or_create_user_record(
        self, discord_user: Union[discord.Member, discord.User, discord.Object]
    ) -> Tuple[Optional[DbUser], bool]:
        """
        Get an existing discord_user record, create a new record if one doesn't exist
        :param discord_user: User entity of discord.
        :return: User record in database, True if the record is new.
        """
        u = self.get_user_record(discord_user)
        if not u:
            return self.create_user_record(discord_user), True

        return u, False

    def get_or_create_guild_record(
        self, discord_guild: Optional[Union[discord.Guild, discord.Object]]
    ) -> Tuple[Optional[DbGuild], bool]:
        """
        Get an existing guild record, create a new record if one doesn't exist
        :param discord_guild: Guild entity of discord
        :return: Guild record in database, True if the record is new
        """
        if discord_guild:
            g = self.get_guild_record(discord_guild)

            if not g:
                return self.create_guild_record(discord_guild), True

            return g, False

        return None, True

    def get_user_record(
        self, discord_user: Union[discord.Member, discord.User, discord.Object]
    ) -> Optional[DbUser]:
        """Get user record in database"""
        return (
            self.session.query(DbUser)
            .filter_by(discord_id=discord_user.id)
            .one_or_none()
        )

    def get_guild_record(
        self, discord_guild: Optional[Union[discord.Guild, discord.Object]]
    ) -> Optional[DbGuild]:
        """Get guild record in database"""
        if discord_guild:
            return (
                self.session.query(DbGuild)
                .filter_by(discord_id=discord_guild.id)
                .one_or_none()
            )

        return None

    def create_user_record(
        self, discord_user: Union[discord.Member, discord.User, discord.Object]
    ) -> DbUser:
        """Create a database entry for the Discord user and return one"""
        decoy_user = DbUser(discord_user.id)

        if (  # noqa
            not self.session.query(DbUser)
            .filter_by(discord_id=discord_user.id)
            .one_or_none()
        ):
            self.session.add(decoy_user)
            self.save_changes()
            return decoy_user

        return self.session.query(DbUser).filter_by(discord_id=discord_user.id).one()

    def create_guild_record(
        self, discord_guild: Optional[Union[discord.Guild, discord.Object]]
    ) -> Optional[DbGuild]:
        """Create a database entry for the Discord guild and return one"""

        if discord_guild:
            decoy_guild = DbGuild(discord_guild.id)

            if (  # noqa
                not self.session.query(DbGuild)
                .filter_by(discord_id=discord_guild.id)
                .one_or_none()
            ):
                self.session.add(decoy_guild)
                self.save_changes()
                return decoy_guild

            return (
                self.session.query(DbGuild).filter_by(discord_id=discord_guild.id).one()
            )

        return None

    def delete_guild_record(self, guild_record: Optional[DbGuild]) -> None:
        """
        Delete a guild record from the database
        :param guild_record: Guild record to delete
        """
        if guild_record:
            self.session.delete(guild_record)
        else:
            raise ValueError("Unable to delete a null entity")

    def delete_user_record(self, user_record: Optional[DbUser]) -> None:
        """
        Delete a discord_user record from the database
        :param user_record: User record to delete
        """
        if user_record:
            self.session.delete(user_record)
        else:
            raise ValueError("Unable to delete a null entity")

    def rollback(self) -> None:
        """Revert changes made on current session"""
        self.session.rollback()

    def save_changes(self) -> None:
        """Save changes made on current session"""
        self.session.commit()
