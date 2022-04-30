import nextcord
from nextcord.ext import commands

import cogs
from globals import *

client = commands.AutoShardedBot(
    intents=nextcord.Intents.all(), command_prefix=Config.PREFIXES
)

crud_database.init()
start_time = datetime.now()


@client.event
async def on_ready():
    logging.info(msg="Setting presence")
    await client.change_presence(
        status=Config.STATUS["user_status"],
        activity=nextcord.Activity(
            type=Config.STATUS["type"],
            name=Config.STATUS["name"],
            url=Config.STATUS["url"] if Config.STATUS["url"] else None,
        ),
    )

    logging.info(msg=f"Logged in as {client.user} (ID: {client.user.id})")


@client.event
async def on_error(event_name: str, *args, **kwargs):
    logging.error(
        msg=f"[{event_name}] We have gone under a crisis!!!",
        stack_info=True,
        exc_info=True,
        extra={**kwargs},
    )


@client.event
async def close():
    logging.warning(msg="Shutting down engine")
    logging.warning(msg="Shutting down pool")
    CRUD.close_all_sessions()


@client.event
async def on_member_join(member: nextcord.Member):
    db_guild, _ = crud_database.get_or_create_guild_record(member.guild)

    if db_guild.is_welcome_enabled:
        if db_guild.welcome_message != "":
            if (
                the_channel := member.guild.get_channel(db_guild.welcome_channel_id)
                is not None
            ):
                await the_channel.send(
                    content=db_guild.welcome_message.replace(
                        "{guild}", f"{member.guild=}"
                    )
                    .replace("{name}", member.display_name)
                    .replace("{tag}", member.discriminator)
                    .replace("{@user}", member.mention)
                )


@client.event
async def on_member_remove(member: nextcord.Member):
    db_guild, _ = crud_database.get_or_create_guild_record(member.guild)

    if db_guild.is_goodbye_enabled:
        if db_guild.goodbye_message != "":
            if (
                the_channel := member.guild.get_channel(db_guild.goodbye_channel_id)
                is not None
            ):
                await the_channel.send(
                    content=db_guild.goodbye_message.replace(
                        "{guild}", f"{member.guild=}"
                    )
                    .replace("{name}", member.display_name)
                    .replace("{tag}", member.discriminator)
                )


if Config.LAB:
    client.add_cog(cogs.ExperimentalCog(client))

client.add_cog(cogs.OwnerCog(client))
client.add_cog(cogs.MusicCog(client))
client.add_cog(cogs.ActivityCog(client))
client.add_cog(cogs.ModeratorCog(client))
client.add_cog(cogs.ConfigCog(client))
client.add_cog(cogs.OsuCog(client))
client.run(Config.TOKEN)
