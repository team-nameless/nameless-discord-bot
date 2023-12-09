from typing import Any

import discord

__all__ = ["NamelessDropdown"]


class NamelessDropdown(discord.ui.Select):
    def __init__(self):
        super().__init__(
            custom_id="nameless-dropdown", placeholder="Default dropdown", min_values=1, max_values=10, options=[]
        )

    async def callback(self, _: discord.Interaction) -> Any:
        v: discord.ui.View | None = self.view
        if v:
            v.stop()
