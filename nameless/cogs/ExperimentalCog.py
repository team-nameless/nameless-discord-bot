import logging

from discord.ext import commands

from NamelessConfig import NamelessConfig


__all__ = ["ExperimentalCog"]

import nameless


class ExperimentalCog(commands.Cog):
    pass


async def setup(bot: nameless.Nameless):
    if getattr(NamelessConfig, "LAB", False):
        await bot.add_cog(ExperimentalCog(bot))
        logging.info("Cog of %s added!", __name__)
    else:
        raise commands.ExtensionFailed(
            __name__,
            ValueError("ExperimentalCog requires NamelessConfig.LAB set to True"),
        )


async def teardown(bot: nameless.Nameless):
    await bot.remove_cog("ExperimentalCog")
    logging.warning("Cog of %s removed!", __name__)
