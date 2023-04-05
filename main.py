import logging
import sys

import discord
from discord.app_commands import AppCommandError, errors
from discord.ext import commands

import NamelessConfig
from nameless import Nameless


UPDATE_CHECK_FLAG = "--allow-updates-check"

cfg = NamelessConfig.NamelessConfig
args = sys.argv

prefixes = getattr(cfg, "PREFIXES", [])
allow_mention = getattr(cfg, "RECEIVE_MENTION_PREFIX", False)

intents = discord.Intents.default()
intents.message_content = getattr(cfg, "RECEIVE_TEXTS", False)
intents.members = getattr(cfg, "RECEIVE_MEMBER_EVENTS", False)

nameless = Nameless(
    intents=intents,
    command_prefix=commands.when_mentioned_or(*prefixes) if allow_mention else prefixes,
    allow_updates_check=UPDATE_CHECK_FLAG in args,
    description=getattr(cfg, "META", {}).get("bot_description", ""),
)


# Since there is no way to put this in nameless.Nameless, I put it here
# https://discord.com/channels/336642139381301249/1044652215228452965/1044652377082433616
# (from d.py official server)
@nameless.tree.error
async def on_app_command_error(interaction: discord.Interaction, err: AppCommandError):
    if not isinstance(err, errors.CommandSignatureMismatch):
        await interaction.followup.send(f"Something went wrong when executing the command:\n```\n{err}\n```")

    logging.exception(
        "[on_command_error] We have gone under a crisis!!!",
        stack_info=True,
        exc_info=err,
    )


# If you are encountering the error such as "column not found", this is for you
# Be aware that this will "erase" your tables as well
# from nameless.database import CRUD
# CRUD.in_case_of_getting_f_up()

nameless.patch_loggers()
nameless.start_bot()
