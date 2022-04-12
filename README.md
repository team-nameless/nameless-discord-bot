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
    TOKEN: str = "your-bot-token-here"
    # List[int] or nextcord.utils.MISSING
    GUILD_IDs = []
    PREFIXES: List[str] = ["alongprefix."]
    # Look above
    POSTGRES: Dict[str, Any] = {
        "username": "[role-name]",
        "password": "[password]",
        "host": "localhost",
        "port": 5432,
        "db_name": "[db-name]"
    }

```