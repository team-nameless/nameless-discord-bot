import re
from datetime import datetime
from typing import List

from discord import Permissions
import requests

from database.crud import CRUD

# Database setup
crud_database: CRUD

# Stuffs
cogs_regex = re.compile(r"^(?!_.).*Cog.py")
upstream_version_txt_url = (
    "https://raw.githubusercontent.com/nameless-on-discord/nameless/main/version.txt"
)
additional_handlers: List = []
__nameless_current_version__ = "0.8.2-beta"
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
needed_permissions.create_instant_invite = True

start_time: datetime = datetime.min
