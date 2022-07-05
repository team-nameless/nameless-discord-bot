from typing import Callable

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
        Note: this is a decorator.
        """

        def pred(ctx: commands.Context, /, **kwargs) -> bool:
            return (
                ctx.invoked_with == "help"
                if ctx.invoked_with is not None
                else check_fn(ctx)
            )

        return pred
