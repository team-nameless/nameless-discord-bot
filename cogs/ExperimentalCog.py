import logging

from discord.ext import commands

__all__ = ["ExperimentalCog"]


class ExperimentalCog(commands.Cog):
    pass


async def setup(bot: commands.AutoShardedBot):
    await bot.add_cog(ExperimentalCog(bot))
    logging.info(f"Cog of {__name__} added!")


async def teardown(bot: commands.AutoShardedBot):
    await bot.remove_cog("ExperimentalCog")
    logging.info(f"Cog of {__name__} removed!")
