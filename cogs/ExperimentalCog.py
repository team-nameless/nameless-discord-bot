import logging

from discord.ext import commands
from config import Config

__all__ = ["ExperimentalCog"]


class ExperimentalCog(commands.Cog):
    pass


async def setup(bot: commands.AutoShardedBot):
    if hasattr(Config, "LAB") and Config.LAB:
        await bot.add_cog(ExperimentalCog(bot))
        logging.info("Cog of %s added!", __name__)
    else:
        raise commands.ExtensionFailed(
            __name__, ValueError("ExperimentalCog requires Config.LAB set to True")
        )


async def teardown(bot: commands.AutoShardedBot):
    await bot.remove_cog("ExperimentalCog")
    logging.warning("Cog of %s removed!", __name__)
