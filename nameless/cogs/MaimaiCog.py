
import logging

from discord import app_commands
from discord.ext import commands

from nameless import Nameless, shared_vars

__all__ = ["MaimaiCog"]

class MaimaiCog(commands.Cog):
    def __init__(self, bot: Nameless):
        self.bot = bot


async def setup(bot: Nameless):
    await bot.add_cog(MaimaiCog(bot))
    logging.info("%s cog added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog("MaimaiCog")
    logging.warning("%s cog removed!", __name__)
