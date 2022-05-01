from typing import Callable
from urllib.parse import quote_plus as qp

import discord

from config import Config


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
        dialect: str = db["dialect"]
        driver: str = qp(f"+{db['driver']}", safe='+') if db["driver"] else ""
        username: str = db["username"]
        password: str = qp(f":{db['password']}", safe=':') if db["password"] else ""
        host: str = db["host"]
        port: int = db["port"]
        db_name: str = db["db_name"]

        return f"{dialect}{driver}://{username}{password}@{host}:{port}/{db_name}"

    @staticmethod
    def get_mongo_db_url() -> str:
        """
        Get the MongoDB database connection URL based on the config.py content.

        :return: MongoDB database connection URL
        """
        mongo = Config.MONGODB
        username = mongo["username"] if mongo["username"] else ""
        password = qp(f":{mongo['password']}") if mongo["password"] else ""
        at = qp("@") if username and password else ""
        host = mongo["host"]
        port = qp(f":{mongo['port']}") if mongo["port"] else ""

        if mongo["is_atlas"]:
            cluster_name = mongo["cluster_name"]
            return f"mongodb+srv://{username}{password}{at}{cluster_name}.spdhq.mongodb.net/"
        else:
            return f"mongodb://{username}{password}{at}{host}{port}/"

    @staticmethod
    def message_waiter(
        interaction: discord.Interaction,
    ) -> Callable[[discord.Message], bool]:
        """
        Message waiter to use with Client.wait_for("message", ...).

        Usages:
            message: discord.Message = await bot.wait_for("message", check=wait_for)

        :param interaction: Current interaction context.
        :return: The waiter function.
        """

        def message_checker(message: discord.Message) -> bool:
            return (
                message.author.id == interaction.user.id
                and interaction.channel_id == message.channel.id
            )

        return message_checker

    @staticmethod
    async def get_or_create_role(
        interaction: discord.Interaction, name: str, reason: str
    ) -> tuple[discord.Role, bool]:
        """
        Get or create new role.
        :param interaction: Current interaction context.
        :param name: Role name.
        :param reason: Reason to create role name, as in the audit log.
        :return: The role. True if the returned one is new, False otherwise.
        """
        guild_roles = interaction.guild.roles
        role_exists = any(role.name == name for role in guild_roles)
        if role_exists:
            roles = [role for role in guild_roles if role.name == name]
            return roles[0], False
        else:
            return await interaction.guild.create_role(name=name, reason=reason), True
