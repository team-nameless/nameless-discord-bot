import logging
import sys

import nextcord
from nextcord.ext import commands

import cogs
from config import Config
import customs
import globals

# Logging setup
logging.basicConfig(level=logging.INFO)
log_nextcord = logging.getLogger("nextcord")
log_sql_engine = logging.getLogger("sqlalchemy.engine")
log_sql_pool = logging.getLogger("sqlalchemy.pool")
log_sql_pool.setLevel(logging.DEBUG)
log_sql_engine.setLevel(logging.DEBUG)
log_nextcord.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(customs.ColoredFormatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'))

log_nextcord.propagate = False
log_sql_engine.propagate = False
log_sql_pool.propagate = False
log_nextcord.addHandler(handler)
log_sql_engine.addHandler(handler)
log_sql_pool.addHandler(handler)

# Bot setup
client = commands.AutoShardedBot(intents=nextcord.Intents.all(), command_prefix=Config.PREFIXES)


@client.event
async def on_ready():
    globals.crud_database.init()
    log_nextcord.info(msg=f"Logged in as {client.user} (ID: {client.user.id})")


@client.event
async def on_error(event_name: str, *args, **kwargs):
    log_nextcord.error(msg=f"[{event_name}] We have gone under a crisis!!!", *args, exc_info=True, extra={**kwargs})


@client.event
async def close():
    log_sql_engine.warning(msg="Shutting down engine")
    log_sql_pool.warning(msg="Shutting down pool")
    globals.CRUD.close_all_sessions()

# Please DO NOT add TestSlashCog in code, even if your mom told you so.
# client.add_cog(cogs.slash.TestSlashCog(client))
client.add_cog(cogs.slash.OwnerSlashCog(client))
client.add_cog(cogs.slash.MusicSlashCog(client))
client.add_cog(cogs.slash.ActivitySlashCog(client))
client.add_cog(cogs.slash.ModeratorSlashCog(client))
client.run(Config.TOKEN)
