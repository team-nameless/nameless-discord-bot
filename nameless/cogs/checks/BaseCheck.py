from typing import Callable, List

from discord.ext import commands

__all__ = ["BaseCheck"]


class BaseCheck:
    """Base check class. Containing some useful decorators."""

    def __init__(self):
        pass

    @staticmethod
    def allow_help_message(check_fn: Callable[[commands.Context], bool]):
        """
        Bypasses command-specific checks.
        Note: this is a decorator for a check.
        """

        def pred(ctx: commands.Context) -> bool:
            return getattr(ctx, "invoked_with", "") == "help" or check_fn(ctx)

        return pred

    @staticmethod
    def require_intents(intents: List):
        """
        Require this command to have specific intent.
        Note: this is a decorator for a command.
        """

        async def pred(ctx: commands.Context, /, **kwargs) -> bool:
            set_intents = ctx.bot.intents

            for intent in intents:
                if (set_intents.value & intent.flag) != intent.flag:
                    return False

            return True

        return pred
