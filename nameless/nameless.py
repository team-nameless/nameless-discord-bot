import asyncio
import logging
import os
import sys
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands
from discord.ext.commands import errors
from discord.message import Message
from packaging import version
from sqlalchemy.orm import close_all_sessions

from nameless import shared_vars
from nameless.database import CRUD
from NamelessConfig import NamelessConfig

__all__ = ["Nameless"]


class Nameless(commands.AutoShardedBot):
    """Customized Discord sharded bot"""

    def __init__(self, is_debug: bool = False, *args, **kwargs):
        super().__init__([], *args, **kwargs)

        self.log_level: int = logging.DEBUG if is_debug else logging.INFO
        self.is_debug = is_debug

        self.loggers: list[logging.Logger] = [
            logging.getLogger(),
            logging.getLogger("sqlalchemy.engine"),
            logging.getLogger("sqlalchemy.dialects"),
            logging.getLogger("sqlalchemy.orm"),
            logging.getLogger("sqlalchemy.pool"),
            logging.getLogger("ossapi.ossapiv2"),
            logging.getLogger("filelock"),
        ]

    def check_for_updates(self):
        nameless_version = version.parse(NamelessConfig.__version__)
        upstream_version = version.parse(shared_vars.__nameless_upstream_version__)

        logging.info("Current version: %s - Upstream version: %s", nameless_version, upstream_version)

        if nameless_version < upstream_version:
            logging.warning("You need to update your code!")
        elif nameless_version == upstream_version:
            logging.info("You are using latest version!")
        else:
            logging.warning("You are using a version NEWER than original code!")

    async def __register_all_cogs(self):
        # Sometimes os.cwd() is bad
        current_path = os.path.dirname(__file__)
        allowed_cogs = list(filter(shared_vars.cogs_regex.match, os.listdir(f"{current_path}{os.sep}cogs")))
        cogs = NamelessConfig.COGS

        for cog_name in cogs:
            fail_reason = ""
            full_qualified_name = f"nameless.cogs.{cog_name}Cog"

            if cog_name + "Cog.py" in allowed_cogs:
                try:
                    await self.load_extension(full_qualified_name)
                    shared_vars.loaded_cogs_list.append(full_qualified_name)
                except commands.ExtensionError as ex:
                    fail_reason = str(ex)
                    shared_vars.unloaded_cogs_list.append(full_qualified_name)

                can_load = fail_reason == ""
            else:
                can_load = False
                fail_reason = "It does not exist in 'allowed_cogs' list."

            if not can_load:
                logging.error("Unable to load %s! %s", cog_name, fail_reason, stack_info=False)
                shared_vars.unloaded_cogs_list.append(full_qualified_name)

        # Convert .py files to valid module names
        loaded_cog_modules = [f"nameless.cogs.{cog.replace('.py', '')}Cog" for cog in cogs]
        allowed_cog_modules = [f"nameless.cogs.{cog.replace('.py', '')}" for cog in allowed_cogs]
        excluded_cogs = list(set(set(allowed_cog_modules) - set(loaded_cog_modules)))
        shared_vars.unloaded_cogs_list.extend(excluded_cogs)

        # An extra set() to exclude cogs ignored by load failure.
        shared_vars.unloaded_cogs_list = list(set(shared_vars.unloaded_cogs_list))

        logging.debug("Loaded cog list: [ %s ]", ", ".join(shared_vars.loaded_cogs_list))
        logging.debug("Excluded cog list: [ %s ]", ", ".join(shared_vars.unloaded_cogs_list))

    async def on_shard_ready(self, shard_id: int):
        logging.info("Shard #%s is ready", shard_id)

    async def setup_hook(self) -> None:
        logging.info("Initiate database.")
        CRUD.init()

        logging.info("Constructing internal variables.")
        await self.construct_shared_vars()

        logging.info("Checking for upstream updates.")
        self.check_for_updates()

        if shared_vars.is_debug:
            logging.info("This bot is running in debug mode.")
        else:
            logging.warning("This bot is running in production mode.")

        logging.info("Registering commands")
        await self.__register_all_cogs()

        if ids := NamelessConfig.GUILDS:
            for _id in ids:
                logging.info("Syncing commands with guild ID %d", _id)
                sf = discord.Object(_id)
                self.tree.copy_global_to(guild=sf)
                await self.tree.sync(guild=sf)
        else:
            logging.info("Syncing commands globally")
            await self.tree.sync()
            logging.warning("Please wait at least one hour before using global commands")

    async def on_ready(self):
        if status := NamelessConfig.STATUS:
            logging.info("Setting presence")
            url = status.DISCORD_ACTIVITY.URL

            await self.change_presence(
                status=status.STATUS,
                activity=discord.Activity(
                    type=status.DISCORD_ACTIVITY.TYPE, name=status.DISCORD_ACTIVITY.NAME, url=url or None
                ),
            )
        else:
            logging.warning("Presence is not set since you did not provide values properly")

        assert self.user is not None
        logging.info("Logged in as %s (ID: %s)", str(self.user), self.user.id)

    async def on_error(self, event_method: str, /, *args, **kwargs) -> None:
        logging.error(
            "[%s] We have gone under a crisis!!! (args: [ %s ])",
            event_method,
            ", ".join([str(a) for a in list(args)]),
            stack_info=True,
            exc_info=True,
            extra={**kwargs},
        )

    async def on_command_error(self, ctx: commands.Context, err: errors.CommandError, /) -> None:
        if not isinstance(err, errors.CommandNotFound):
            await ctx.send(f"Something went wrong when executing the command:\n```\n{err}\n```")

            logging.exception("[on_command_error] We have gone under a crisis!!!", stack_info=True, exc_info=err)

    async def construct_shared_vars(self):
        """
        Constructs variables to shared_vars.py.
        """
        logging.info("Populating nameless/shared_vars.py")

        shared_vars.start_time = datetime.now()
        shared_vars.is_debug = self.is_debug
        # shared_vars.crud_database = CRUD()

        try:
            async with aiohttp.ClientSession() as session, session.get(
                NamelessConfig.META.UPSTREAM_VERSION_FILE, timeout=10
            ) as response:
                if 200 <= response.status <= 299:
                    shared_vars.__nameless_upstream_version__ = await response.text()
                else:
                    logging.warning("Upstream version fetching failed, using 0.0.0 as upstream version")
                    shared_vars.__nameless_upstream_version__ = "0.0.0"

        except asyncio.exceptions.TimeoutError:
            logging.error("Upstream version fetching error, using 0.0.0 as upstream version")
            logging.info("This is because your internet failed to fetch within 10 seconds timeout")
            shared_vars.__nameless_upstream_version__ = "0.0.0"

        # Debug data
        logging.debug("Bot start time: %s", shared_vars.start_time)

    async def on_message(self, message: Message):
        if not await self.is_blacklisted(message.author, message.guild):
            await super().on_message(message)

    async def is_blacklisted(self, user: discord.User | discord.Member, guild: discord.Guild | None) -> bool:
        # The owners, even if they are in the blacklist, can still use the bot
        if await self.is_owner(user):
            return False

        if guild.id in NamelessConfig.BLACKLISTS.GUILD_BLACKLIST:
            return True

        if user.id in NamelessConfig.BLACKLISTS.USER_BLACKLIST:
            return True

        return False

    def start_bot(self) -> None:
        """Starts the bot."""
        logging.info("Starting the bot...")

        self.run(NamelessConfig.TOKEN, log_handler=None)

    async def close(self) -> None:
        logging.warning("Shutting down...")
        close_all_sessions()
        await super().close()
