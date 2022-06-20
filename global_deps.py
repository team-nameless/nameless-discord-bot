import logging.handlers
import re
import sys
from datetime import datetime
from typing import List

import requests
from discord import Permissions

import customs
from config import Config
from database import CRUD

# Database setup
crud_database = CRUD()

# Stuffs
cogs_regex = re.compile(r"^(?!_.).*Cog.py")
upstream_version_txt_url = (
    "https://raw.githubusercontent.com/nameless-on-discord/nameless/main/version.txt"
)
__nameless_current_version__ = "0.5.2-beta"
__nameless_upstream_version__ = requests.get(upstream_version_txt_url).text
needed_permissions = Permissions.none()
needed_permissions.manage_roles = True
needed_permissions.manage_channels = True
needed_permissions.kick_members = True
needed_permissions.ban_members = True
needed_permissions.read_messages = True
needed_permissions.view_channel = True
needed_permissions.moderate_members = True
needed_permissions.send_messages = True
needed_permissions.send_messages_in_threads = True
needed_permissions.manage_messages = True
needed_permissions.embed_links = True
needed_permissions.attach_files = True
needed_permissions.read_message_history = True
needed_permissions.read_message_history = True
needed_permissions.use_external_stickers = True
needed_permissions.use_external_emojis = True
needed_permissions.add_reactions = True
needed_permissions.use_application_commands = True
needed_permissions.connect = True
needed_permissions.speak = True
needed_permissions.use_voice_activation = True

start_time: datetime = datetime.min

# Logging setup
log_level: int = (
    logging.DEBUG if hasattr(Config, "LAB") and Config.LAB else logging.INFO
)
logging.getLogger().handlers.clear()
logging.basicConfig(level=log_level)
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(customs.ColoredFormatter(""))

default_handlers: List[logging.Handler] = [stdout_handler]

if hasattr(Config, "LAB") and Config.LAB:
    file_handler = logging.handlers.RotatingFileHandler(
        filename="nameless.log", mode="w", backupCount=90, encoding="utf-8", delay=False
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - [%(levelname)s] [%(name)s] %(message)s")
    )
    default_handlers.append(file_handler)

logging.getLogger().handlers[:] = default_handlers
