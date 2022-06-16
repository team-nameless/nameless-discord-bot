import wavelink
from discord.ext import commands

from .BaseCheck import *

__all__ = ["MusicCogCheck"]

class MusicCogCheck(BaseCheck):
    @staticmethod
    def bot_in_voice(ctx: commands.Context):
        if MusicCogCheck.is_from_help(ctx):
            return True

        if not ctx.voice_client:
            raise commands.CommandError("I must be in a voice channel.")

        return True

    @staticmethod
    def user_in_voice(ctx: commands.Context):
        if MusicCogCheck.is_from_help(ctx):
            return True

        if not ctx.author.voice:  # pyright: ignore
            raise commands.CommandError("You must be in a voice channel.")

        return True

    @staticmethod
    def bot_must_silent(ctx: commands.Context):
        if MusicCogCheck.is_from_help(ctx):
            return True

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        if vc.is_playing():
            raise commands.CommandError("I must be silenced.")

        return True

    @staticmethod
    def bot_must_play_something(ctx: commands.Context):
        if MusicCogCheck.is_from_help(ctx):
            return True

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        if not vc.is_playing():
            raise commands.CommandError("I need to play something.")

        return True

    @staticmethod
    def must_not_be_a_stream(ctx: commands.Context):
        if MusicCogCheck.is_from_help(ctx):
            return True

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        if vc.track.is_stream():
            raise commands.CommandError("I can't use this command on streams.")

        return True

    @staticmethod
    def queue_has_element(ctx: commands.Context):
        if MusicCogCheck.is_from_help(ctx):
            return True

        vc: wavelink.Player= ctx.voice_client  # pyright: ignore

        if vc.queue.is_empty:
            raise commands.CommandError("I need to have something in the queue.")

        return True
