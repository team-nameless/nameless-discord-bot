from typing import Any, Optional

import discord


__all__ = ["NamelessDropdown"]


class NamelessDropdown(discord.ui.Select):
    def __init__(self):
        super().__init__(
            custom_id="nameless-dropdown",
            placeholder="Default dropdown",
            min_values=1,
            max_values=10,
            options=[],
        )

    async def callback(self, _: discord.Interaction) -> Any:
        v: Optional[discord.ui.View] = self.view
        if v:
            v.stop()
