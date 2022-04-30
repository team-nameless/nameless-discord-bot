from typing import List, Any, Dict, Optional

import nextcord


class Config:
    LAB: bool = True

    TOKEN: str = ""
    GUILD_IDs = []
    PREFIXES: List[str] = ["alongprefix."]

    STATUS: Dict[str, Any] = {
        # Allowed: watching, competing, playing, listening, streaming
        "type": nextcord.ActivityType.watching,
        "name": "you",
        # Allowed: dnd, idle, online, invisible, offline
        "user_status": nextcord.Status.dnd,
        # if "type" is "nextcord.ActivityType.streaming"
        "url": "",
    }

    # Specialized configurations for MongoDB.
    # If both MONGODB and DATABASE options are provided, MONGO will be used.
    # Passing None to either config will use THE OTHER CONFIG. If both are None, an error will be thrown.
    MONGODB: Optional[Dict[str, Any]] = {
        "is_atlas": True,
        # For atlas
        "username": "",
        "password": "",
        "cluster_name": "",
        # Else
        "host": "localhost",
        "port": 27017,
        "db_name": "lilia",
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
