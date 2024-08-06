import contextlib
import logging

import discord
from discord import InteractionResponded
from discord.app_commands import AppCommandError, CommandTree, errors
from discord.interactions import Interaction

from NamelessConfig import NamelessConfig
from nameless.nameless import Nameless

__all__ = ["NamelessCommandTree"]


class NamelessCommandTree(CommandTree[Nameless]):
    """Custom CommandTree for nameless*, for handling blacklists and custom error handling."""

    def __init__(self, client, *, fallback_to_global: bool = True):
        super().__init__(client, fallback_to_global=fallback_to_global)

    async def is_blacklisted(
        self, *, user: discord.User | discord.Member | None = None, guild: discord.Guild | None = None
    ) -> bool:
        """Check if an entity is blacklisted from using the bot."""
        # The owners, even if they are in the blacklist, can still use the bot.
        if user and await self.client.is_owner(user):
            return False

        if guild and guild.id in NamelessConfig.BLACKLISTS.GUILD_BLACKLIST:
            return True

        if user and user.id in NamelessConfig.BLACKLISTS.USER_BLACKLIST:
            return True

        return False

    async def interaction_check(self, interaction: Interaction) -> bool:
        user = interaction.user
        guild = interaction.guild

        is_user_blacklisted = await self.is_blacklisted(user=user)
        is_guild_blacklisted = await self.is_blacklisted(guild=guild)

        if is_user_blacklisted:
            await interaction.response.send_message(
                "You have been blacklisted from using me, " "please contact the owner for more information.",
                ephemeral=True,
            )
            return False

        if is_guild_blacklisted:
            await interaction.response.send_message(
                "This guild has been blacklisted from using me, " "please inform the guild owner about this.",
                ephemeral=True,
            )
            return False

        return True

    async def on_error(self, interaction: Interaction[Nameless], error: AppCommandError, /) -> None:
        content = f"Something went wrong when executing the command:\n```\n{error}\n```"

        if not isinstance(error, errors.CommandSignatureMismatch):
            with contextlib.suppress(InteractionResponded):
                await interaction.response.defer()

            await interaction.followup.send(content)

            logging.exception("[on_command_error] We have gone under a crisis!!!", stack_info=True, exc_info=error)
