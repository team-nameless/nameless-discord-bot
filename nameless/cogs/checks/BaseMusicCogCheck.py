from typing import Union

import discord
import wavelink
from discord.app_commands import CheckFailure

from .BaseCheck import BaseCheck


__all__ = ["BaseMusicCogCheck"]

VoiceClientT_ = Union[discord.VoiceClient, wavelink.Player]


class BaseMusicCogCheck(BaseCheck):
    @staticmethod
    def user_and_bot_in_voice(interaction: discord.Interaction):
        return __class__.bot_in_voice(interaction) and __class__.user_in_voice(interaction)

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
    def bot_is_not_playing_something(interaction: discord.Interaction):
        vc: VoiceClientT_ = interaction.guild.voice_client  # pyright: ignore

        if vc and vc.is_playing():
            raise CheckFailure("I must not be playing something (or paused while doing it).")

        return True

    @staticmethod
    def bot_is_silent(interaction: discord.Interaction):
        vc: VoiceClientT_ = interaction.guild.voice_client  # pyright: ignore

        if vc and not vc.is_paused():
            raise CheckFailure("I must be silenced.")

        return True

    @staticmethod
    def bot_is_playing_something(interaction: discord.Interaction):
        vc: VoiceClientT_ = interaction.guild.voice_client  # pyright: ignore
        if vc and not vc.is_playing():
            raise CheckFailure("I need to play something.")

        return True

    @staticmethod
    def must_not_be_a_stream(interaction: discord.Interaction):
        raise NotImplementedError

    @staticmethod
    def queue_has_element(interaction: discord.Interaction):
        raise NotImplementedError
