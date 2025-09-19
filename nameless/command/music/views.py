from __future__ import annotations

from typing import TYPE_CHECKING, Self, final, override

import discord
from discord.ui import Button, View

if TYPE_CHECKING:
    from .player import CustomPlayer


@final
class MusicControlView(View):
    def __init__(self, player: CustomPlayer, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.player = player
        self.pause_resume_button = None

        self.update_buttons()

    def update_buttons(self):
        if self.pause_resume_button:
            self.pause_resume_button.emoji = "▶️" if self.player.is_paused else "⏸️"
            self.pause_resume_button.label = "Resume" if self.player.is_paused else "Pause"

        has_track = self.player.current is not None
        for item in self.children:
            if isinstance(item, Button) and item.custom_id not in ["disconnect", "queue"]:
                item.disabled = not has_track

    @discord.ui.button(label="Previous", emoji="⏮️", style=discord.ButtonStyle.secondary, custom_id="previous")
    async def previous(self, interaction: discord.Interaction, _: Button[Self]):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("⏮️ Previous track feature not implemented yet", ephemeral=True)

    @discord.ui.button(label="Pause", emoji="⏸️", style=discord.ButtonStyle.primary, custom_id="pause_resume")
    async def pause_resume(self, interaction: discord.Interaction, button: Button[Self]):
        await interaction.response.defer(ephemeral=True)

        if self.player.is_paused:
            await self.player.set_pause(False)
            await interaction.followup.send("▶️ Resumed playback", ephemeral=True)
        else:
            await self.player.set_pause(True)
            await interaction.followup.send("⏸️ Paused playback", ephemeral=True)

        self.pause_resume_button = button
        self.update_buttons()
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="Skip", emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="skip")
    async def skip(self, interaction: discord.Interaction, _: Button[Self]):
        await interaction.response.defer(ephemeral=True)
        await self.player.stop()
        await interaction.followup.send("⏭️ Skipped track", ephemeral=True)

    @discord.ui.button(label="Shuffle", emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="shuffle", row=1)
    async def shuffle(self, interaction: discord.Interaction, _: Button[Self]):
        await interaction.response.defer(ephemeral=True)

        if not self.player.queue:
            await interaction.followup.send("❌ Queue is empty", ephemeral=True)
            return

        self.player.queue.shuffle()
        await interaction.followup.send("🔀 Queue shuffled", ephemeral=True)

    @discord.ui.button(label="Queue", emoji="📋", style=discord.ButtonStyle.secondary, custom_id="queue", row=1)
    async def show_queue(self, interaction: discord.Interaction, _: Button[Self]):
        await interaction.response.defer(ephemeral=True)

        if not self.player.queue:
            await interaction.followup.send("📭 Queue is empty", ephemeral=True)
            return

        queue_text: list[str] = []
        queue_list = list(self.player.queue._queue[:10])  # type: ignore
        for i, track in enumerate(queue_list, 1):
            queue_text.append(f"{i}. {track.title}")

        if len(self.player.queue) > 10:
            queue_text.append(f"... and {len(self.player.queue) - 10} more tracks")

        embed = discord.Embed(title="📋 Queue", description="\n".join(queue_text), color=discord.Color.blue())

        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Disconnect", emoji="🔌", style=discord.ButtonStyle.danger, custom_id="disconnect", row=1)
    async def disconnect(self, interaction: discord.Interaction, _: Button[Self]):
        await interaction.response.defer(ephemeral=True)
        await self.player.disconnect()
        await interaction.followup.send("👋 Disconnected from voice channel", ephemeral=True)
        self.stop()

    @override
    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, Button):
                item.disabled = True


@final
class VolumeModal(discord.ui.Modal):
    def __init__(self, player: CustomPlayer):
        super().__init__(title="Set Volume")
        self.player = player

        self.volume_input = discord.ui.TextInput[MusicControlView](
            label="Volume (0-200)",
            placeholder="Enter volume level...",
            min_length=1,
            max_length=3,
        )

    @override
    async def on_submit(self, interaction: discord.Interaction):
        try:
            volume = int(self.volume_input.value)
            if not 0 <= volume <= 200:
                await interaction.response.send_message("❌ Volume must be between 0 and 200", ephemeral=True)
                return

            await self.player.set_volume(volume)
            await interaction.response.send_message(f"🔊 Volume set to {volume}%", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number", ephemeral=True)


@final
class ConfirmationView(View):
    def __init__(self, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.result = None

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, _: Button[Self]):
        self.result = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, _: Button[Self]):
        self.result = False
        await interaction.response.defer()
        self.stop()
