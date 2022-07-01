import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List

import discord
from discord.ext import commands
from discord.ext.commands import ExtensionFailed, errors
from packaging import version
from sqlalchemy.orm import close_all_sessions

import customs
from customs.Utility import Utility
import shared_vars
from config import Config
from database.crud import CRUD

os.chdir(Path(__file__).resolve().parent)
log_level: int = (
    logging.DEBUG if hasattr(Config, "LAB") and Config.LAB else logging.INFO
)
logging.basicConfig(level=log_level)

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(customs.ColoredFormatter())
logging.getLogger().handlers[:] = [stdout_handler]


class Nameless(commands.AutoShardedBot):
    def __init__(self, command_prefix, **kwargs):
        self.log_level: int = (
            logging.DEBUG if hasattr(Config, "LAB") and Config.LAB else logging.INFO
        )

        self.loggers: List[logging.Logger] = [
            logging.getLogger(),
            logging.getLogger("sqlalchemy.engine"),
            logging.getLogger("sqlalchemy.dialects"),
            logging.getLogger("sqlalchemy.orm"),
            logging.getLogger("sqlalchemy.pool"),
            logging.getLogger("ossapi.ossapiv2"),
        ]

        super().__init__(command_prefix, **kwargs)

    def check_for_updates(self):
        nameless_version = version.parse(shared_vars.__nameless_current_version__)
        upstream_version = version.parse(shared_vars.__nameless_upstream_version__)

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
            logging.info("Writing current version into version.txt")
            f.write(shared_vars.__nameless_current_version__)

    async def __register_all_cogs(self):
        if hasattr(Config, "COGS"):
            allowed_cogs = list(
                filter(shared_vars.cogs_regex.match, os.listdir("cogs"))
            )

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
            ", ".join([str(a) for a in list(args)]),
            stack_info=True,
            exc_info=True,
            extra={**kwargs},
        )

    async def on_member_join(self, member: discord.Member):
        db_guild, _ = shared_vars.crud_database.get_or_create_guild_record(member.guild)

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
        db_guild, _ = shared_vars.crud_database.get_or_create_guild_record(member.guild)

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

    def patch_loggers(self) -> None:
        if hasattr(Config, "LAB") and Config.LAB:
            file_handler = logging.FileHandler(
                filename="nameless.log", mode="w", delay=True
            )
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - [%(levelname)s] [%(name)s] %(message)s"
                )
            )
            shared_vars.additional_handlers.append(file_handler)

        for logger in self.loggers:
            if logger.name != "root":
                logger.handlers[:] = [stdout_handler]
                logger.propagate = False

            logger.setLevel(log_level)

            for handler in shared_vars.additional_handlers:
                logger.handlers.append(handler)

            if logger.parent:
                logger.parent.setLevel(log_level)
                logger.parent.handlers[:] = [stdout_handler]
                for handler in shared_vars.additional_handlers:
                    logger.parent.handlers.append(handler)
                logger.parent.propagate = False

    def start_bot(self):
        self.patch_loggers()
        self.check_for_updates()
        shared_vars.start_time = datetime.now()
        shared_vars.crud_database = CRUD()
        self.run(Config.TOKEN, log_handler=None)


def main():
    can_cont = Utility.is_valid_config_class(Config)

    if not isinstance(can_cont, bool):
        logging.warning(
            "This bot might run into error because not all fields are presented"
        )
    else:
        if not can_cont:
            logging.error("Fields validation failed, the bot will exit")
            sys.exit()

    prefixes = Config.PREFIXES
    allow_mention = hasattr(Config, "RECEIVE_MENTION_PREFIX") and Config.RECEIVE_MENTION_PREFIX

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = (
        hasattr(Config, "RECEIVE_MESSAGE_COMMANDS") and Config.RECEIVE_MESSAGE_COMMANDS
    )

    nameless = Nameless(
        intents=intents,
        command_prefix=commands.when_mentioned_or(*prefixes)
        if allow_mention
        else prefixes,
        description="Just a bot",
    )
    nameless.start_bot()


if __name__ == "__main__":
    main()
