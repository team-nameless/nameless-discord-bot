from typing import Callable, Tuple
from urllib.parse import quote_plus as qp

import discord
from discord.ext import commands

from config import Config

__all__ = ["Utility"]


class Utility:
    """
    List of utilities that aid the further developments of this project.
    """

    @staticmethod
    def get_db_url() -> str:
        """
        Get the database connection URL based on the config.py content.

        :return: Database connection URL
        """
        db = Config.DATABASE
        dialect = db["dialect"]
        driver = qp(f"+{db['driver']}", safe="+") if db["driver"] else ""
        username = db["username"] if db["username"] else ""
        password = qp(f":{db['password']}", safe=":") if db["password"] else ""
        at = qp("@", safe="@") if username and password else ""
        host = db["host"]
        port = qp(f":{db['port']}", safe=":") if db["port"] else ""
        db_name = db["db_name"]
        return f"{dialect}{driver}://{username}{password}{at}{host}{port}/{db_name}"

    @staticmethod
    def message_waiter(ctx: commands.Context) -> Callable[[discord.Message], bool]:
        """
        Message waiter to use with Client.wait_for("message", ...).

        Usages:
            message: discord.Message = await bot.wait_for("message", check=wait_for)

        :param ctx: Current context.
        :return: The waiter function.
        """

        def message_checker(message: discord.Message) -> bool:
            return (
                message.author.id == ctx.author.id
                and ctx.channel.id == message.channel.id
            )

        return message_checker

    @staticmethod
    async def get_or_create_role(
        name: str, reason: str, ctx: commands.Context
    ) -> Tuple[discord.Role, bool]:
        guild_roles = ctx.guild.roles
        role_exists = any(role.name == name for role in guild_roles)
        if role_exists:
            roles = [role for role in guild_roles if role.name == name]
            return roles[0], False

        return await ctx.guild.create_role(name=name, reason=reason), True
