import logging
import logging.handlers
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands

import nameless.shared_vars
from config import Config
from nameless import Nameless
from nameless.commons import Utility

os.chdir(Path(__file__).resolve().parent)
log_level: int = logging.DEBUG if getattr(Config, "LAB", False) else logging.INFO
logging.basicConfig(level=log_level)
logging.getLogger().handlers[:] = [nameless.shared_vars.stdout_handler]


def main():
    can_cont = Utility.is_valid_config_class(Config)

    if not isinstance(can_cont, bool):
        logging.warning(
            "This bot might run into errors because not all fields are presented"
        )
    else:
        if not can_cont:
            logging.error("Fields validation failed, the bot will exit")
            sys.exit()

    prefixes = getattr(Config, "PREFIXES", [])
    allow_mention = getattr(Config, "RECEIVE_MENTION_PREFIX", False)

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = getattr(Config, "RECEIVE_MESSAGE_COMMANDS", False)

    inst = Nameless(
        commands.when_mentioned_or(*prefixes) if allow_mention else prefixes,
        intents=intents,
        config_cls=Config,
        log_level=log_level,
        allow_updates_checks=True,
    )
    inst.start_bot()


if __name__ == "__main__":
    main()
