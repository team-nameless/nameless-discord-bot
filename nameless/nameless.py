import importlib
import logging
import os
import pkgutil
from datetime import UTC, datetime
from typing import Self, cast, final, override

import discord
from discord import ActivityType, Permissions
from discord.ext import commands

import nameless.command
from nameless.config import nameless_config
from nameless.custom.cache import nameless_cache
from nameless.custom.prisma import NamelessPrisma

__all__ = ["Nameless"]


class Nameless(commands.Bot):
    """Customized Discord instance, or so called, nameless* bot."""

    def __init__(self, *args: object, **kwargs: object):
        _intents: discord.Intents = discord.Intents.default()
        _intents.message_content = True
        _intents.members = True

        _prefixes: set[str] = nameless_config.command.prefixes
        _prefixes.add("nl.")

        super().__init__(
            commands.when_mentioned_or(*_prefixes),
            *args,
            intents=_intents,
            description=nameless_config.nameless.description,
            **kwargs,
        )
        nameless_config.runtime.is_shutting_down = False
        self._file_watcher = None

    @override
    async def setup_hook(self):
        await NamelessPrisma.init()
        nameless_cache.populate_from_persistence()
        await self._register_commands()
        # await self._setup_file_watcher()

        logging.info("Syncing commands.")
        if nameless_config.dev.enabled and nameless_config.dev.server_sync_ids:
            for guild_id in nameless_config.dev.server_sync_ids:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                logging.info(f"Synced commands to guild ID: {guild_id}")
        else:
            await self.tree.sync()
            logging.info("Synced commands globally.")
            logging.warning("Application Commands should be available in one hour.")

        logging.warning("Text-based Commands should be available now.")

    async def on_ready(self):
        logging.info("Setting presence.")
        await self._change_presence()

        assert self.user is not None
        logging.info("Logged in as %s (ID: %s)", str(self.user), self.user.id)

        logging.info("nameless* is now operational!")
        nameless_config.nameless.start_time = datetime.now(UTC)

    @override
    async def on_command_error(self, ctx: commands.Context[Self], ex: commands.errors.CommandError):  # type: ignore[reportIncompatibleMethodOverride]
        logging.error("Something went wrong.", exc_info=ex)
        await ctx.send(
            "Something went wrong during command execution, " + "please notify us on GitHub issue if needed."
        )

    def start_bot(self, *, is_debug: bool = False):
        """Start the bot."""
        logging.info(f"This bot will now start in {'debug' if is_debug else 'production'} mode.")
        self.run(os.getenv("TOKEN", ""), log_handler=None)

    @override
    async def close(self):
        logging.warning("Shutting down...")
        nameless_config.runtime.is_shutting_down = True

        if self._file_watcher:
            self._file_watcher.stop()
            self._file_watcher.join()

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

    async def _setup_file_watcher(self):
        if not nameless_config.dev.enabled:
            return

        try:
            import asyncio
            from pathlib import Path

            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer

            @final
            class ExtensionReloadHandler(FileSystemEventHandler):
                def __init__(self, bot: Nameless, command_path: Path):
                    self.bot = bot
                    self.command_path = command_path

                @override
                def on_modified(self, event):
                    if event.is_directory:
                        return

                    file_path = Path(cast(str, event.src_path))
                    if file_path.suffix != ".py":
                        return

                    # Check if the modified file is in the command package
                    try:
                        relative_path = file_path.relative_to(self.command_path)
                        module_parts = list(relative_path.parts[:-1]) + [relative_path.stem]
                        module_name = f"nameless.command.{'.'.join(module_parts)}"

                        # Check if this extension is loaded
                        if module_name in self.bot.extensions:
                            asyncio.create_task(self._reload_extension(module_name))

                    except ValueError:
                        # File is not in command package
                        pass

                async def _reload_extension(self, extension_name: str):
                    try:
                        await self.bot.reload_extension(extension_name)
                        logging.info(f"Auto-reloaded extension: {extension_name}")
                    except Exception as ex:
                        logging.error(f"Failed to auto-reload extension {extension_name}", exc_info=ex)

            self._file_watcher = Observer()
            command_dir = Path(nameless.command.__path__[0])
            event_handler = ExtensionReloadHandler(self, command_dir)

            # Watch the command directory
            self._file_watcher.schedule(event_handler, str(command_dir), recursive=True)
            self._file_watcher.start()

            logging.info("File watcher started for auto-reloading extensions")

        except ImportError:
            logging.warning("watchdog not installed, auto-reload disabled")
        except Exception as ex:
            logging.error("Failed to setup file watcher", exc_info=ex)

    async def _register_commands(self):
        """Register all available commands."""
        logging.info("Registering commands.")

        # Add jishaku by default.
        await self.load_extension("jishaku")

        ignore_list = nameless_config.command.ignores
        logging.info(f"Loaded ignore list: {ignore_list}")

        command_package = nameless.command
        for _, module_name, _ in pkgutil.iter_modules(command_package.__path__, command_package.__name__ + "."):
            name = module_name.split(".")[-1]
            if name.startswith("_") or name in ignore_list:
                continue

            try:
                module = importlib.import_module(module_name)
                if hasattr(module, "setup") and callable(module.setup):
                    await self.load_extension(module_name)
                    logging.info(f"Loaded extension: {module_name}")
                else:
                    logging.debug(f"Skipped {module_name}: no setup function found")
            except Exception as ex:
                logging.error(f"Failed to load extension {module_name}", exc_info=ex)
