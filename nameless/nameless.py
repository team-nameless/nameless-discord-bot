import asyncio
import logging
import os
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands
from discord.ext.commands import errors
from packaging import version
from sqlalchemy.orm import close_all_sessions

from nameless import shared_vars
from nameless.database import CRUD
from nameless.shared_vars import stdout_handler
from NamelessConfig import NamelessConfig


__all__ = ["Nameless"]

logging.getLogger().handlers[:] = [shared_vars.stdout_handler]


class Nameless(commands.AutoShardedBot):
    """Customized Discord sharded bot"""

    def __init__(
        self,
        *args,
        command_prefix,
        **kwargs,
    ):
        super().__init__(command_prefix, *args, **kwargs)

        self.log_level: int = kwargs.get(
            "log_level",
            logging.DEBUG if getattr(NamelessConfig, "DEV", False) else logging.INFO,
        )
        self.allow_updates_check: bool = kwargs.get("allow_updates_check", False)

        self.loggers: list[logging.Logger] = [
            logging.getLogger(),
            logging.getLogger("sqlalchemy.engine"),
            logging.getLogger("sqlalchemy.dialects"),
            logging.getLogger("sqlalchemy.orm"),
            logging.getLogger("sqlalchemy.pool"),
            logging.getLogger("ossapi.ossapiv2"),
        ]
        self.description = getattr(NamelessConfig, "BOT_DESCRIPTION", "")

    def check_for_updates(self):
        if not self.allow_updates_check:
            logging.warning("Your bot might fall behind updates, consider using flag '--allow-updates-check'")
        else:
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

    async def __register_all_cogs(self):
        # Sometimes os.cwd() is bad
        current_path = os.path.dirname(__file__)

        if cogs := getattr(NamelessConfig, "COGS", []):
            allowed_cogs = list(filter(shared_vars.cogs_regex.match, os.listdir(f"{current_path}{os.sep}cogs")))

            for cog_name in cogs:
                fail_reason = ""

                if cog_name + "Cog.py" in allowed_cogs:
                    try:
                        await self.load_extension(f"nameless.cogs.{cog_name}Cog")
                    except commands.ExtensionError as ex:
                        fail_reason = str(ex)

                    can_load = fail_reason == ""
                else:
                    can_load = False
                    fail_reason = "It does not exist in 'allowed_cogs' list."

                if not can_load:
                    logging.error("Unable to load %s! %s", cog_name, fail_reason)
        else:
            logging.warning("NamelessConfig.COGS is None or non-existence, nothing will be loaded.")

    async def on_shard_ready(self, shard_id: int):
        logging.info("Shard #%s is ready", shard_id)

    async def setup_hook(self) -> None:
        await self.construct_shared_vars()
        self.check_for_updates()

        logging.info("Registering commands")
        await self.__register_all_cogs()

        if ids := getattr(NamelessConfig, "GUILD_IDs", []):
            for _id in ids:
                logging.info("Syncing commands with guild ID %d", _id)
                sf = discord.Object(_id)
                await self.tree.sync(guild=sf)
        else:
            logging.info("Syncing commands globally")
            await self.tree.sync()
            logging.warning("Please wait at least one hour before using global commands")

    async def on_ready(self):
        if status := getattr(NamelessConfig, "STATUS", {}):
            logging.info("Setting presence")
            url = status.get("url", None)

            await self.change_presence(
                status=status.get("user_status", discord.Status.online),
                activity=discord.Activity(
                    type=status.get("type", discord.ActivityType.playing),
                    name=status.get("name", "something"),
                    url=url if url else None,
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

    async def on_member_join(self, member: discord.Member):
        db_guild = shared_vars.crud_database.get_or_create_guild_record(member.guild)

        if db_guild.is_welcome_enabled:
            if db_guild.welcome_message != "":
                if member.bot and not db_guild.is_bot_greeting_enabled:
                    return

                send_target = member.guild.get_channel_or_thread(db_guild.welcome_channel_id)

                if db_guild.is_dm_preferred:
                    send_target = member

                await self.send_greeter(db_guild.goodbye_message, member, send_target)

    async def on_member_remove(self, member: discord.Member):
        db_guild = shared_vars.crud_database.get_or_create_guild_record(member.guild)

        if db_guild.is_goodbye_enabled:
            if db_guild.goodbye_message != "":
                if member.bot and not db_guild.is_bot_greeting_enabled:
                    return

                send_target = member.guild.get_channel_or_thread(db_guild.goodbye_channel_id)

                # Should always be useless now because user is no longer in server
                # if db_guild.is_dm_preferred:
                #    send_target = member

                await self.send_greeter(db_guild.goodbye_message, member, send_target)

    async def send_greeter(self, content: str, member: discord.Member, send_target: discord.abc.Messageable):
        if send_target is not None and (
            isinstance(send_target, discord.TextChannel)
            or isinstance(send_target, discord.Thread)
            or isinstance(send_target, discord.Member)
        ):
            await send_target.send(
                content=content.replace("{guild}", member.guild.name)
                .replace("{name}", member.display_name)
                .replace("{tag}", member.discriminator)
            )

    async def on_command_error(self, ctx: commands.Context, err: errors.CommandError, /) -> None:
        print(err.args)

        if not isinstance(err, errors.CommandNotFound):
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

    async def is_owner(self, user: discord.User, /) -> bool:
        the_app = self.application
        assert the_app is not None

        if await super().is_owner(user):
            return True

        if the_app.team:
            if user in the_app.team.members:
                return True

        owner_list = getattr(NamelessConfig, "OWNERS", [])
        if user.id in owner_list:
            return True

        return False

    def patch_loggers(self) -> None:
        if getattr(NamelessConfig, "DEV", False):
            file_handler = logging.FileHandler(filename="nameless.log", mode="w", delay=True)
            file_handler.setFormatter(logging.Formatter("%(asctime)s - [%(levelname)s] [%(name)s] %(message)s"))
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

    @staticmethod
    async def construct_shared_vars():
        """
        Constructs variables to shared_vars.py.
        """
        logging.info("Populating nameless/shared_vars.py")

        shared_vars.start_time = datetime.now()
        shared_vars.crud_database = CRUD()

        meta = getattr(NamelessConfig, "META", {})

        # The default value is "", so an additional or might work
        shared_vars.__nameless_current_version__ = meta.get("version", None) or shared_vars.__nameless_current_version__
        shared_vars.upstream_version_txt_url = (
            meta.get("version_txt", None)
            or "https://raw.githubusercontent.com/nameless-on-discord/nameless/main/version.txt"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(shared_vars.upstream_version_txt_url, timeout=10) as response:
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
        logging.debug(shared_vars.upstream_version_txt_url)

    def start_bot(self):
        self.run(getattr(NamelessConfig, "TOKEN", ""), log_handler=None)
