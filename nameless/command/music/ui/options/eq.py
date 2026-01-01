from __future__ import annotations

from typing import TYPE_CHECKING, Self, final, override

import discord
from discord.ui import Select, View

from ..embeds import create_eq_preview_embed

if TYPE_CHECKING:
    from nameless.command.music.player import CustomPlayer


@final
class EQSettingsView(View):
    def __init__(self, player: CustomPlayer, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.player = player
        self.message: discord.Message | None = None
        self.add_item(EQBandSelect(player, self))

    async def update_embed(self, interaction: discord.Interaction) -> None:
        if not self.message:
            self.message = interaction.message

        embed = create_eq_preview_embed(self.player)
        await interaction.edit_original_response(embed=embed, view=self)

    @override
    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, Select):
                item.disabled = True


@final
class EQBandSelect(Select[EQSettingsView]):
    def __init__(self, player: CustomPlayer, parent_view: EQSettingsView):
        self.player = player
        self.parent_view = parent_view

        options = [
            discord.SelectOption(
                label=f"Band {i}",
                value=str(i),
                description=f"Current: {player.eq_bands.get(i, 0.0):+.2f}",
                emoji="🎚️",
            )
            for i in range(15)
        ]

        options.append(
            discord.SelectOption(
                label="Reset All Bands",
                value="reset",
                description="Clear all EQ adjustments",
                emoji="🔄",
            )
        )

        super().__init__(
            placeholder="Select a band to adjust...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="eq_band_select",
        )

    @override
    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]

        if selected == "reset":
            await interaction.response.defer(ephemeral=True)
            await self.player.reset_eq()
            await self.parent_view.update_embed(interaction)
            await interaction.followup.send("EQ reset to flat", ephemeral=True)
        else:
            band = int(selected)
            modal = EQBandInputModal(self.player, band, self.parent_view)
            await interaction.response.send_modal(modal)


@final
class EQBandInputModal(discord.ui.Modal):
    def __init__(self, player: CustomPlayer, band: int, parent_view: EQSettingsView):
        super().__init__(title=f"🎚️ EQ Band {band}")
        self.player = player
        self.band = band
        self.parent_view = parent_view

        current_gain = player.eq_bands.get(band, 0.0)

        self.gain_input = discord.ui.TextInput[Self](
            label=f"Gain for Band {band} (-0.25 to 1.0)",
            placeholder=f"Current: {current_gain:+.2f}",
            default=f"{current_gain:+.2f}",
            min_length=1,
            max_length=6,
            required=True,
        )
        self.add_item(self.gain_input)

    @override
    async def on_submit(self, interaction: discord.Interaction):
        try:
            gain = float(self.gain_input.value.strip())

            if not -0.25 <= gain <= 1.0:
                await interaction.response.send_message("Gain must be between -0.25 and 1.0", ephemeral=True)
                return

            await self.player.set_eq_band(self.band, gain)

            await interaction.response.defer(ephemeral=True)
            await self.parent_view.update_embed(interaction)

            await interaction.followup.send(f"✅ Band {self.band} set to {gain:+.2f}", ephemeral=True)

        except ValueError:
            await interaction.response.send_message("Please enter a valid number", ephemeral=True)
