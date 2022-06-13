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
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(
    customs.ColoredFormatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
)
logging.getLogger().handlers[:] = [handler]
