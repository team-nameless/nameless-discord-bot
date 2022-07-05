import logging
import logging.handlers
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands

import nameless.shared_vars
from nameless import Nameless
from nameless.commons import Utility
from config import Config

os.chdir(Path(__file__).resolve().parent)
log_level: int = (
    logging.DEBUG if hasattr(Config, "LAB") and Config.LAB else logging.INFO
)
logging.basicConfig(level=log_level)
logging.getLogger().handlers[:] = [nameless.shared_vars.stdout_handler]


def main():
    can_cont = Utility.is_valid_config_class(Config)

    if not isinstance(can_cont, bool):
        logging.warning(
            "This bot might run into error because not all fields are presented"
        )
    else:
        if not can_cont:
            logging.error("Fields validation failed, the bot will exit")
            sys.exit()

    prefixes = Config.PREFIXES
    allow_mention = (
        hasattr(Config, "RECEIVE_MENTION_PREFIX") and Config.RECEIVE_MENTION_PREFIX
    )

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = (
        hasattr(Config, "RECEIVE_MESSAGE_COMMANDS") and Config.RECEIVE_MESSAGE_COMMANDS
    )

    inst = Nameless(
        commands.when_mentioned_or(*prefixes) if allow_mention else prefixes,
        intents=intents,
        description=Config.BOT_DESCRIPTION,
        log_level=log_level,
        allow_updates_checks=True,
    )
    inst.start_bot()


if __name__ == "__main__":
    main()
