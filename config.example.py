from typing import List, Any, Dict
import nextcord


class Config:
    # Enable more logging and experimental features
    # Normally you don't want to set this to True
    LAB: bool = False

    # Your Discord bot token
    TOKEN: str = ""

    # List[str] if you need to register guild-only
    # nextcord.utils.MISSING otherwise
    GUILD_IDs = nextcord.utils.MISSING

    # Prefixes for text commands
    PREFIXES: List[str] = ["alongprefix."]

    # Your Discord status
    STATUS: Dict[str, Any] = {
        # Allowed: watching, competing, playing, listening, streaming
        "type": nextcord.ActivityType.watching,
        "name": "you",
        # Allowed: dnd, idle, online, invisible, offline
        "user_status": nextcord.Status.dnd,
        # if "type" is "nextcord.ActivityType.streaming"
        "url": "",
    }

    # Your database
    # Watch above for guide
    DATABASE: Dict[str, Any] = {
        # If you have any other DBMS that you like, feel free to use
        # As long as SQLAlchemy supports it - https://docs.sqlalchemy.org/en/14/core/engines.html
        # I will PostgreSQL for the sake of this guide
        "dialect": "postgresql",
        "driver": "psycopg2",
        "username": "[role-name]",
        "password": "[password]",
        "host": "localhost",
        "port": 5432,
        "db_name": "[db-name]",
    }

    # osu! client info
    # https://osu.ppy.sh/docs/index.html#registering-an-oauth-application
    # don't even care about Redirect URL
    OSU: Dict[str, Any] = {
        "client_id": 0,
        "client_secret": "",
    }
