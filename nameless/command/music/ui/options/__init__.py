from __future__ import annotations

from typing import TYPE_CHECKING, final, override

import discord
from discord.ui import Select, View

from ..embeds import create_eq_preview_embed
from .eq import EQSettingsView
from .general import GeneralSettingsModal

__all__ = (
    "EQSettingsView",
    "GeneralSettingsModal",
    "PlayerOptionsMenuView",
)

if TYPE_CHECKING:
    from nameless.command.music.player import CustomPlayer


@final
class PlayerOptionsMenuView(View):
    def __init__(self, player: CustomPlayer, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.player = player
        self.add_item(PlayerOptionsSelect(player))

    @override
    async def on_timeout(self):
        """Disable all items when the view times out."""
        for item in self.children:
            if isinstance(item, Select):
                item.disabled = True


@final
class PlayerOptionsSelect(Select[PlayerOptionsMenuView]):
    def __init__(self, player: CustomPlayer):
        self.player = player

        autoplay_status = "ON" if player.is_autoplay_enabled else "OFF"
        autoplay_emoji = "✅" if player.is_autoplay_enabled else "❌"

        # up to 25 options
        options = [
            discord.SelectOption(
                label="General Settings",
                value="general",
                description="Adjust Volume and Speed",
                emoji="🎛️",
            ),
            discord.SelectOption(
                label=f"Toggle Autoplay ({autoplay_status})",
                value="autoplay",
                description=f"Currently {autoplay_status} - Click to toggle",
                emoji=autoplay_emoji,
            ),
            discord.SelectOption(
                label="EQ Settings",
                value="eq",
                description="Audio equalizer settings",
                emoji="🎚️",
            ),
        ]

        super().__init__(
            placeholder="Choose a setting to configure...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="player_options_select",
        )

    @override
    async def callback(self, interaction: discord.Interaction):
        """Handle dropdown selection."""
        selected = self.values[0]

        if selected == "general":
            modal = GeneralSettingsModal(self.player)
            await interaction.response.send_modal(modal)

        elif selected == "autoplay":
            await interaction.response.defer(ephemeral=True)

            self.player.toggle_autoplay()

            autoplay_status = "ON" if self.player.is_autoplay_enabled else "OFF"
            autoplay_emoji = "✅" if self.player.is_autoplay_enabled else "❌"

            self.options[1].label = f"Toggle Autoplay ({autoplay_status})"
            self.options[1].description = f"Currently {autoplay_status} - Click to toggle"
            self.options[1].emoji = autoplay_emoji

            status = "enabled" if self.player.is_autoplay_enabled else "disabled"
            await interaction.followup.send(f"🔄 Autoplay {status}", ephemeral=True)

            if interaction.message:
                await interaction.message.edit(view=self.view)
                await self.player.update_now_playing_embed(interaction.message, interaction.user)

        elif selected == "eq":
            embed = create_eq_preview_embed(self.player)
            view = EQSettingsView(self.player)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
