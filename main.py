import argparse
import contextlib
import logging
import sys

import discord
from discord import InteractionResponded
from discord.app_commands import AppCommandError, errors
from filelock import FileLock, Timeout

from nameless import Nameless
from nameless.customs.NamelessCommandTree import NamelessCommandTree
from NamelessConfig import NamelessConfig

DEBUG_FLAG = "--debug"
VERSION_FLAG = "--version"

parser = argparse.ArgumentParser(prog="nameless*", description="A Discord bot written on python")

parser.add_argument(DEBUG_FLAG, action="store_true")
parser.add_argument(VERSION_FLAG, "-v", action="store_true")

args = parser.parse_args()

logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] [%(name)s] %(message)s",
    stream=sys.stdout,
    level=logging.DEBUG if args.debug else logging.INFO,
)

logging.getLogger().name = "nameless"

# If VERSION_FLAG is present, we print the version and update version file, then f- off.
if args.version:
    print(NamelessConfig.__version__)

    with FileLock("version.txt.lck"), open("version.txt", "w") as version_file:
        version_file.write(NamelessConfig.__version__)

    exit(0)


intents = discord.Intents.default()
intents.message_content = NamelessConfig.INTENT.MESSAGE
intents.members = NamelessConfig.INTENT.MEMBER

nameless = Nameless(
    intents=intents,
    tree_cls=NamelessCommandTree,
    is_debug=args.debug,
    description=NamelessConfig.__description__,
)

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
