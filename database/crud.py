from typing import Optional, Tuple

import discord
import pymongo
from pymongo.collection import Collection
from pymongo.database import Database
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.orm.session import close_all_sessions
from sqlalchemy.util import IdentitySet

from config import Config
from customs import Utility
from .models import Base, DbUser, DbGuild

__all__ = ["CRUD"]


class CRUD:
    """
    Basic database CRUD operations.
    """

    def __init__(self):
        self.is_mongo = Config.DATABASE["dialect"] == "mongodb"

        if self.is_mongo:
            self.mongo_client = pymongo.MongoClient(Utility.get_db_url())
            self.mongo_engine: Database = self.mongo_client[Config.DATABASE["db_name"]]

            self.mongo_guilds: Collection = self.mongo_engine.get_collection(
                DbGuild.__tablename__
            )
            self.mongo_users: Collection = self.mongo_engine.get_collection(
                DbUser.__tablename__
            )
        else:
            self.engine = create_engine(
                Utility.get_db_url(), logging_name=Config.DATABASE["db_name"]
            )
            _session = sessionmaker(bind=self.engine)
            self.session = _session()
            Base.metadata.create_all(self.engine)

    @property
    def current_session(self) -> Session:
        """
        Current session, None in MongoDB.
        """
        return self.session

    @property
    def dirty(self) -> IdentitySet:
        """
        The data that is modified, but not updated to database, None in MongoDB.
        """
        return self.session.dirty

    @property
    def new(self) -> IdentitySet:
        """
        The PENDING new data, None in MongoDB.
        """
        return self.session.new

    def get_or_create_user_record(self, user: discord.User) -> Tuple[DbUser, bool]:
        """
        Get an existing user record, create a new record if one doesn't exist.
        :param user: User entity of discord.
        :return: User record in database. True if the returned record is the new one, False otherwise.
        """
        u = self.get_user_record(user)
        if not u:
            return self.create_user_record(user), True

        return u, False

    def get_or_create_guild_record(self, guild: Optional[discord.Guild]) -> Tuple[DbGuild, bool]:
        """
        Get an existing guild record, create a new record if one doesn't exist.
        :param guild: Guild entity of discord.
        :return: Guild record in database. True if the returned record is the new one, False otherwise.
        """
        if guild:
            g = self.get_guild_record(guild)
            if not g:
                return self.create_guild_record(guild), True

            return g, False

    def get_user_record(self, user: discord.User) -> Optional[DbUser]:
        if self.is_mongo:
            record = self.mongo_users.find_one({"id": user.id})
            if record:
                return DbUser.from_dict(dict(record))

            return None

        return self.session.query(DbUser).filter_by(id=user.id).one_or_none()

    def get_guild_record(self, guild: Optional[discord.Guild]) -> Optional[DbGuild]:
        if guild:
            if self.is_mongo:
                record = self.mongo_guilds.find_one({"id": guild.id})
                if record:
                    return DbGuild.from_dict(dict(record))

                return None

            return self.session.query(DbGuild).filter_by(id=guild.id).one_or_none()

    def create_user_record(self, user: discord.User) -> DbUser:
        decoy_user = DbUser(id=user.id)

        if self.is_mongo:  # noqa
            self.mongo_users.insert_one(decoy_user.to_dict())
            return decoy_user

        if not self.session.query(DbUser).filter_by(id=user.id).one_or_none():
            self.session.add(decoy_user)
            self.save_changes()
            return decoy_user

        return self.session.query(DbUser).filter_by(id=user.id).one()

    def create_guild_record(self, guild: Optional[discord.Guild]) -> DbGuild:
        if guild:
            decoy_guild = DbGuild(id=guild.id)

            if self.is_mongo:  # noqa
                self.mongo_guilds.insert_one(decoy_guild.to_dict())
                return decoy_guild

            if not self.session.query(DbGuild).filter_by(id=guild.id).one_or_none():
                self.session.add(decoy_guild)
                self.save_changes()
                return decoy_guild

            return self.session.query(DbGuild).filter_by(id=guild.id).one()

    def delete_guild_record(self, guild_record: DbGuild) -> None:
        """
        Delete a guild record from the database.
        :param guild_record: Guild record to delete.
        """
        if self.is_mongo:
            self.mongo_guilds.delete_many({"id": guild_record.id})
        else:
            self.session.delete(guild_record)

    def delete_user_record(self, user_record: DbUser) -> None:
        """
        Delete a user record from the database.
        :param user_record: User record to delete.
        """
        if self.is_mongo:
            self.mongo_users.delete_many({"id": user_record.id})
        else:
            self.session.delete(user_record)

    def rollback(self) -> None:
        """
        Revert ALL changes made on current session. If you use this after save_changes(), congrats, you did nothing!

        """
        if self.is_mongo:
            pass
        else:
            self.session.rollback()

    def save_changes(
        self, user_record: DbUser = None, guild_record: DbGuild = None
    ) -> None:
        """
        Save changes made on current session. In some cases, this will clear the pending queue of rollback().

        "Mom, but it works in my codes!"
                    - Swyrin
        """
        if self.is_mongo:
            if user_record:
                self.mongo_users.update_one(
                    {"id": user_record.id}, {"$set": user_record.to_dict()}
                )

            if guild_record:
                self.mongo_guilds.update_one(
                    {"id": guild_record.id}, {"$set": guild_record.to_dict()}
                )
        else:
            self.session.commit()

    def close_all_sessions(self) -> None:
        if self.is_mongo:
            self.mongo_client.close()
        else:
            close_all_sessions()
