import discord
import wavelink
from discord.app_commands import CheckFailure

from nameless.commands.checks import BaseCheck
from nameless.database import CRUD

__all__ = ["MusicCommandChecks"]


class MusicCommandChecks(BaseCheck):
    @staticmethod
    def must_not_be_a_stream(interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore

        if vc and vc.current and vc.current.is_stream:
            raise CheckFailure("I can't use this command on streams.")

        return True

    @staticmethod
    def bot_must_play_track_not_stream(interaction: discord.Interaction):
        return MusicCommandChecks.bot_is_playing_something(interaction) and MusicCommandChecks.must_not_be_a_stream(
            interaction
        )

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
        return MusicCommandChecks.bot_in_voice(interaction) and MusicCommandChecks.user_in_voice(interaction)

    @staticmethod
    def queue_has_element(interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore

        if MusicCommandChecks.user_and_bot_in_voice(interaction) and not bool(vc.queue):
            raise CheckFailure("I need to have something in the queue.")

        return True

    @staticmethod
    def bot_is_not_playing_something(interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore

        if vc and vc.playing:
            raise CheckFailure("I must not be playing something (or paused while doing it).")

        return True

    @staticmethod
    def bot_is_silent(interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore

        if vc and not vc.paused:
            raise CheckFailure("I must be silenced.")

        return True

    @staticmethod
    def bot_is_playing_something(interaction: discord.Interaction):
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore

        if vc and not vc.playing:
            raise CheckFailure("I need to play something.")

        return True

    @staticmethod
    def has_audio_role(interaction: discord.Interaction):
        dbg = CRUD.get_or_create_guild_record(interaction.guild)
        role_id: int

        if dbg and dbg.audio_role_id:
            role_id = dbg.audio_role_id
        else:
            role_id = discord.utils.get(interaction.guild.roles, name="Audio").id  # type: ignore
            dbg.audio_role_id = role_id

        if not role_id:
            return True  # guild dont have audio role, just return True I guess

        if interaction.guild and role_id in interaction.user._roles:  # type: ignore
            raise CheckFailure("You must have an audio role to use this command.")

        return True
