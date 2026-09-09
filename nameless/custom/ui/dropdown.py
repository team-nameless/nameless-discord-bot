import os
from collections.abc import Callable
from typing import Self, override

import discord
from discord import ui

__all__ = ["NamelessDropdown"]


_DropdownCallback = Callable[[discord.Interaction], str | None]
"""
A callback for a dropdown.

Parameters:
-----------
interaction: `discord.Interaction`
    The interaction object.

Returns:
--------
`str` | `None`
    Return with a string to mark it as an error message, otherwise None.
"""


class NamelessDropdown(ui.Select[ui.View]):
    """nameless* custom dropdown."""

    def __init__(
        self,
        custom_id: str | None = None,
        placeholder: str | None = "Select an option",
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
    ):
        assert min_values >= 1
        assert max_values >= 1
        assert min_values <= max_values

        self._callback: list[_DropdownCallback] = []

        if custom_id is None:
            custom_id = "nameless-dropdown-" + os.urandom(16).hex()

        super().__init__(
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            disabled=disabled,
            options=[],
        )

    def push_callback(self, callback: _DropdownCallback) -> Self:
        self._callback.append(callback)
        return self

    @override
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        for callback in self._callback:
            error = callback(interaction)
            if error:
                await interaction.response.send_message(error, ephemeral=True)
                return

        if self.view is not None:
            self.view.stop()

    def push_option(
        self,
        *,
        label: str,
        value: str = "",
        description: str | None = None,
        emoji: str | discord.Emoji | discord.PartialEmoji | None = None,
        default: bool = False,
    ) -> Self:
        self.add_option(
            label=label,
            value=value,
            description=description,
            emoji=emoji,
            default=default,
        )
        return self
