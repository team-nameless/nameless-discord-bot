import discord
from discord import app_commands

from nameless import shared_vars


__all__ = ["Autocomplete"]


class Autocomplete:
    @staticmethod
    async def load_module_complete(
        dummy, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """An autofill method for load module command"""
        choices = shared_vars.unloaded_cogs_list
        a = [app_commands.Choice(name=choice, value=choice) for choice in choices if current.lower() in choice.lower()]
        return a

    @staticmethod
    async def module_complete(dummy, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """An autofill method for reload and unload module command."""
        choices = shared_vars.loaded_cogs_list
        return [
            app_commands.Choice(name=choice, value=choice) for choice in choices if current.lower() in choice.lower()
        ]
