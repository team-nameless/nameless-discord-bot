from typing import List, Any, Dict, Optional

import discord


class Config:
    # Enable experimental changes
    # Set to True if you know what you are doing
    LAB: bool = False

    # Bot token
    # Get it here: https://discord.com/developers/applications/{your-bot-id}/bot
    TOKEN: str = ""

    # Guild IDs to register commands
    # Leave empty array for global (slash commands takes one hour to mitigate, text takes immediately)
    GUILD_IDs = []
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
    # For example with PostgreSQL: pip install psycopg2-binary, then fill "psycopg2" as "driver" below.
    DATABASE: Optional[Dict[str, Any]] = {
        "dialect": "postgresql",
        "driver": None,
        "username": "swyrin",
        "password": "uwu",
        "host": "localhost",
        "port": 5432,
        "db_name": "lilia",
    }

    # Configurations for Lavalink servers for music commands
    LAVALINK = {
        "nodes": [
            {
                "host": "lavalink.darrenofficial.com",
                "port": 80,
                "password": "lavalink_is_cool",
                "is_secure": False,
            },
            {
                "host": "usui-linku.kadantte.moe",
                "port": 443,
                "password": "Usui#0256",
                "is_secure": True,
            },
            {
                "host": "lavalink.oops.wtf",
                "port": 443,
                "password": "www.freelavalink.ga",
                "is_secure": True,
            },
        ],
        "spotify": {
            "client_id": "c6716be485d048e7a1b1ef4ed1a7b648",
            "client_secret": "202cb8c313854c058ba5576e68215c14",
        },
    }

    # Configurations for osu! commands
    # How-to: https://osu.ppy.sh/docs/index.html#client-credentials-grant
    OSU: Dict[str, Any] = {
        "client_id": 0,
        "client_secret": "",
    }
