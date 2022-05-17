import discord
from discord.ext import commands

import cogs
from global_deps import *

start_time = datetime.now()


class Nameless(commands.AutoShardedBot):
    async def __register_all_cogs(self):
        if Config.LAB:
            await self.load_extension(cogs.ExperimentalCog.__module__)
        else:
            logging.warning(
                "Experimental commands will not be available since you did not enable it"
            )

        await self.load_extension(cogs.OwnerCog.__module__)
        await self.load_extension(cogs.ActivityCog.__module__)
        await self.load_extension(cogs.ConfigCog.__module__)
        await self.load_extension(cogs.ModeratorCog.__module__)

        if Config.OSU and Config.OSU["client_id"] and Config.OSU["client_secret"]:
            await self.load_extension(cogs.OsuCog.__module__)
        else:
            logging.warning(
                "osu! commands will not be loaded since you did not provide enough credentials"
            )

        if Config.LAVALINK and Config.LAVALINK["nodes"]:
            await self.load_extension(cogs.MusicCog.__module__)
        else:
            logging.warning(
                "Music commands will not be loaded since you did not provide enough credentials"
            )

    async def on_shard_ready(self, shard_id: int):
        logging.info("Shard #{0} is ready".format(shard_id))

    async def on_ready(self):
        logging.info("Registering commands")
        await self.__register_all_cogs()

        if Config.GUILD_IDs:
            for _id in Config.GUILD_IDs:
                logging.info(f"Syncing commands with guild ID {_id}")
                sf = discord.Object(_id)
                await self.tree.sync(guild=sf)
        else:
            logging.info(f"Syncing commands globally")
            await self.tree.sync()

        logging.info(msg="Setting presence")
        await self.change_presence(
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
