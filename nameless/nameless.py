import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Self, override

import discord
from discord import ActivityType, Permissions
from discord.ext import commands

from nameless.config import nameless_config
from nameless.custom.cache import nameless_cache
from nameless.custom.prisma import NamelessPrisma

__all__ = ["Nameless"]


class Nameless(commands.Bot):
    """Customized Discord instance, or so called, nameless* bot."""

    def __init__(self, *args: object, **kwargs: object):
        # Downcasting because duck typed is a b*tch
        _description: str = nameless_config["nameless"]["description"]

        _intents: discord.Intents = discord.Intents.default()
        _intents.message_content = True
        _intents.members = True

        _prefixes: list[str] = nameless_config["command"]["prefixes"]
        _prefixes.append("nl.")
        _prefixes = [*set(_prefixes)]

        super().__init__(
            commands.when_mentioned_or(*_prefixes),
            *args,
            intents=_intents,
            description=_description,
            **kwargs,
        )
        nameless_config["nameless"]["is_shutting_down"] = False

    @override
    async def setup_hook(self):
        await NamelessPrisma.init()
        nameless_cache.populate_from_persistence()
        await self._register_commands()

        logging.info("Syncing commands.")
        await self.tree.sync()
        logging.warning("Text-based Commands should be available now.")
        logging.warning("Application Commands should be available in one hour.")

    async def on_ready(self):
        logging.info("Setting presence.")
        await self._change_presence()

        assert self.user is not None
        logging.info("Logged in as %s (ID: %s)", str(self.user), self.user.id)

        logging.info("nameless* is now operational!")
        nameless_config["nameless"]["start_time"] = datetime.now(UTC)

    @override
    async def on_command_error(
        self, ctx: commands.Context[Self], ex: commands.errors.CommandError
    ):
        await ctx.send(
            "Something went wrong during command execution, "
            + "please notify us on GitHub issue if needed."
        )
        logging.error("Something went wrong.", exc_info=ex)

    def start_bot(self, *, is_debug: bool = False):
        """Start the bot."""
        logging.info(
            f"This bot will now start in {'debug' if is_debug else 'production'} mode."
        )
        self.run(os.getenv("TOKEN", ""), log_handler=None)

    @override
    async def close(self):
        logging.warning("Shutting down...")
        nameless_config["nameless"]["is_shutting_down"] = True
        await NamelessPrisma.dispose()
        nameless_cache.yank_to_persitence()
        await super().close()

    @staticmethod
    def get_needed_permissions() -> Permissions:
        """Get minimum permissions needed for bare functionalities."""
        perms = Permissions.none()

        perms.view_channel = True
        perms.send_messages = True
        perms.send_messages_in_threads = True
        perms.embed_links = True
        perms.attach_files = True
        perms.use_external_emojis = True
        perms.use_external_stickers = True
        perms.connect = True
        perms.speak = True
        perms.use_voice_activation = True
        perms.manage_channels = True

        return perms

    async def _change_presence(self):
        """Set up nameless status."""
        await self.change_presence(
            status=discord.Status.do_not_disturb,
            activity=discord.Activity(type=ActivityType.watching, name="you"),
        )

    async def _register_commands(self):
        """Register all available commands."""
        logging.info("Registering commands.")

        # Add jishaku by default.
        await self.load_extension("jishaku")

        # We get ones that end in .py, in `command` directory.
        # And ignore ones that starts with _ (underscore)
        current_path = Path(__file__).parent
        py_file_re = re.compile(r"^(?!_.*)(\w.*).py")
        available_files = [
            *filter(py_file_re.match, os.listdir(current_path / "command"))
        ]

        for file in available_files:
            module_name = file.replace(".py", "")
            module_name = f"nameless.command.{module_name}"

            try:
                await self.load_extension(module_name)
            except commands.ExtensionFailed as ex:
                logging.error("Command load failure.", exc_info=ex)

    def get_prefix_list(self) -> list[str]:
        """Get prefix list."""
        assert self.user is not None

        _prefixes: list[str] = nameless_config["command"]["prefixes"]
        _prefixes.append("nl.")
        _prefixes.append(self.user.mention)
        _prefixes = [*set(_prefixes)]

        return _prefixes
