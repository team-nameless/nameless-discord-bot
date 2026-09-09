from __future__ import annotations

from typing import TYPE_CHECKING, Self, override

import discord

if TYPE_CHECKING:
    from nameless import Nameless

__all__ = ["NamelessYesNoPrompt"]


class NamelessYesNoPrompt(discord.ui.View):
    """A simple Yes/No prompt."""

    def __init__(self, timeout: int = 15) -> None:
        super().__init__(timeout=timeout)
        self.is_a_yes: bool = False

    @discord.ui.button(label="Yep!", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction[Nameless], _btn: discord.ui.Button[Self]) -> None:
        self.is_a_yes = True
        await interaction.followup.send("Response received!")
        self.stop()

    @discord.ui.button(label="Nope!", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction[Nameless], _btn: discord.ui.Button[Self]) -> None:
        await interaction.followup.send("Response received!")
        self.stop()

    @override
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        await interaction.response.defer()
        return await super().interaction_check(interaction)
