import discord
import wavelink
from discord.app_commands import CheckFailure

from .BaseCheck import BaseCheck


__all__ = ["MusicLavalinkCogCheck"]


class MusicLavalinkCogCheck(BaseCheck):
    @staticmethod
    def user_and_bot_in_voice(interaction: discord.Interaction):
        return MusicLavalinkCogCheck.bot_in_voice(interaction) and MusicLavalinkCogCheck.user_in_voice(interaction)

    @staticmethod
    def bot_must_play_track_not_stream(interaction: discord.Interaction):
        return MusicLavalinkCogCheck.bot_must_play_something(
            interaction
        ) and MusicLavalinkCogCheck.must_not_be_a_stream(interaction)

    @staticmethod
    def bot_in_voice(interaction: discord.Interaction):
        if interaction.guild and interaction.guild.voice_client is None:
            raise CheckFailure("I must be in a voice channel.")

        return True

    @staticmethod
    def user_in_voice(interaction: discord.Interaction):
        if isinstance(interaction.user, discord.Member) and interaction.user.voice is None:
            raise CheckFailure("You must be in a voice channel.")

        return True

    @staticmethod
    def bot_is_silent(interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if vc and vc.is_playing():
            raise CheckFailure("I must be silenced.")

        return True

    @staticmethod
    def bot_must_play_something(interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore
        if vc and not vc.is_playing():
            raise CheckFailure("I need to play something.")

        return True

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
