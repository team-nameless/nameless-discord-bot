import logging
import sys
from typing import List

import discord
from discord.ext import commands

import NamelessConfig_example
from nameless import Nameless, shared_vars


UPDATE_CHECK_FLAG = "--allow-updates-check"
CONFIG_CLASS_FLAG = "--config"


def main(args: List[str]):
    cls_arg = [arg for arg in args if arg.startswith(f"{CONFIG_CLASS_FLAG}=")]

    if cls_arg:
        try:
            cfg = __import__(cls_arg[0][len(f"{CONFIG_CLASS_FLAG}=") :]).NamelessConfig  # noqa: E203
        except (ValueError, ModuleNotFoundError):
            cfg = NamelessConfig_example.NamelessConfig
            logging.warning(f"Invalid value for '--config' flag: {cfg.__module__.__name__}")
            logging.warning("Maybe an invalid module name, or NamelessConfig class in not in it?")
            logging.warning("NamelessConfig_example.NamelessConfig will be used as fallback option")
    else:
        cfg = NamelessConfig_example.NamelessConfig

    shared_vars.config_cls = cfg
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

    nameless.start_bot()


if __name__ == "__main__":
    main(sys.argv)
