import contextlib
import logging

from discord import InteractionResponded
from discord._types import ClientT
from discord.app_commands import AppCommandError, CommandTree, errors
from discord.interactions import Interaction

from nameless.nameless import Nameless

__all__ = ["NamelessCommandTree"]


class NamelessCommandTree(CommandTree[Nameless]):
    def __init__(self, client, *, fallback_to_global: bool = True):
        super().__init__(client, fallback_to_global=fallback_to_global)

    async def interaction_check(self, interaction: Interaction) -> bool:
        user = interaction.user
        guild = interaction.guild

        is_user_blacklisted = await self.client.is_blacklisted(user=user)
        is_guild_blacklisted = await self.client.is_blacklisted(guild=guild)

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

    async def on_error(self, interaction: Interaction[ClientT], error: AppCommandError, /) -> None:
        content = f"Something went wrong when executing the command:\n```\n{error}\n```"

        if not isinstance(error, errors.CommandSignatureMismatch):
            with contextlib.suppress(InteractionResponded):
                await interaction.response.defer()

            await interaction.followup.send(content)

            logging.exception("[on_command_error] We have gone under a crisis!!!", stack_info=True, exc_info=error)
