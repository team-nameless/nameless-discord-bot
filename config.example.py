from typing import List, Any, Dict, Optional

import discord


class Config:
    # Enable experimental stuffs
    # Set to True if you know what you are doing
    LAB: bool = False

    # Bot token
    # Get it here: https://discord.com/developers/applications/{your-bot-id}/bot
    TOKEN: str = ""

    # Support server invite
    SUPPORT_SERVER_INVITE: str = "https://rick-roll.ed"

    # Guild IDs to register commands
    # Leave empty array for global (slash commands takes one hour to mitigate, text takes immediately)
    GUILD_IDs = []

    # Choose which cog(s) to load
    # Available options: Config, Experimental (requires `LAB` set as True), General, Moderator,
    #                    Music (requires `LAVALINK` to be properly provided),
    #                    Osu (requires `OSU` to be properly provided), Owner
    COGS: List[str] = ["Music", "Osu", "General"]

    # Guild prefixes for text commands
    PREFIXES: List[str] = ["alongprefix."]

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
    # It is recommended that you set a simple database such as SQLite or MongoDB/MongoDB Atlas
    # Use "mongodb" dialect for Mongo ("srv" as "driver" if using Atlas), "sqlite" for SQLite of Python, "" as "driver)
    # Please note: Install driver BY YOURSELF if NOT using SQLite or MongoDB/MongoDB Atlas.
    # For example with PostgreSQL: pip install psycopg2-binary, then use "psycopg2" as "driver" below.
    # If you are too lazy to set this, leave this as default.
    DATABASE: Optional[Dict[str, Any]] = {
        "dialect": "sqlite",
        "driver": "",
        "username": "",
        "password": "",
        "host": "",
        "port": None,
        "db_name": "lilia.db",
    }

    # Configurations for Lavalink servers for music commands
    LAVALINK: Dict[str, Any] = {
        "nodes": [],
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
