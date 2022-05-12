import discord
from discord.ext import commands

import cogs
from globals import *

start_time = datetime.now()


class Nameless(commands.AutoShardedBot):
    async def __register_all_cogs(self):
        if Config.LAB:
            await client.add_cog(cogs.ExperimentalCog(client))

        await client.add_cog(cogs.OwnerCog(client))
        await client.add_cog(cogs.ActivityCog(client))
        await client.add_cog(cogs.ConfigCog(client))
        await client.add_cog(cogs.ModeratorCog(client))
        await client.add_cog(cogs.OsuCog(client))

        if Config.LAVALINK:
            await client.add_cog(cogs.MusicCog(client))

    async def on_shard_ready(self, shard_id: int):
        logging.info("Shard #{0} is ready".format(shard_id))

    async def on_ready(self):
        logging.info("Registering commands")
        await self.__register_all_cogs()

        if Config.GUILD_IDs:
            for _id in Config.GUILD_IDs:
                logging.info(f"Syncing commands with guild id {_id}")
                sf = discord.Object(_id)
                await client.tree.sync(guild=sf)
        else:
            logging.info(f"Syncing commands globally")
            await client.tree.sync()

        logging.info(msg="Setting presence")
        await client.change_presence(
            status=Config.STATUS["user_status"],
            activity=discord.Activity(
                type=Config.STATUS["type"]
                if Config.STATUS["type"]
                or (
                    Config.STATUS["type"] == discord.ActivityType.streaming
                    and Config.STATUS["url"]
                )
                else discord.ActivityType.playing,
                name=Config.STATUS["name"],
                url=Config.STATUS["url"] if Config.STATUS["url"] else None,
            ),
        )

        logging.info(msg=f"Logged in as {client.user} (ID: {client.user.id})")

    async def on_error(self, event_method: str, /, *args, **kwargs) -> None:
        logging.error(
            msg=f"[{event_method}] We have gone under a crisis!!!",
            stack_info=True,
            exc_info=True,
            extra={**kwargs},
        )

    async def on_member_join(self, member: discord.Member):
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

    async def on_member_remove(self, member: discord.Member):
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

    async def close(self) -> None:
        logging.warning(msg="Shutting down database")
        crud_database.close_all_sessions()
        await super().close()


intents = discord.Intents.none()
intents.guild_messages = True
intents.members = True

client = Nameless(intents=discord.Intents.all(), command_prefix=Config.PREFIXES)
client.run(Config.TOKEN)
