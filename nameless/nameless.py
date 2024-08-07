import logging
import os
import re

import discord
from discord import Permissions
from discord.ext import commands
from sqlalchemy.orm import close_all_sessions

from NamelessConfig import NamelessConfig
import nameless.runtime_config as runtime_config

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

        runtime_config.is_debug = self.is_debug

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
                    runtime_config.loaded_modules.append(full_qualified_name)
                except commands.ExtensionError as ex:
                    fail_reason = str(ex)
            else:
                fail_reason = "It does not exist in `loadable` list."

            if fail_reason != "":
                logging.error("Unable to load %s! %s", cog_name, fail_reason, stack_info=False)
                runtime_config.rejected_modules.append(full_qualified_name)

        # Convert .py files to valid module names
        loaded_cog_modules = [f"nameless.commands.{cog.replace('.py', '')}Commands" for cog in cogs]
        allowed_cog_modules = [f"nameless.commands.{cog.replace('.py', '')}" for cog in allowed_cogs]

        # Get the commands that are not loaded at will (not specified in NamelessConfig
        excluded_cogs = list(set(set(allowed_cog_modules) - set(loaded_cog_modules)))
        runtime_config.rejected_modules.extend(excluded_cogs)

        # An extra set() to exclude dupes.
        runtime_config.loaded_modules = list(set(runtime_config.loaded_modules))
        runtime_config.rejected_modules = list(set(runtime_config.rejected_modules))

        logging.debug("Loaded modules: [ %s ]", ", ".join(runtime_config.loaded_modules))
        logging.debug("Excluded modules: [ %s ]", ", ".join(runtime_config.rejected_modules))

    async def setup_hook(self) -> None:
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

        try:
            logging.info("Trying to set custom activity.")
            await self.change_presence(
                status=status.STATUS,
                activity=discord.CustomActivity(
                    name=status.CUSTOM_ACTIVITY.CONTENT,
                    emoji=discord.PartialEmoji(name=status.CUSTOM_ACTIVITY.EMOJI),
                )
            )
        except TypeError:
            logging.error("Failed to set custom activity. Falling back to basic activity.")
            await self.change_presence(
                status=status.STATUS,
                activity=discord.Activity(
                    type=status.DISCORD_ACTIVITY.TYPE,
                    name=status.DISCORD_ACTIVITY.NAME,
                    url=status.DISCORD_ACTIVITY.URL
                ),
            )

        logging.info("Logged in as %s (ID: %s)", str(self.user), self.user.id)

    def start_bot(self) -> None:
        """Starts the bot."""
        logging.info(f"This bot will start in {'debug' if self.is_debug else 'production'} mode.")
        logging.info("Starting the bot...")
        self.run(NamelessConfig.TOKEN, log_handler=None)

    async def close(self) -> None:
        logging.warning("Shutting down...")
        close_all_sessions()
        await super().close()
