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
    globals.postgres_database.init()
    log_nextcord.info(msg=f"Logged in as {client.user} (ID: {client.user.id})")


@client.event
async def on_error(event_name: str, *args, **kwargs):
    log_nextcord.error(msg=f"[{event_name}] We have gone under a crisis!!!", *args, exc_info=True, extra={**kwargs})


@client.event
async def close():
    log_sql_engine.warning(msg="Shutting down engine")
    log_sql_pool.warning(msg="Shutting down pool")
    globals.PostgreSqlCRUD.close_all_sessions()


@client.event
async def on_member_join(member: nextcord.Member):
    db_guild, _ = globals.postgres_database.get_or_create_guild_record(member.guild)

    if db_guild.is_welcome_enabled:
        if db_guild.welcome_message != "":
            if the_channel := member.guild.get_channel(db_guild.welcome_channel_id) is not None:
                await the_channel.send(content=db_guild.welcome_message)


@client.event
async def on_member_remove(member: nextcord.Member):
    db_guild, _ = globals.postgres_database.get_or_create_guild_record(member.guild)

    if db_guild.is_goodbye_enabled:
        if db_guild.goodbye_message != "":
            if the_channel := member.guild.get_channel(db_guild.goodbye_channel_id) is not None:
                await the_channel.send(content=db_guild.goodbye_message)


client.add_cog(cogs.slash.OwnerSlashCog(client))
client.add_cog(cogs.slash.MusicSlashCog(client))
client.add_cog(cogs.slash.ActivitySlashCog(client))
client.add_cog(cogs.slash.ModeratorSlashCog(client))
client.run(Config.TOKEN)
