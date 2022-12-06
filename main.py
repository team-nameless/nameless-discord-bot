import sys
from typing import List

import discord
from discord.ext import commands

import NamelessConfig
from nameless import Nameless


UPDATE_CHECK_FLAG = "--allow-updates-check"


def main(args: List[str]):
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
        allow_updates_check=UPDATE_CHECK_FLAG in args,
        description=getattr(cfg, "META", {}).get("bot_description", ""),
    )

    nameless.patch_loggers()
    nameless.start_bot()


if __name__ == "__main__":
    main(sys.argv)
