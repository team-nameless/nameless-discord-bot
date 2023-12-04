# Tool to generate cog

import sys

cog_name = sys.argv[1] + "Cog"

cog_template = f"""
import logging

from discord import app_commands
from discord.ext import commands

from nameless import Nameless, shared_vars

__all__ = ["{cog_name}"]

class {cog_name}(commands.Cog):
    def __init__(self, bot: Nameless):
        self.bot = bot


async def setup(bot: Nameless):
    await bot.add_cog({cog_name}(bot))
    logging.info("%s cog added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog("{cog_name}")
    logging.warning("%s cog removed!", __name__)
"""

with open("nameless/cogs/" + cog_name + ".py", "w") as f:
    f.write(cog_template)

print(f"Cog {cog_name} generated!")
