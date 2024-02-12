import asyncio
import logging
import os
import re
import json
from datetime import datetime

import aiohttp
import discord
from discord import Permissions
from discord.ext import commands
from discord.ext.commands import errors
from discord.message import Message
from filelock import FileLock
from packaging import version
from sqlalchemy.orm import close_all_sessions

from .database import CRUD
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

        self.needed_permissions: Permissions = Permissions(
            view_channel=True,
            send_messages=True,
            send_messages_in_threads=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True,
            use_external_emojis=True,
            use_external_stickers=True,
            add_reactions=True,
            connect=True,
            speak=True,
            use_voice_activation=True
        )

        self.internals = {
            "debug": False,
            "start_time": 0,
            "modules": {
                "loaded": [],
                "not_loaded": []
            }
        }

    async def check_for_updates(self) -> bool | None:
        """
        Performs an update check.

        Returns True if at the latest version, False if falling behind.
        And None if your version is newer than the latest.
        """
        __nameless_upstream_version__ = f"{NamelessConfig.__version__}-offline"

        try:
            async with aiohttp.ClientSession() as session, session.get(
                    NamelessConfig.META.UPSTREAM_VERSION_FILE, timeout=10
            ) as response:
                if 200 <= response.status <= 299:
                    __nameless_upstream_version__ = await response.text()
                else:
                    logging.warning("Upstream version fetching failed.")
        except asyncio.exceptions.TimeoutError:
            logging.error("Upstream version failed to fetch within 10 seconds.")

        nameless_version = version.parse(NamelessConfig.__version__)
        upstream_version = version.parse(__nameless_upstream_version__)

        logging.info("Current version: %s - Upstream version: %s", nameless_version, upstream_version)

        if nameless_version < upstream_version:
            logging.warning("You need to update your code!")
            return False
        elif nameless_version == upstream_version:
            logging.info("You are using latest version!")
            return True

        logging.warning("You are using a version NEWER than original code!")
        return None

    async def register_all_cogs(self):
        """Registers all cogs in the `cogs` directory."""
        current_path = os.path.dirname(__file__)
        cog_regex = re.compile(r"^(?!_.).*Cog.py")
        allowed_cogs = list(filter(cog_regex.match, os.listdir(f"{current_path}{os.sep}cogs")))
        cogs = NamelessConfig.COGS

        for cog_name in cogs:
            fail_reason = ""
            full_qualified_name = f"nameless.cogs.{cog_name}Cog"

            if cog_name + "Cog.py" in allowed_cogs:
                try:
                    await self.load_extension(full_qualified_name)
                    self.internals["modules"]["loaded"].append(full_qualified_name)
                except commands.ExtensionError as ex:
                    fail_reason = str(ex)
            else:
                fail_reason = "It does not exist in 'allowed_cogs' list."

            if not (fail_reason == ""):
                logging.error("Unable to load %s! %s", cog_name, fail_reason, stack_info=False)
                self.internals["modules"]["not_loaded"].append(full_qualified_name)

        # Convert .py files to valid module names
        loaded_cog_modules = [f"nameless.cogs.{cog.replace('.py', '')}Cog" for cog in cogs]
        allowed_cog_modules = [f"nameless.cogs.{cog.replace('.py', '')}" for cog in allowed_cogs]

        # Get the cogs that are not loaded at will (not specified in NamelessConfig
        excluded_cogs = list(set(set(allowed_cog_modules) - set(loaded_cog_modules)))
        self.internals["modules"]["not_loaded"].extend(excluded_cogs)

        # An extra set() to exclude dupes.
        self.internals["modules"]["loaded"] = list(set(self.internals["modules"]["loaded"]))
        self.internals["modules"]["not_loaded"] = list(set(self.internals["modules"]["not_loaded"]))

        logging.debug("Loaded cog list: [ %s ]", ", ".join(self.internals["modules"]["loaded"]))
        logging.debug("Excluded cog list: [ %s ]", ", ".join(self.internals["modules"]["not_loaded"]))

    async def on_shard_ready(self, shard_id: int):
        logging.info("Shard #%s is ready", shard_id)

    async def setup_hook(self) -> None:
        logging.info("Initiating database.")
        CRUD.init()

        logging.info("Constructing internal variables.")
        await self.construct_internals()

        logging.info("Checking for upstream updates.")
        await self.check_for_updates()

        logging.info("Registering commands")
        await self.register_all_cogs()

        logging.info("Syncing commands")
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

        with (
            FileLock("internals.json.lck"), \
                open(f"{os.path.dirname(__file__)}{os.sep}internals.json", "w") as internals_file
        ):
            json.dump(self.internals, internals_file)

    async def on_ready(self):
        logging.info("Setting presence")
        status = NamelessConfig.STATUS

        await self.change_presence(
            status=status.STATUS,
            activity=discord.Activity(
                type=status.DISCORD_ACTIVITY.TYPE,
                name=status.DISCORD_ACTIVITY.NAME,
                url=status.DISCORD_ACTIVITY.URL
            ),
        )

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

    async def construct_internals(self):
        """
        Constructs internal variables to internals.json
        """
        logging.info("Populating internals.json")

        self.internals["debug"] = self.is_debug
        self.internals["start_time"] = int(datetime.utcnow().timestamp())

    async def is_blacklisted(self, *,
                             user: discord.User | discord.Member = None,
                             guild: discord.Guild | None = None
                             ) -> bool:
        """Check if an entity is blacklisted from using the bot."""
        # The owners, even if they are in the blacklist, can still use the bot
        if user and await self.is_owner(user):
            return False

        if guild and guild.id in NamelessConfig.BLACKLISTS.GUILD_BLACKLIST:
            return True

        if user and user.id in NamelessConfig.BLACKLISTS.USER_BLACKLIST:
            return True

        return False

    def start_bot(self) -> None:
        """Starts the bot."""
        logging.info(f"This bot will start in {'debug' if self.is_debug else 'production'} mode.")
        logging.info("Starting the bot...")
        self.run(NamelessConfig.TOKEN, log_handler=None)

    async def close(self) -> None:
        logging.warning("Shutting down...")
        close_all_sessions()
        await super().close()
