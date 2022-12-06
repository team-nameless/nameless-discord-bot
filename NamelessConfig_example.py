from typing import Any, Dict, List, Optional

import discord
from typing_extensions import LiteralString


__all__ = ["NamelessConfig"]


class NamelessConfig:
    # Enable stuffs for developers
    # Set to True if you know what you are doing
    DEV: bool = False

    # Bot token
    # Go to here: https://discord.com/developers/applications/
    # Then pick your client, then go to Bot->Copy Token
    TOKEN: LiteralString = ""

    # Choose when to receive texts
    # This will potentially slow down the bot if your bot is in many (large) guilds
    # This will decide whether the bot should:
    # - Receive text commands
    # - Receive response from prompts (will use default values)
    # (Requires "MESSAGE CONTENT" intent to be enabled on bot dashboard if this sets to True)
    # (Might require verification if the bot is over 100 guilds)
    RECEIVE_TEXTS: bool = False

    # Choose when to receive member events
    # This will potentially slow down the bot if your bot is in many (large) guilds
    # This will decide whether the bot should:
    # - Receive guild member event (for welcome/goodbye notifications)
    # (Requires "GUILD MEMBERS" intent to be enabled on bot dashboard if this sets to True)
    # (Might require verification if the bot is over 100 guilds)
    RECEIVE_MEMBER_EVENTS: bool = True

    # Choose when to receive mention prefix
    # This is unaffected by the RECEIVE_TEXT setting since Discord allow mentions to the bot, despite "MESSAGE CONTENT"
    # intent is disabled
    RECEIVE_MENTION_PREFIX: bool = True

    # Metadata of the bot
    META: Dict[LiteralString, Any] = {
        # Any source control link
        # Use falsy values for closed source (like when you have a private fork), but remember to comply the license.
        "source_code": "https://github.com/nameless-on-discord/nameless",
        # A link leading to the RAW version.txt file, used for upstream version checking
        # If this is a falsy value, https://raw.githubusercontent.com/nameless-on-discord/nameless/main/version.txt
        "version_txt": "https://raw.githubusercontent.com/nameless-on-discord/nameless/feat/v2/version.txt",
        # Bot support server URL
        # This should be a valid Discord invite URL, or a URL that leads to a valid Discord invite URL
        "support_server_url": "",
        # Bot custom version, should be a string:
        # Falsy value will use the value provided in nameless/shared_vars.py
        "version": None,
        # Bot description
        # Placeholders: {source_code} - META[source_code], or "original nameless repo" if META[source_code] is ""
        #                               If it was set to None, set to literal "{source_code}"
        "bot_description": "Just a bot",
    }

    # Guild IDs to register commands
    # Leave empty array for global (slash commands takes one hour to mitigate, text takes immediately)
    GUILD_IDs: List[int] = []

    # Choose which cog(s) to load
    # Available options:    Config,
    #                       Moderator,
    #                       MusicV1 (requires `LAVALINK` to be properly provided),
    #                       Osu (requires `OSU` to be properly provided),
    #                       Owner
    COGS: List[LiteralString] = [
        "MusicV1",
        "Owner",
        "General",
        "Config",
        "Moderator",
        "Osu",
    ]

    # Guild prefixes for text commands
    PREFIXES: List[LiteralString] = ["nameless."]

    # Bot status
    # For example: "Playing with me"
    STATUS: Dict[LiteralString, Any] = {
        # Allowed: watching, competing, playing, listening, streaming
        "type": discord.ActivityType.watching,
        "name": "you",
        # Allowed: dnd, idle, online, invisible, offline
        "user_status": discord.Status.dnd,
        # if "type" is "discord.ActivityType.streaming"
        "url": "",
    }

    # Database configuration
    # It is recommended that you set a simple database such as SQLite
    # Please note: Install driver BY YOURSELF if NOT using SQLite.
    # For example with PostgreSQL: pip install psycopg2-binary, then use "psycopg2" as "driver" below.
    # If you are too lazy to set this, leave this as default.
    DATABASE: Optional[Dict[LiteralString, Any]] = {
        "dialect": "sqlite",
        "driver": "",
        "username": "",
        "password": "",
        "host": "",
        "port": None,
        "db_name": "nameless.db",
    }

    # Configurations for Lavalink servers for music commands
    LAVALINK: Dict[LiteralString, Any] = {
        # Your lavalink node configurations
        # Each node config is a dictionary with the following keys:
        #   host (str),
        #   port (int),
        #   password (str),
        #   is_secure (bool)
        "nodes": [],
        # Configuration for spotify integrations, safe to ignore
        # You can get these from here: https://developer.spotify.com/dashboard/applications
        "spotify": {
            "client_id": "",
            "client_secret": "",
        },
    }

    # Configurations for osu! commands
    # How-to: https://osu.ppy.sh/docs/index.html#client-credentials-grant
    OSU: Dict[LiteralString, Any] = {
        "client_id": 0,
        "client_secret": "",
    }
