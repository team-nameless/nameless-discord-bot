import logging
import sys

import discord
from discord import InteractionResponded
from discord.app_commands import AppCommandError, errors
from discord.ext import commands

from nameless import Nameless
from NamelessConfig import NamelessConfig

DEBUG_FLAG = "--debug"
UPDATE_CHECK_FLAG = "--allow-updates-check"

args = sys.argv[1:]

intents = discord.Intents.default()
intents.message_content = NamelessConfig.INTENT.MESSAGE
intents.members = NamelessConfig.INTENT.MEMBER

nameless = Nameless(
    intents=intents,
    is_debug=DEBUG_FLAG in args,
    command_prefix=commands.when_mentioned_or(*NamelessConfig.PREFIXES),
    allow_updates_check=UPDATE_CHECK_FLAG in args,
    description=NamelessConfig.__description__,
)


# Since there is no way to put this in nameless.Nameless, I put it here
# https://discord.com/channels/336642139381301249/1044652215228452965/1044652377082433616
# (from d.py official server)
@nameless.tree.error
async def on_app_command_error(interaction: discord.Interaction, err: AppCommandError):
    content = f"Something went wrong when executing the command:\n```\n{err}\n```"

    if not isinstance(err, errors.CommandSignatureMismatch):
        try:
            await interaction.response.defer()
        except InteractionResponded:
            pass

        await interaction.followup.send(content)

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
