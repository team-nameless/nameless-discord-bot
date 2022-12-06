import logging
import re
import sys
from datetime import datetime
from typing import List

import requests
from discord import Permissions

from nameless import customs
from nameless.database import CRUD


# Database setup
crud_database: CRUD

# Logging
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(customs.ColoredFormatter())

# Patterns
cogs_regex = re.compile(r"^(?!_.).*Cog.py")

# Meta
upstream_version_txt_url = "https://raw.githubusercontent.com/nameless-on-discord/nameless/main/version.txt"
start_time: datetime = datetime.min
additional_handlers: List = []
__nameless_current_version__ = "1.5.3"

try:
    __nameless_upstream_version__ = requests.get(upstream_version_txt_url, timeout=10).text
except requests.exceptions.ConnectTimeout:
    __nameless_upstream_version__ = ""

# Perms
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
needed_permissions.use_external_stickers = True
needed_permissions.use_external_emojis = True
needed_permissions.add_reactions = True
needed_permissions.connect = True
needed_permissions.speak = True
needed_permissions.use_voice_activation = True
