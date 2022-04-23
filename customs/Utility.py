from typing import Callable

import nextcord

from config import Config
from urllib.parse import quote_plus


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
        postgres = Config.DATABASE
        dialect: str = postgres["dialect"]
        driver: str = "" if not postgres["driver"] else f"+{postgres['driver']}"
        username: str = postgres["username"]
        password: str = "" if not postgres["password"] else f":{postgres['password']}"
        host: str = postgres["host"]
        port: int = postgres["port"]
        db_name: str = postgres["db_name"]
        
        return f"{dialect}{quote_plus(driver, safe='+')}://{username}{quote_plus(password, safe=':')}@{host}:{port}/{db_name}"

    @staticmethod
    def message_waiter(
        interaction: nextcord.Interaction,
    ) -> Callable[[nextcord.Message], bool]:
        """
        Message waiter to use with Client.wait_for("message", ...).

        Usages:
            message: nextcord.Message = await bot.wait_for("message", check=wait_for)

        :param interaction: Current interaction context.
        :return: The waiter function.
        """

        def message_checker(message: nextcord.Message) -> bool:
            return (
                message.author.id == interaction.user.id
                and interaction.channel_id == message.channel.id
            )

        return message_checker

    @staticmethod
    async def get_or_create_role(
        interaction: nextcord.Interaction, name: str, reason: str
    ) -> tuple[nextcord.Role, bool]:
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
