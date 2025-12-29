from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, override

import discord

if TYPE_CHECKING:
    from nameless.command.music.player import CustomPlayer

    from . import PlayerOptionsMenuView


class PlayerOptionModal(discord.ui.Modal, ABC):
    def __init__(self, player: CustomPlayer, title: str, timeout: float = 180.0):
        super().__init__(title=title, timeout=timeout)
        self.player = player
        self.parent_view: PlayerOptionsMenuView | None = None

    @abstractmethod
    async def validate_inputs(self, interaction: discord.Interaction) -> tuple[bool, str | None]:
        """Validate user inputs before applying changes.

        Returns:
            (success, error_message): If success is False, error_message will be shown.
        """

    @abstractmethod
    async def apply_changes(self, interaction: discord.Interaction) -> str:
        """Apply validated changes to the player.

        Returns:
            success_message: A message to display after successful application.
        """

    @override
    async def on_submit(self, interaction: discord.Interaction):
        is_valid, error_message = await self.validate_inputs(interaction)
        if not is_valid:
            await interaction.response.send_message(f"❌ {error_message}", ephemeral=True)
            return

        try:
            success_message = await self.apply_changes(interaction)
            await interaction.response.send_message(success_message, ephemeral=True)

            if interaction.message:
                await self.player.update_now_playing_embed(interaction.message, interaction.user)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @override
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logging_message = f"Error in {self.__class__.__name__}: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ {logging_message}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {logging_message}", ephemeral=True)
