from typing import Any, Callable, Coroutine, List, Union

import discord
import wavelink
from discord.ext import commands
from wavelink.ext.spotify import SpotifyTrack


TrackT_ = Union[discord.AudioSource, wavelink.Playable, SpotifyTrack]
PlayerT_ = Union[discord.VoiceClient, wavelink.Player]


class BaseVoiceCog(commands.GroupCog, name="voice"):
    @staticmethod
    async def sync_async_runner(callback: Callable) -> Any:
        """Why wavelink. Why you make me do this..."""
        ret = callback()
        if isinstance(ret, Coroutine):
            return await ret

        return ret

    async def initialize(self, interaction: discord.Interaction, guild):
        raise NotImplementedError(f"{__class__.__name__}.initialize is not implemented")

    async def connect(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        await interaction.response.defer()
        await interaction.followup.send("`connect` is not define in this bot")

    async def leave(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        await interaction.response.defer()
        await interaction.followup.send("`leave` is not define in this bot")

    async def play(self, interaction: discord.Interaction, source: TrackT_, *args):
        """Start playing the queue."""
        await interaction.response.defer()

        vc: PlayerT_ = interaction.guild.voice_client  # pyright: ignore

        # When the user switch from radio -> normal queued track
        vc.queue.loop = False  # type: ignore
        setattr(vc, "should_send_play_now", True)

        await interaction.followup.send("The queue should be playing now.")
        await vc.play(vc.queue.get(), populate=vc.autoplay)  # pyright: ignore

    async def pause(self, interaction: discord.Interaction):
        """Pause current track"""
        await interaction.response.defer()

        vc: PlayerT_ = interaction.guild.voice_client  # type: ignore

        if vc.is_paused():
            await interaction.followup.send("Already paused")
            return

        ret = vc.pause()
        if isinstance(ret, Coroutine):
            await ret

        await interaction.followup.send("Paused")

    async def resume(self, interaction: discord.Interaction):
        """Resume current playback, if paused"""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if not vc.is_paused():
            await interaction.followup.send("Already resuming")
            return

        await vc.resume()
        await interaction.followup.send("Resumed")

    async def toggle_loop_track(self, interaction: discord.Interaction):
        """Toggle loop of current track."""
        await interaction.response.defer()

        vc: PlayerT_ = interaction.guild.voice_client  # type: ignore
        if not vc.queue:  # type: ignore
            return

        vc.queue.loop = not vc.queue.loop  # type: ignore
        setattr(vc, "should_send_play_now", not vc.queue.loop)  # type: ignore
        await interaction.followup.send(f"Track loop set to {'on' if vc.queue.loop else 'off'}")  # type: ignore

    async def toggle_loop_queue(self, interaction: discord.Interaction):
        """Toggle loop of current queue."""
        await interaction.response.defer()

        vc: PlayerT_ = interaction.guild.voice_client  # pyright: ignore

        if vc.queue.loop:  # type: ignore
            await interaction.followup.send("You must have track looping disabled before using this.")
            return

        vc.queue.loop_all = not vc.queue.loop_all  # type: ignore
        await interaction.followup.send(f"Queue loop set to {'on' if vc.queue.loop_all else 'off'}")  # type: ignore

    async def toggle_now_playing(self, interaction: discord.Interaction):
        """Toggle 'Now playing' message delivery on every non-looping track."""
        await interaction.response.defer()

        vc: PlayerT_ = interaction.guild.voice_client  # pyright: ignore
        setattr(vc, "play_now_allowed", not getattr(vc, "play_now_allowed"))

        await interaction.followup.send(f"'Now playing' is now {'on' if getattr(vc, 'play_now_allowed') else 'off'}")

    async def toggle_autoplay(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.followup.send("`toggle_autoplay` is not define in this bot")

    async def radio(self, interaction: discord.Interaction, source: str):
        await interaction.response.defer()
        await interaction.followup.send("`radio` is not define in this bot")

    async def skip(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.followup.send("`skip` is not define in this bot")

    async def seek_percent(self, interaction: discord.Interaction, percent: int):
        await interaction.response.defer()
        await interaction.followup.send("`seek_percent` is not define in this bot")

    async def seek(self, interaction: discord.Interaction, milisecond: int):
        await interaction.response.defer()
        await interaction.followup.send("`seek` is not define in this bot")

    async def now_playing(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.followup.send("`now_playing` is not define in this bot")

    async def queue_view(self, interaction: discord.Interaction):
        ...

    async def queue_view_autoplay(self, interaction: discord.Interaction):
        ...

    async def queue_add(self, interaction: discord.Interaction, source: TrackT_):
        ...

    async def queue_add_playlist(self, interaction: discord.Interaction, source: str):
        ...

    async def queue_delete(self, interaction: discord.Interaction, index: int):
        ...

    async def queue_move(self, interaction: discord.Interaction, _from: int, _to: int):
        ...

    async def queue_move_relative(self, interaction: discord.Interaction, _from: int, _difference: int):
        ...

    async def queue_swap(self, interaction: discord.Interaction, q: List, pos1: int, pos2: int):
        """Swap two tracks."""
        await interaction.response.defer()
        q_length = len(q)

        if not (1 <= pos1 <= q_length and 1 <= pos2 <= q_length):
            await interaction.followup.send(f"Invalid position(s): ({pos1}, {pos2})")
            return

        q[pos1 - 1], q[pos2 - 1] = q[pos2 - 1], q[pos1 - 1]
        await interaction.followup.send(f"Swapped track #{pos1} and #{pos2}")


class ExampleCog(BaseVoiceCog):
    def __init__(self) -> None:
        pass

    async def test_swap(self, interaction: discord.Interaction, pos1: int, pos2: int):
        return await super().queue_swap(interaction, [1, 2, 3], pos1, pos2)
