import logging
import sys

import nextcord
from nextcord.ext import commands

import cogs
from config import Config
import customs

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('nextcord')
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(customs.ColoredFormatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'))
logger.propagate = False
logger.addHandler(handler)

# Bot setup
client = commands.AutoShardedBot(intents=nextcord.Intents.all(), command_prefix=Config.PREFIXES)


@client.event
async def on_ready():
    logger.info(msg=f"Logged in as {client.user} (ID: {client.user.id})")


@client.event
async def on_error(event_name: str, *args, **kwargs):
    logger.error(msg=f"[{event_name}] We have gone under a crisis!!!", *args, exc_info=True, extra={**kwargs})

# Please DO NOT add TestSlashCog, even if your mom told you so.
# client.add_cog(cogs.slash.TestSlashCog(client))
client.add_cog(cogs.slash.OwnerSlashCog(client))
client.add_cog(cogs.slash.MusicSlashCog(client))

client.run(Config.TOKEN)
