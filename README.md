# :D
:warning: Don't try to understand this.
```shell
# In case you are f- up sometimes
# https://stackoverflow.com/questions/21530577/fatal-error-python-h-no-such-file-or-directory
# And: sudo apt install python3.x-distutils -y

# Install core requirements
pip install -r requirements_core.txt

# (Optional, only when contributing to code) install development dependencies
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
import nextcord
from typing import Union, List

TOKEN: str = "[bot-token-here]"

# None for global commands
# List[int] for guilds
GUILD_IDs: Union[nextcord.utils.MISSING | List[int]] = None
```