import discord
import wavelink

from . import NamelessDropdown

__all__ = ["NamelessTrackDropdown"]


class NamelessTrackDropdown(NamelessDropdown):
    def __init__(self, tracks: list[wavelink.Playable]):
        super().__init__()

        self.options = [
            discord.SelectOption(
                label="I don't see my results here", description="Nothing here!", value="Nope", emoji="❌"
            )
        ] + [
            discord.SelectOption(
                label=f"{track.author} - {track.title}"[:100],
                description=track.uri[:100] if track.uri else "No URI",
                value=str(index),
            )
            for index, track in enumerate(tracks[:25])
        ]

        self.custom_id = "music-pick-select"
        self.placeholder = "Choose your tracks"
        self.min_values = 1
        self.max_values = 10
