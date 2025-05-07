import logging
import os
import sys

from discord.ext import commands

from nameless import Nameless

__all__ = ["OwnerCommand"]


class OwnerCommand(commands.Cog):
    """Commands for owners."""

    def __init__(self, bot: Nameless):
        pass

    @commands.hybrid_command()
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context[Nameless]):
        """Shutdown the bot."""
        await ctx.defer()
        await ctx.send("Bye owo!")

        await ctx.bot.close()

    @commands.hybrid_command()
    @commands.is_owner()
    async def restart(self, ctx: commands.Context[Nameless]):
        """Restart the bot."""
        await ctx.defer()
        await ctx.send("See you soon!")

        os.execl(sys.executable, sys.executable, *sys.argv)

    @commands.hybrid_command()
    @commands.is_owner()
    async def reload_commands(self, ctx: commands.Context[Nameless]):
        """Reload all loaded commands."""
        await ctx.defer()

        loaded_extensions = dict(ctx.bot.extensions).copy()

        for ext in loaded_extensions:
            await ctx.bot.reload_extension(ext)
            logging.info(f"Done reloading {ext}")

        await ctx.send("Done reloading all commands.")

    @commands.hybrid_command()
    @commands.is_owner()
    async def wipe_commands(self, ctx: commands.Context[Nameless]):
        """Wipe command list. Require a immediate restart."""
        await ctx.defer()

        for guild in ctx.bot.guilds:
            ctx.bot.tree.clear_commands(guild=guild)
            await ctx.bot.tree.sync(guild=guild)

        ctx.bot.tree.clear_commands(guild=None)
        await ctx.bot.tree.sync(guild=None)

        await ctx.send(
            "Command cleaning done, you should restart me to update the new commands."
        )


async def setup(bot: Nameless):
    await bot.add_cog(OwnerCommand(bot))
    logging.info("%s added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog(OwnerCommand.__cog_name__)
    logging.warning("%s removed!", __name__)
