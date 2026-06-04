from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Self, final, override

import discord.ui
from discord.ui import Button, Select, View

if TYPE_CHECKING:
    from collections.abc import Sequence

    from discord.ext import commands

    from nameless.nameless import Nameless


class TrackLike(Protocol):
    @property
    def title(self) -> str: ...

    @property
    def author(self) -> str: ...

    @property
    def length(self) -> int | None: ...


class TrackSelector:
    @staticmethod
    async def select_tracks[TrackItem: TrackLike](
        ctx: commands.Context[Nameless],
        tracks: Sequence[TrackItem],
        *,
        title: str | None = None,
        timeout: float = 60,
        timeout_message: str | None = None,
    ) -> list[TrackItem]:
        tracks_list = list(tracks)
        if len(tracks_list) == 1:
            return tracks_list

        if len(tracks_list) > 25:
            tracks_list = tracks_list[:25]

        view: TrackSelectionView[TrackItem] = TrackSelectionView(tracks_list, ctx.author.id)
        message = await ctx.send(
            title or "**Multiple tracks found!** Please select the ones you want:",
            view=view,
        )

        timeout = await view.wait()
        if timeout:
            await message.edit(
                content=timeout_message or "Selection timed out! Please try again.",
                view=None,
            )
            return []

        await message.delete()
        return view.selected_tracks


@final
class TrackSelectionView[TrackItem: TrackLike](View):
    def __init__(self, tracks: list[TrackItem], user_id: int, *, timeout: float = 60) -> None:
        super().__init__(timeout=timeout)
        self.tracks = tracks
        self.selected_tracks: list[TrackItem] = []
        self.user_id = user_id

        self._dropdown: TrackDropdown[TrackItem] = TrackDropdown(tracks)
        self.add_item(self._dropdown)

    @discord.ui.button(label="Confirm Selection", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, _: Button[Self]) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ You cannot interact with this selection.", ephemeral=True)
            return

        await interaction.response.defer()

        if self._dropdown.values:
            self.selected_tracks = [self.tracks[int(value)] for value in self._dropdown.values]

        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, _: Button[Self]) -> None:
        self.selected_tracks = []
        await interaction.response.defer()
        self.stop()


class TrackDropdown[TrackItem: TrackLike](Select[TrackSelectionView[TrackItem]]):
    def __init__(self, tracks: list[TrackItem]) -> None:
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

    @override
    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if view and hasattr(view, "children") and self.values:
            for item in view.children:
                if isinstance(item, Button) and item.label == "Confirm Selection":
                    count = len(self.values)
                    item.label = f"Confirm Selection ({count})"
                    break

        await interaction.response.edit_message(view=view)
