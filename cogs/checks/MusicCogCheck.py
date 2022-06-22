import wavelink
from discord.ext import commands

from .BaseCheck import BaseCheck

__all__ = ["MusicCogCheck"]


class MusicCogCheck(BaseCheck):
    @staticmethod
    @BaseCheck.allow_help_message
    def user_and_bot_in_voice(ctx: commands.Context):
        return MusicCogCheck.bot_in_voice(ctx) and MusicCogCheck.user_in_voice(ctx)

    @staticmethod
    @BaseCheck.allow_help_message
    def bot_must_play_track_not_stream(ctx: commands.Context):
        return MusicCogCheck.bot_must_play_something(
            ctx
        ) and MusicCogCheck.must_not_be_a_stream(ctx)

    @staticmethod
    @BaseCheck.allow_help_message
    def bot_in_voice(ctx: commands.Context):
        if not ctx.voice_client:
            raise commands.CheckFailure("I must be in a voice channel.")

        return True

    @staticmethod
    @BaseCheck.allow_help_message
    def user_in_voice(ctx: commands.Context):
        if not ctx.author.voice:  # pyright: ignore
            raise commands.CheckFailure("You must be in a voice channel.")

        return True

    @staticmethod
    @BaseCheck.allow_help_message
    def bot_must_silent(ctx: commands.Context):
        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        if vc and vc.is_playing():
            raise commands.CheckFailure("I must be silenced.")

        return True

    @staticmethod
    @BaseCheck.allow_help_message
    def bot_must_play_something(ctx: commands.Context):
        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        if vc and not vc.is_playing():
            raise commands.CheckFailure("I need to play something.")

        return True

    @staticmethod
    @BaseCheck.allow_help_message
    def must_not_be_a_stream(ctx: commands.Context):
        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        if vc and vc.track and vc.track.is_stream():  # pyright: ignore
            raise commands.CheckFailure("I can't use this command on streams.")

        return True

    @staticmethod
    @BaseCheck.allow_help_message
    def queue_has_element(ctx: commands.Context):
        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        if vc and vc.queue.is_empty:
            raise commands.CheckFailure("I need to have something in the queue.")

        return True
