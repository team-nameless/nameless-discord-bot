# :D
:warning: Don't try to understand this.
```shell
# PostgreSQL setup
# TYPE IN ORDER
sudo apt update
sudo apt install postgresql postgresql-contrib -y
sudo -i -u postgres
createuser --interactive
# Type your [role-name]
# "y"
psql -U postgres
\password [role-name]
# Type your [password]
# Type your [password], again
CREATE DATABASE [db-name];
\q
# Quit current terminal session
sudo service postgresql start

# In case you are f- up sometimes
# https://stackoverflow.com/questions/21530577/fatal-error-python-h-no-such-file-or-directory
# And: sudo apt install python3.x-distutils -y

# Install core dependencies
pip install -r requirements_core.txt

# (Optional, only when contributing to code)
# Install development dependencies
pip install -r requirements_dev.txt 
```

```python
# config.py
"""
cogs/
customs/
[everything else]
main.py
config.py <- It should be here
"""
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
    POSTGRES: Dict[str, Any] = {
        "username": "swyrin",
        "password": "qu1tg4m3",
        "host": "swyrin.me",
        "port": 5432,
        "db_name": "lilia",
    }
    
    # osu! client info
    # https://osu.ppy.sh/docs/index.html#registering-an-oauth-application
    # don't even care about Redirect URL
    OSU: Dict[str, Any] = {
        "client_id": 9742,
        "client_secret": "5kXYHNfXOUPM6S8R62QMfBGL4sNwDpkm9RprYseH",
    }
```