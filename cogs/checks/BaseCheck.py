__all__ = ["BaseCheck"]

from discord.ext import commands


class BaseCheck:
    @staticmethod
    def is_from_help(ctx: commands.Context):
        return ctx.invoked_with and ctx.invoked_with == "help"
