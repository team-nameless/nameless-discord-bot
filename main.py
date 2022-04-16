import nextcord
from nextcord.ext import commands

import cogs
from globals import *

client = commands.AutoShardedBot(intents=nextcord.Intents.all(), command_prefix=Config.PREFIXES)


@client.event
async def on_ready():
    postgres_database.init()
    logging.info(msg=f"Logged in as {client.user} (ID: {client.user.id})")


@client.event
async def on_error(event_name: str, *args, **kwargs):
    logging.error(msg=f"[{event_name}] We have gone under a crisis!!!", stack_info=True, exc_info=True,
                  extra={**kwargs, "args": args})


@client.event
async def close():
    logging.warning(msg="Shutting down engine")
    logging.warning(msg="Shutting down pool")
    PostgreSqlCRUD.close_all_sessions()


@client.event
async def on_member_join(member: nextcord.Member):
    db_guild, _ = postgres_database.get_or_create_guild_record(member.guild)

    if db_guild.is_welcome_enabled:
        if db_guild.welcome_message != "":
            if the_channel := member.guild.get_channel(db_guild.welcome_channel_id) is not None:
                await the_channel.send(content=db_guild.welcome_message
                                       .replace("{guild}", f"{member.guild=}")
                                       .replace("{name}", member.display_name)
                                       .replace("{tag}", member.discriminator)
                                       .replace("{@user}", member.mention))


@client.event
async def on_member_remove(member: nextcord.Member):
    db_guild, _ = postgres_database.get_or_create_guild_record(member.guild)

    if db_guild.is_goodbye_enabled:
        if db_guild.goodbye_message != "":
            if the_channel := member.guild.get_channel(db_guild.goodbye_channel_id) is not None:
                await the_channel.send(content=db_guild.goodbye_message
                                       .replace("{guild}", f"{member.guild=}")
                                       .replace("{name}", member.display_name)
                                       .replace("{tag}", member.discriminator))

if Config.LAB:
    client.add_cog(cogs.slash.ExperimentalSlashCog(client))
    client.add_cog(cogs.message.ExperimentalMessageCog(client))

client.add_cog(cogs.slash.OwnerSlashCog(client))
client.add_cog(cogs.slash.MusicSlashCog(client))
client.add_cog(cogs.slash.ActivitySlashCog(client))
client.add_cog(cogs.slash.ModeratorSlashCog(client))
client.add_cog(cogs.slash.ConfigSlashCog(client))
client.add_cog(cogs.slash.OsuSlashCog(client))
client.run(Config.TOKEN)
