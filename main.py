import logging
import os
import re
from datetime import datetime
from pathlib import Path

import discord
import requests
from discord.ext import commands
from discord.ext.commands import errors, ExtensionFailed
from packaging import version
from sqlalchemy.orm import close_all_sessions

import global_deps
from config import Config

upstream_version_txt_url = (
    "https://raw.githubusercontent.com/nameless-on-discord/nameless/main/version.txt"
)
os.chdir(Path(__file__).resolve().parent)

class Nameless(commands.AutoShardedBot):
    def check_for_updates(self):
        nameless_version = version.parse(global_deps.__nameless_version__)
        upstream_version = version.parse(requests.get(upstream_version_txt_url).text)

        logging.info(
            "Current version: %s - Upstream version: %s",
            nameless_version,
            upstream_version,
        )

        if nameless_version < upstream_version:
            logging.warning("You need to update your code!")
        elif nameless_version == upstream_version:
            logging.info("You are using latest version!")
        else:
            logging.warning("You are using a version NEWER than original code!")

        # Write current version in case I forgot
        with open("version.txt", "w", encoding="utf-8") as f:
            f.write(global_deps.__nameless_version__)

    async def __register_all_cogs(self):
        if hasattr(Config, "COGS"):
            allowed_cogs = list(filter(global_deps.cogs_regex.match, os.listdir("cogs")))

            for cog_name in Config.COGS:
                fail_reason = ""

                if cog_name + "Cog.py" in allowed_cogs:
                    try:
                        await self.load_extension(f"cogs.{cog_name}Cog")
                    except ExtensionFailed as ex:
                        fail_reason = str(ex.original)

                    can_load = fail_reason == ""
                else:
                    can_load = False
                    fail_reason = "It does not exist in 'allowed_cogs' list."

                if not can_load:
                    logging.error("Unable to load %s! %s", cog_name, fail_reason)
        else:
            logging.warning("Config.COGS is None, nothing will be loaded")

    async def on_shard_ready(self, shard_id: int):
        logging.info("Shard #%s is ready", shard_id)

    async def on_ready(self):
        logging.info("Registering commands")
        await self.__register_all_cogs()

        if Config.GUILD_IDs:
            for _id in Config.GUILD_IDs:
                logging.info("Syncing commands with guild ID %d", _id)
                sf = discord.Object(_id)
                await self.tree.sync(guild=sf)
        else:
            logging.info("Syncing commands globally")
            await self.tree.sync()

        logging.info("Setting presence")
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

        logging.info("Logged in as %s (ID: %s)", str(self.user), self.user.id)

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        logging.error(
            "[%s] We have gone under a crisis!!! (args: [ %s ])",
            event_method,
            ", ".join(args),
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
                    await the_channel.send(  # pyright: ignore
                        content=db_guild.welcome_message.replace(
                            "{guild}", member.guild.name
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
                    await the_channel.send(  # pyright: ignore
                        content=db_guild.goodbye_message.replace(
                            "{guild}", member.guild.name
                        )
                        .replace("{name}", member.display_name)
                        .replace("{tag}", member.discriminator)
                    )

    async def on_command_error(
        self, ctx: commands.Context, err: errors.CommandError, /
    ) -> None:
        if not isinstance(err, errors.CommandNotFound):
            await ctx.defer()
            await ctx.send(f"Something went wrong when executing the command: {err}")

        logging.exception(
            "[on_command_error] We have gone under a crisis!!!",
            stack_info=True,
            exc_info=err,
        )

    async def close(self) -> None:
        logging.warning(msg="Shutting down...")
        close_all_sessions()
        await super().close()


def main():
    global_deps.start_time = datetime.now()

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = (
        hasattr(Config, "RECEIVE_MESSAGE_COMMANDS") and Config.RECEIVE_MESSAGE_COMMANDS
    )

    client = Nameless(
        intents=intents, command_prefix=Config.PREFIXES, description="Just a bot"
    )
    client.check_for_updates()
    client.run(Config.TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
