import logging

import discord
from prisma import Prisma, models

__all__ = ["NamelessPrisma"]

_raw_db = Prisma(auto_register=True)


class NamelessPrisma:
    """A Prisma class to connect to Prisma ORM."""

    @staticmethod
    async def init():
        """Intialize Prisma connection."""
        logging.info("Connecting to database.")
        await _raw_db.connect()

    @staticmethod
    async def dispose():
        """Properly dispose Prisma connection."""
        logging.warning("Disconnecting from Prisma.")
        await _raw_db.disconnect()
        logging.warning("Prisma WILL NOT be available from now on.")

    @staticmethod
    async def get_guild_entry(guild: discord.Guild) -> models.Guild:
        """Create a Prisma Guild entry if not exist."""
        return await _raw_db.guild.upsert(
            where={"Id": guild.id},
            data={"create": {"Id": guild.id, "HoneypotChannelId": 0}, "update": {}},
        )

    @staticmethod
    async def get_user_entry(user: discord.User | discord.Member) -> models.User:
        """Create a Prisma User entry if not exist."""
        return await _raw_db.user.upsert(
            where={"Id": user.id},
            data={"create": {"Id": user.id, "MaimaiFriendCode": 0}, "update": {}},
        )
