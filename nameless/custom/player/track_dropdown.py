from typing import final

import discord
import wavelink

from nameless.custom.ui import NamelessDropdown

__all__ = ["TrackDropdown"]


@final
class TrackDropdown(NamelessDropdown):
    def __init__(self, tracks: list[wavelink.Playable]):
        super().__init__(
            custom_id="music-pick-select",
            placeholder="Choose your tracks",
            min_values=1,
            max_values=10,
        )

        self.options = [
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
