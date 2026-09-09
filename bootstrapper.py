import logging

import discord
from dotenv import find_dotenv, load_dotenv

from nameless import Nameless, nameless_config

find_dotenv(raise_error_if_not_found=True)
load_dotenv()

discord.utils.setup_logging(level=logging.DEBUG if nameless_config.dev.debug else logging.INFO)
logging.getLogger().name = "nameless"

Nameless().start_bot(is_debug=nameless_config.dev.debug)
