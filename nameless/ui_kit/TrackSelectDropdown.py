from typing import Any, List, Optional, Union

import discord
import wavelink

from nameless.cogs.MusicV2Cog import YTDLSource

__all__ = ["TrackSelectDropdown"]

TrackT_ = Union[wavelink.Playable, YTDLSource]


class TrackSelectDropdown(discord.ui.Select):
    def __init__(self, tracks: List[TrackT_]):
        options = [
            discord.SelectOption(
                label="I don't see my results here",
                description="Nothing here!",
                value="Nope",
                emoji="❌",
            )
        ] + [
            discord.SelectOption(
                label=f"{track.author} - {track.title}"[:100],
                description=track.uri[:100] if track.uri else "No URI",
                value=str(index),
            )
            for index, track in enumerate(tracks[:25])
        ]

        super().__init__(
            custom_id="music-pick-select",
            placeholder="Choose your tracks",
            min_values=1,
            max_values=10,
            options=options,
        )

    async def callback(self, _: discord.Interaction) -> Any:
        v: Optional[discord.ui.View] = self.view
        if v:
            v.stop()
