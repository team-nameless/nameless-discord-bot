from typing import List, Any, Dict, Optional

import discord


class Config:
    LAB: bool = True

    TOKEN: str = ""
    GUILD_IDs = []
    PREFIXES: List[str] = ["alongprefix."]

    STATUS: Dict[str, Any] = {
        # Allowed: watching, competing, playing, listening, streaming
        "type": discord.ActivityType.watching,
        "name": "you",
        # Allowed: dnd, idle, online, invisible, offline
        "user_status": discord.Status.dnd,
        # if "type" is "discord.ActivityType.streaming"
        "url": "",
    }

    DATABASE: Optional[Dict[str, Any]] = {
        "dialect": "postgresql",
        "driver": None,
        "username": "swyrin",
        "password": "uwu",
        "host": "localhost",
        "port": 5432,
        "db_name": "lilia",
    }

    OSU: Dict[str, Any] = {
        "client_id": 0,
        "client_secret": "",
    }
