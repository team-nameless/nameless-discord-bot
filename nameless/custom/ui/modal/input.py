from collections.abc import Callable
from typing import Generic, TypeVar, override

import discord
from discord import ui

V = TypeVar("V", bound=str | int | float | None)

__all__ = ["NamelessModalInput"]


class NamelessModalInput(Generic[V], ui.TextInput[ui.Modal]):
    def __init__(
        self,
        label: str,
        custom_id: str,
        default: str = "0",
        *,
        convert: Callable[[str], V] = str,
    ):
        super().__init__(
            label=label, custom_id=custom_id, placeholder=default, default=default
        )
        self.convert: Callable[[str], V] = convert
        self.input: V = self.convert(default)

    @override
    async def callback(self, interaction: discord.Interaction):
        self.input = self.convert(self.value)
