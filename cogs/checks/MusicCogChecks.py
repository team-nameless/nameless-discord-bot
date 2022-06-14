from discord.ext import commands
import wavelink


__all__ = ["MusicCogChecks"]


class MusicCogChecks:
    @staticmethod
    def bot_in_voice():
        async def predicate(ctx: commands.Context) -> bool:
            if not ctx.voice_client:
                raise commands.CommandError("I must be in a voice channel.")

            return True

        return commands.check(predicate)

    @staticmethod
    def user_in_voice():
        async def predicate(ctx: commands.Context) -> bool:
            if not ctx.author.voice:  # pyright: ignore
                raise commands.CommandError("You must be in a voice channel.")

            return True

        return commands.check(predicate)

    @staticmethod
    def bot_must_silent():
        async def predicate(ctx: commands.Context) -> bool:
            vc: wavelink.Player = ctx.voice_client  # pyright: ignore
            if vc.is_playing():
                raise commands.CommandError("I must be silenced.")

            return True

        return commands.check(predicate)

    @staticmethod
    def bot_must_play_something():
        async def predicate(ctx: commands.Context) -> bool:
            vc: wavelink.Player = ctx.voice_client  # pyright: ignore
            if not vc.is_playing():
                raise commands.CommandError("I need to play something.")

            return True

        return commands.check(predicate)

    @staticmethod
    def must_not_be_a_stream():
        async def predicate(ctx: commands.Context) -> bool:
            vc: wavelink.Player = ctx.voice_client  # pyright: ignore
            if vc.track.is_stream():  # pyright: ignore
                raise commands.CommandError("I can't use this command on streams.")

            return True

        return commands.check(predicate)

    @staticmethod
    def queue_has_element():
        async def predicate(ctx: commands.Context) -> bool:
            vc: wavelink.Player = ctx.voice_client  # pyright: ignore

            if vc.queue.is_empty:
                raise commands.CommandError("I need to have something in the queue.")

            return True

        return commands.check(predicate)
