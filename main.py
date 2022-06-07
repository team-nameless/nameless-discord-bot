import logging
import os
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import close_all_sessions
import discord
from discord.ext import commands

import global_deps
from config import Config


class Nameless(commands.AutoShardedBot):
    async def __register_all_cogs(self):
        r = re.compile(r"^(?!_.).*Cog.py")
        os.chdir(Path(__file__).resolve().parent)
        allowed_cogs = list(filter(r.match, os.listdir("cogs")))

        for cog_name in Config.COGS:
            can_load = False
            fail_reason = ""

            if cog_name + "Cog.py" in allowed_cogs:

                if cog_name == "Experimental":
                    if Config.LAB:
                        can_load = True
                    else:
                        fail_reason = "'Experimental' needs 'Config.LAB' set to True."

                elif cog_name == "Osu":
                    if (
                        Config.OSU
                        and Config.OSU["client_id"]
                        and Config.OSU["client_secret"]
                    ):
                        can_load = True
                    else:
                        fail_reason = (
                            "'Osu' needs 'Config.OSU' itself to be not 'None' "
                            "and its 'client_id' and 'client_secret' properties "
                            "set to a valid value."
                        )

                elif cog_name == "Music":
                    if Config.LAVALINK and Config.LAVALINK["nodes"]:
                        can_load = True
                    else:
                        fail_reason = (
                            "'Music' needs 'Config.Music' itself to be not 'None' "
                            "and its 'node' properties set to a valid value "
                            "'spotify' is optional."
                        )

                else:
                    can_load = True
            else:
                fail_reason = "It does not exist in 'allowed_cogs' list."

            if can_load:
                await self.load_extension(f"cogs.{cog_name}Cog")
            else:
                logging.error(f"Unable to load {cog_name}! Reason: {fail_reason}")

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

        logging.info(
            msg=f"Logged in as {self.user} (ID: {self.user.id})"  # pyright: ignore
        )

    async def on_error(self, event_method: str, /, *args, **kwargs) -> None:
        logging.error(
            msg=f"[{event_method}] We have gone under a crisis!!!",
            stack_info=True,
            exc_info=True,
            extra={**kwargs},
        )

    async def on_member_join(self, member: discord.Member):
        db_guild, _ = global_deps.crud_database.get_or_create_guild_record(member.guild)

        if db_guild.is_welcome_enabled:
            if db_guild.welcome_message != "":
                if the_channel := member.guild.get_channel_or_thread(
                    db_guild.welcome_channel_id
                ):
                    await the_channel.send(
                        content=db_guild.welcome_message.replace(
                            "{guild}", member.guild
                        )
                        .replace("{name}", member.display_name)
                        .replace("{tag}", member.discriminator)
                        .replace("{@user}", member.mention)
                    )

    async def on_member_remove(self, member: discord.Member):
        db_guild, _ = global_deps.crud_database.get_or_create_guild_record(member.guild)

        if db_guild.is_goodbye_enabled:
            if db_guild.goodbye_message != "":
                if the_channel := member.guild.get_channel_or_thread(
                    db_guild.goodbye_channel_id
                ):
                    await the_channel.send(
                        content=db_guild.goodbye_message.replace(
                            "{guild}", member.guild
                        )
                        .replace("{name}", member.display_name)
                        .replace("{tag}", member.discriminator)
                    )

    async def close(self) -> None:
        logging.warning(msg="Shutting down database")
        close_all_sessions()
        await super().close()


def main():
    global_deps.start_time = datetime.now()

    intents = discord.Intents.none()
    intents.guild_messages = True
    intents.members = True

    client = Nameless(intents=discord.Intents.all(), command_prefix=Config.PREFIXES)
    client.run(Config.TOKEN)


if __name__ == "__main__":
    main()
