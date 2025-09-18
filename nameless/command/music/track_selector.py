from __future__ import annotations

from typing import TYPE_CHECKING, Self

import discord.ui
from discord.ui import Button, Select, View

if TYPE_CHECKING:
    import pomice
    from discord.ext import commands

    from nameless.nameless import Nameless


class TrackSelector:
    @staticmethod
    async def select_tracks(ctx: commands.Context[Nameless], tracks: list[pomice.Track]) -> list[pomice.Track]:
        if len(tracks) == 1:
            return tracks

        if len(tracks) > 25:
            tracks = tracks[:25]

        view = TrackSelectionView(tracks)
        message = await ctx.send("🎵 **Multiple tracks found!** Please select the ones you want:", view=view)

        timeout = await view.wait()
        if timeout:
            await message.edit(content="⏰ Selection timed out! Please try again.", view=None)
            return []

        await message.delete()
        return view.selected_tracks


class TrackSelectionView(View):
    def __init__(self, tracks: list[pomice.Track]):
        super().__init__(timeout=60)
        self.tracks = tracks
        self.selected_tracks: list[pomice.Track] = []

        self.add_item(TrackDropdown(tracks))

    @discord.ui.button(label="Confirm Selection", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: Button[Self]):
        dropdown = self.children[0]
        if isinstance(dropdown, TrackDropdown) and dropdown.values:
            self.selected_tracks = [self.tracks[int(value)] for value in dropdown.values]

        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: Button[Self]):
        self.selected_tracks = []
        await interaction.response.defer()
        self.stop()


class TrackDropdown(Select[TrackSelectionView]):
    def __init__(self, tracks: list[pomice.Track]):
        options: list[discord.SelectOption] = []

        for i, track in enumerate(tracks[:25]):
            title = track.title or "Unknown Title"
            if len(title) > 50:
                title = title[:47] + "..."

            author = track.author or "Unknown Artist"
            if len(author) > 30:
                author = author[:27] + "..."

            description = f"by {author}"
            if track.length:
                duration_seconds = track.length // 1000
                minutes, seconds = divmod(duration_seconds, 60)
                description += f" • {minutes}:{seconds:02d}"

            options.append(discord.SelectOption(label=title, description=description, value=str(i), emoji="🎵"))

        super().__init__(
            placeholder="Select tracks to add...",
            min_values=1,
            max_values=min(len(options), 25),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if view and hasattr(view, "children"):
            for item in view.children:
                if isinstance(item, Button) and item.label == "Confirm Selection":
                    count = len(self.values)
                    item.label = f"Confirm Selection ({count})"
                    break

        await interaction.response.edit_message(view=view)
