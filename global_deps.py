import logging
import sys
from datetime import datetime

from discord import Permissions

import customs
from config import Config
from database import CRUD

# Database setup
crud_database = CRUD()

# Stuffs
__nameless_version__ = "0.0.1-beta1"
needed_permissions = (
    Permissions.manage_roles
    or Permissions.manage_channels
    or Permissions.kick_members
    or Permissions.ban_members
    or Permissions.read_messages
    or Permissions.view_channel
    or Permissions.moderate_members
    or Permissions.send_messages
    or Permissions.send_messages_in_threads
    or Permissions.manage_messages
    or Permissions.embed_links
    or Permissions.attach_files
    or Permissions.read_message_history
    or Permissions.read_message_history
    or Permissions.use_external_stickers
    or Permissions.use_external_emojis
    or Permissions.add_reactions
    or Permissions.use_application_commands
    or Permissions.connect
    or Permissions.speak
    or Permissions.use_voice_activation
)

start_time: datetime = datetime.min

# Logging setup
log_level: int = (
    logging.DEBUG if hasattr(Config, "LAB") and Config.LAB else logging.INFO
)
logging.getLogger().handlers.clear()
logging.basicConfig(level=log_level)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(
    customs.ColoredFormatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
)
logging.getLogger().handlers[:] = [handler]
