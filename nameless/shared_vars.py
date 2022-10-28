import logging
import re
import sys
from datetime import datetime
from typing import Any, List

from discord import Permissions

from nameless import customs
from nameless.database import CRUD


# Setup
crud_database: CRUD
config_cls: Any

# Logging
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(customs.ColoredFormatter())
additional_handlers: List = []

# Patterns
cogs_regex = re.compile(r"^(?!_.).*Cog.py")

# Meta
upstream_version_txt_url: str
start_time: datetime = datetime.min
__nameless_current_version__ = "2.0.0"
__nameless_upstream_version__: str

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
needed_permissions.create_instant_invite = True
