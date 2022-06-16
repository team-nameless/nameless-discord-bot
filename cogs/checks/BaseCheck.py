from discord.ext import commands

__all__ = ["BaseCheck"]


class BaseCheck:
    @staticmethod
    def is_from_help(ctx: commands.Context):
        return ctx.invoked_with and ctx.invoked_with == "help"
