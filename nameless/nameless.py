import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Type

import discord
from discord.ext import commands
from discord.ext.commands import ExtensionFailed, errors
from packaging import version
from sqlalchemy.orm import close_all_sessions

from nameless import shared_vars
from nameless.commons import Utility
from nameless.database import CRUD
from nameless.shared_vars import stdout_handler

__all__ = ["Nameless"]

os.chdir(Path(__file__).resolve().parent)
logging.getLogger().handlers[:] = [shared_vars.stdout_handler]


class Nameless(commands.AutoShardedBot):
    def __init__(
        self,
        *args,
        command_prefix,
        config_cls: Optional[Type] = None,
        **kwargs,
    ):
        super().__init__(command_prefix, *args, **kwargs)

        self.config_cls = config_cls
        self.log_level: int = kwargs.get(
            "log_level",
            logging.DEBUG if getattr(self.config_cls, "LAB", False) else logging.INFO,
        )
        self.allow_updates_check: bool = kwargs.get("allow_updates_check", False)
        self.global_logger = logging.getLogger()

        self.loggers: List[logging.Logger] = [
            logging.getLogger(),
            logging.getLogger("sqlalchemy.engine"),
            logging.getLogger("sqlalchemy.dialects"),
            logging.getLogger("sqlalchemy.orm"),
            logging.getLogger("sqlalchemy.pool"),
            logging.getLogger("ossapi.ossapiv2"),
        ]
        self.description = getattr(self.config_cls, "BOT_DESCRIPTION", "")

    def check_for_updates(self):
        if not self.allow_updates_check:
            self.global_logger.warning(
                "Your bot might fall behind updates, consider setting allow_updates_check to True"
            )
        else:
            nameless_version = version.parse(shared_vars.__nameless_current_version__)
            upstream_version = version.parse(shared_vars.__nameless_upstream_version__)

            self.global_logger.info(
                "Current version: %s - Upstream version: %s",
                nameless_version,
                upstream_version,
            )

            if nameless_version < upstream_version:
                self.global_logger.warning("You need to update your code!")
            elif nameless_version == upstream_version:
                self.global_logger.info("You are using latest version!")
            else:
                self.global_logger.warning(
                    "You are using a version NEWER than original code!"
                )

        # Write current version in case I forgot
        with open("../version.txt", "w", encoding="utf-8") as f:
            logging.info("Writing current version into version.txt")
            f.write(shared_vars.__nameless_current_version__)

    async def __register_all_cogs(self):
        if cogs := getattr(self.config_cls, "COGS", []):
            allowed_cogs = list(
                filter(shared_vars.cogs_regex.match, os.listdir("cogs"))
            )

            for cog_name in cogs:
                fail_reason = ""

                if cog_name + "Cog.py" in allowed_cogs:
                    try:
                        await self.load_extension(f"nameless.cogs.{cog_name}Cog")
                    except ExtensionFailed as ex:
                        fail_reason = str(ex.original)

                    can_load = fail_reason == ""
                else:
                    can_load = False
                    fail_reason = "It does not exist in 'allowed_cogs' list."

                if not can_load:
                    logging.error("Unable to load %s! %s", cog_name, fail_reason)
        else:
            logging.warning(
                "config_cls.COGS is None or non-existence, nothing will be loaded (config_cls=%s)",
                self.config_cls.__name__,
            )

    async def on_shard_ready(self, shard_id: int):
        logging.info("Shard #%s is ready", shard_id)

    async def on_ready(self):
        logging.info("Registering commands")
        await self.__register_all_cogs()

        if ids := getattr(self.config_cls, "GUILD_IDs", []):
            for _id in ids:
                logging.info("Syncing commands with guild ID %d", _id)
                sf = discord.Object(_id)
                await self.tree.sync(guild=sf)
        else:
            logging.info("Syncing commands globally")
            await self.tree.sync()
            logging.warning(
                "Please wait at least one hour before using global commands"
            )

        if status := getattr(self.config_cls, "STATUS", {}):
            logging.info("Setting presence")

            await self.change_presence(
                status=status.get("user_status", discord.Status.online),
                activity=discord.Activity(
                    type=status.get("type", discord.ActivityType.playing),
                    name=status.get("name", "something"),
                    url=status.get("url", ""),
                ),
            )
        else:
            logging.warning(
                "Presence is not set since you did not provide values properly"
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
        if getattr(self.config_cls, "LAB", False):
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

            logger.setLevel(self.log_level)

            for handler in shared_vars.additional_handlers:
                logger.handlers.append(handler)

            if logger.parent:
                logger.parent.setLevel(self.log_level)
                logger.parent.handlers[:] = [stdout_handler]
                for handler in shared_vars.additional_handlers:
                    logger.parent.handlers.append(handler)
                logger.parent.propagate = False

    def start_bot(self):
        self.patch_loggers()
        self.check_for_updates()

        can_cont = Utility.is_valid_config_class(self.config_cls)

        if not isinstance(can_cont, bool):
            logging.warning(
                "This bot might run into errors because not all fields are presented"
            )
        else:
            if not can_cont:
                logging.error("Fields validation failed, the bot will exit")
                sys.exit()

        shared_vars.start_time = datetime.now()
        shared_vars.crud_database = CRUD(self.config_cls)
        self.run(getattr(self.config_cls, "TOKEN", ""), log_handler=None)
