import logging

import discord
from discord.ext import commands

import NamelessConfig
from nameless import Nameless


def main():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    try:
        cfg = NamelessConfig.NamelessConfig

        nameless = Nameless(
            config_cls=cfg,
            instance_name="nameless1",
            intents=intents,
            command_prefix=commands.when_mentioned_or(*getattr(cfg, "PREFIXES", [])),
        )

        nameless.start_bot()
    except ModuleNotFoundError:
        logging.error(
            "You need to provide a NamelessConfig.py file in the same directory with this file!"
        )


if __name__ == "__main__":
    main()
