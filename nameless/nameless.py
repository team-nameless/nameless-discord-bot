import logging
import os
import re
from datetime import datetime

import discord
from discord import Permissions
from discord.ext import commands
from discord.ext.commands import errors
from sqlalchemy.orm import close_all_sessions

from NamelessConfig import NamelessConfig

from .customs import shared_variables

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
            manage_channels=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True,
            use_external_emojis=True,
            use_external_stickers=True,
            add_reactions=True,
            connect=True,
            speak=True,
            use_voice_activation=True,
        )

    async def register_all_commands(self):
        """Registers all commands in the `commands` directory."""
        current_path = os.path.dirname(__file__)
        cog_regex = re.compile(r"^(?!_.).*Commands.py")
        allowed_cogs = list(filter(cog_regex.match, os.listdir(f"{current_path}{os.sep}commands")))
        cogs = NamelessConfig.COGS

        for cog_name in cogs:
            fail_reason = ""
            full_qualified_name = f"nameless.commands.{cog_name}Commands"

            if cog_name + "Commands.py" in allowed_cogs:
                try:
                    await self.load_extension(full_qualified_name)
                    shared_variables.loaded_modules.append(full_qualified_name)
                except commands.ExtensionError as ex:
                    fail_reason = str(ex)
            else:
                fail_reason = "It does not exist in `loadable` list."

            if fail_reason != "":
                logging.error("Unable to load %s! %s", cog_name, fail_reason, stack_info=False)
                shared_variables.rejected_modules.append(full_qualified_name)

        # Convert .py files to valid module names
        loaded_cog_modules = [f"nameless.commands.{cog.replace('.py', '')}Commands" for cog in cogs]
        allowed_cog_modules = [f"nameless.commands.{cog.replace('.py', '')}" for cog in allowed_cogs]

        # Get the commands that are not loaded at will (not specified in NamelessConfig
        excluded_cogs = list(set(set(allowed_cog_modules) - set(loaded_cog_modules)))
        shared_variables.rejected_modules.extend(excluded_cogs)

        # An extra set() to exclude dupes.
        shared_variables.loaded_modules = list(set(shared_variables.loaded_modules))
        shared_variables.rejected_modules = list(set(shared_variables.rejected_modules))

        logging.debug("Loaded modules: [ %s ]", ", ".join(shared_variables.loaded_modules))
        logging.debug("Excluded modules: [ %s ]", ", ".join(shared_variables.rejected_modules))

    async def on_shard_ready(self, shard_id: int):
        logging.info("Shard #%s is ready", shard_id)

    async def setup_hook(self) -> None:
        logging.info("Constructing internal variables.")
        await self.construct_internals()

        logging.info("Initiating database.")
        from .database import CRUD

        CRUD.init()

        logging.info("Registering commands")
        await self.register_all_commands()

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

    async def on_ready(self):
        logging.info("Setting presence")
        status = NamelessConfig.STATUS

        await self.change_presence(
            status=status.STATUS,
            activity=discord.Activity(
                type=status.DISCORD_ACTIVITY.TYPE, name=status.DISCORD_ACTIVITY.NAME, url=status.DISCORD_ACTIVITY.URL
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

        shared_variables.nameless_debug_mode = self.is_debug
        shared_variables.nameless_start_time = datetime.utcnow()

    async def is_blacklisted(
        self, *, user: discord.User | discord.Member | None = None, guild: discord.Guild | None = None
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
