from collections.abc import Callable
from typing import cast, Any, Coroutine

import discord
from discord import app_commands
from discord.ext import commands

__all__ = ["BaseCheck"]

from nameless import Nameless


class BaseCheck:
    """Base check class. Containing some useful decorators."""

    def __init__(self):
        pass

    @staticmethod
    def allow_display_in_help_message(check_fn: Callable[[commands.Context], bool]):
        """
        Bypasses command-specific checks.
        Note: this is a decorator for a check.
        """

        def pred(interaction: discord.Interaction, /, **kwargs) -> bool:
            # This will be always true for a while
            return True

        return app_commands.check(pred)

    @staticmethod
    def require_interaction_intents(intents: list):
        """
        Require the bot to have specific intent(s).
        Note: this is a decorator for an application command.
        """

        async def pred(interaction: discord.Interaction, /, **kwargs) -> bool:
            set_intents = interaction.client.intents

            return all(set_intents.value & intent.flag == intent.flag for intent in intents)

        return app_commands.check(pred)

    @staticmethod
    def owns_the_bot():
        """
        Require the command author to be in the owner(s) list of the bot.
        Note: this is a decorator for an application command.
        """

        async def pred(interaction: discord.Interaction, /, **kwargs) -> bool:
            nameless: Nameless = interaction.client
            return await nameless.is_owner(interaction.user)

        return app_commands.check(pred)
