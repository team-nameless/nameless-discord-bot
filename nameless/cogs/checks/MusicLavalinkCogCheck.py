import discord
import wavelink
from discord.app_commands import CheckFailure

from .BaseMusicCogCheck import BaseMusicCogCheck

__all__ = ["MusicLavalinkCogCheck"]


class MusicLavalinkCogCheck(BaseMusicCogCheck):
    @staticmethod
    def bot_must_play_track_not_stream(interaction: discord.Interaction):
        return __class__.bot_is_playing_something(interaction) and __class__.must_not_be_a_stream(interaction)

    @staticmethod
    def must_not_be_a_stream(interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if vc and vc.current and vc.current.is_stream:
            raise CheckFailure("I can't use this command on streams.")

        return True

    @staticmethod
    def queue_has_element(interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if vc and vc.queue.is_empty:
            raise CheckFailure("I need to have something in the queue.")

        return True
