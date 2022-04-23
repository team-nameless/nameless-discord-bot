# nameless

A rewrite of [Lilia-#master](https://github.com/Lilia-Workshop/Lilia/tree/master) and an extension of [nameless](https://github.com/FoxeiZ/nameless), in python. More extensibility, less proprietary. Keep the original Lilia mindset.

[![CodeFactor](https://www.codefactor.io/repository/github/lilia-workshop/lilia/badge/new)](https://www.codefactor.io/repository/github/lilia-workshop/lilia/overview/new)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> ⚠️ This project goes through continuous development 24/7 so **please don't** expect this to work properly.

# Before you get your hands dirty

```shell
# TYPE IN ORDER
# Tested with Python 3.10 w/ Ubuntu 22.04
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

# Config file `config.py`

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
        # If you have any other DBMS that you like, feel free to use
        # As long as SQLAlchemy supports it
        # https://docs.sqlalchemy.org/en/14/core/engines.html
        "dialect": "postgresql",
        "driver": "psycopg2"

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
```

# Credits
![Me](https://img.shields.io/badge/%E2%9D%A4%EF%B8%8FMade%20with%20love%20by-Swyrin%237193-red?style=for-the-badge&logo=discord)
![Python God](https://img.shields.io/badge/Python%20God-C%C3%A1o%20trong%20s%C3%A1ng%238029-blue?style=for-the-badge&logo=python)