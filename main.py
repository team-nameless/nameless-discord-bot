import logging
import sys
from typing import List

import discord
from discord.ext import commands

import NamelessConfig
from nameless import Nameless


def main(args: List[str]):
    try:
        cfg = NamelessConfig.NamelessConfig
        prefixes = getattr(cfg, "PREFIXES", [])
        allow_mention = getattr(cfg, "RECEIVE_MENTION_PREFIX", False)

        intents = discord.Intents.default()
        intents.message_content = getattr(cfg, "RECEIVE_TEXTS", False)
        intents.members = getattr(cfg, "RECEIVE_MEMBER_EVENTS", False)

        nameless = Nameless(
            config_cls=cfg,
            intents=intents,
            command_prefix=commands.when_mentioned_or(*prefixes) if allow_mention else prefixes,
            allow_updates_check="--allow-updates-check" in args,
            description=getattr(cfg, "BOT_DESCRIPTION", ""),
        )

        nameless.start_bot()
    except ModuleNotFoundError:
        logging.error("You need to provide a NamelessConfig.py file in the same directory with this file!")
        logging.error("This program will now exit! (with code 128)")
        sys.exit(128)


if __name__ == "__main__":
    main(sys.argv)
