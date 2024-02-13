import argparse
import contextlib
import logging
import os
import sys
from pathlib import Path

import discord
from discord import InteractionResponded
from discord.app_commands import AppCommandError, errors
from discord.ext import commands
from filelock import FileLock, Timeout

from nameless import Nameless
from nameless.customs.NamelessCommandTree import NamelessCommandTree

import version
from NamelessConfig import NamelessConfig

# This is a dirty workarounds for inconsistencies between
# manual run and "PyCharm run"
cwd = Path(os.getcwd())
required_paths = [cwd/"nameless", cwd/"tests"]
for path in required_paths:
    if path not in sys.path:
        sys.path.append(str(path))

DEBUG_FLAG = "--debug"
VERSION_FLAG = "--version"

parser = argparse.ArgumentParser(prog="nameless*", description="A Discord bot written on python")

parser.add_argument(DEBUG_FLAG, action="store_true")
parser.add_argument(VERSION_FLAG, "-v", action="store_true")

args = parser.parse_args()

# If VERSION_FLAG is present, we print the version and update version file, then f- off.
if args.version:
    version.sanity_check()

logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] [%(name)s] %(message)s",
    stream=sys.stdout,
    level=logging.DEBUG if args.debug else logging.INFO
)

logging.getLogger().name = "nameless"

intents = discord.Intents.default()
intents.message_content = NamelessConfig.INTENT.MESSAGE
intents.members = NamelessConfig.INTENT.MEMBER

nameless = Nameless(
    intents=intents,
    tree_cls=NamelessCommandTree,
    is_debug=args.debug,
    description=NamelessConfig.__description__,
)


# Since there is no way to put this in nameless.Nameless, I put it here
# https://discord.com/channels/336642139381301249/1044652215228452965/1044652377082433616
# (from d.py official server)
@nameless.tree.error
async def on_app_command_error(interaction: discord.Interaction, err: AppCommandError):
    content = f"Something went wrong when executing the command:\n```\n{err}\n```"

    if not isinstance(err, errors.CommandSignatureMismatch):
        with contextlib.suppress(InteractionResponded):
            await interaction.response.defer()

        await interaction.followup.send(content)

        logging.exception("[on_command_error] We have gone under a crisis!!!", stack_info=True, exc_info=err)


# If you are encountering the error such as "column not found", this is for you
# Be aware that this will "erase" your tables as well
# from nameless.database import CRUD
# CRUD.in_case_of_getting_f_up()

lock = FileLock("nameless.lck", timeout=5)

try:
    logging.warning("Acquiring lock...")
    with lock.acquire():
        nameless.start_bot()
except Timeout as timeout:
    raise RuntimeError("Another 'nameless*' instance is running.") from timeout
finally:
    logging.warning("Releasing lock...")
    lock.release()
