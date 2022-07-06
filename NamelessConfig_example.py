from typing import Any, Dict, List, Optional

import discord

__all__ = ["NamelessConfig"]


class NamelessConfig:
    # Enable experimental stuffs
    # Set to True if you know what you are doing
    LAB: bool = False

    # Bot token
    # Get it here: https://discord.com/developers/applications/{your-bot-id}/bot
    TOKEN: str = ""

    # Choose when to receive message commands
    # This will *potentially* slow down the bot if your bot is in many (large) guilds
    RECEIVE_MESSAGE_COMMANDS: bool = True

    # Whether to receive mention prefix
    RECEIVE_MENTION_PREFIX: bool = True

    # Bot description
    BOT_DESCRIPTION: str = "Just a bot"

    # Support server url
    SUPPORT_SERVER_URL: str = "https://example.com"

    # Guild IDs to register commands
    # Leave empty array for global (slash commands takes one hour to mitigate, text takes immediately)
    GUILD_IDs = []

    # Choose which cog(s) to load
    # Available options:    NamelessConfig,
    #                       Experimental (requires `LAB` set as True),
    #                       General,
    #                       Moderator,
    #                       Music (requires `LAVALINK` to be properly provided),
    #                       Osu (requires `OSU` to be properly provided),
    #                       Owner
    COGS: List[str] = ["Music", "Osu", "General"]

    # Guild prefixes for text commands
    PREFIXES: List[str] = ["aprefix."]

    # Bot status
    # For example: "Playing with me"
    STATUS: Dict[str, Any] = {
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
    DATABASE: Optional[Dict[str, Any]] = {
        "dialect": "sqlite",
        "driver": "",
        "username": "",
        "password": "",
        "host": "",
        "port": None,
        "db_name": "nameless.db",
    }

    # Configurations for Lavalink servers for music commands
    LAVALINK: Dict[str, Any] = {
        # Your lavalink nodes
        # Each node is a dictionary with the following keys: host (str), port (int), password (str), is_secure (bool)
        "nodes": [],
        # Spotify configuration
        # You can get these from here: https://developer.spotify.com/dashboard/applications
        # Safe to ignore?
        "spotify": {
            "client_id": "",
            "client_secret": "",
        },
    }

    # Configurations for osu! commands
    # How-to: https://osu.ppy.sh/docs/index.html#client-credentials-grant
    OSU: Dict[str, Any] = {
        "client_id": 0,
        "client_secret": "",
    }
