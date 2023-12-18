import discord
import wavelink
from discord.app_commands import CheckFailure

from nameless.cogs.checks import BaseCheck

__all__ = ["MusicCogCheck"]


class MusicCogCheck(BaseCheck):
    @staticmethod
    def must_not_be_a_stream(interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if vc and vc.current and vc.current.is_stream:
            raise CheckFailure("I can't use this command on streams.")

        return True

    @staticmethod
    def bot_must_play_track_not_stream(interaction: discord.Interaction):
        return MusicCogCheck.bot_is_playing_something(interaction) and MusicCogCheck.must_not_be_a_stream(interaction)

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
    def user_and_bot_in_voice(interaction: discord.Interaction):
        return MusicCogCheck.bot_in_voice(interaction) and MusicCogCheck.user_in_voice(interaction)

    @staticmethod
    def queue_has_element(interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if MusicCogCheck.user_and_bot_in_voice(interaction) and not bool(vc.queue):
            raise CheckFailure("I need to have something in the queue.")

        return True

    @staticmethod
    def bot_is_not_playing_something(interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if vc and vc.playing:
            raise CheckFailure("I must not be playing something (or paused while doing it).")

        return True

    @staticmethod
    def bot_is_silent(interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if vc and not vc.paused:
            raise CheckFailure("I must be silenced.")

        return True

    @staticmethod
    def bot_is_playing_something(interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if vc and not vc.playing:
            raise CheckFailure("I need to play something.")

        return True
