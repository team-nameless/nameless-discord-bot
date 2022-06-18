from typing import Callable
from discord.ext import commands

__all__ = ["BaseCheck"]


class BaseCheck:
    """Base check class. Containing some useful decorators."""

    def __init__(self):
        pass

    @staticmethod
    def allow_help_message(fn: Callable[[commands.Context], bool]):
        """
        Allow this command to be viewed in the help command.
        Commonly used for bypassing command-specific checks.
        Note: this is a decorator.
        """

        def pred(ctx: commands.Context) -> bool:
            return fn(ctx) or (
                ctx.invoked_with is not None and ctx.invoked_with == "help"
            )

        return pred
