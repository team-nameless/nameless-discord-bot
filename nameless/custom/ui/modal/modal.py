from typing import Generic, TypeVar, cast, override

import discord

from nameless.custom.ui.modal.input import NamelessModalInput

V = TypeVar("V", bound=str | int | float | None, covariant=True)

__all__ = ["NamelessModal"]


class NamelessModal(discord.ui.Modal, Generic[V]):
    def __init__(self, title: str) -> None:
        super().__init__(timeout=30, title=title)

    @override
    async def on_submit(self, interaction: discord.Interaction[discord.Client]) -> None:
        await interaction.response.defer()
        for child in self.children:
            if isinstance(child, CustomInput):
                await child.callback(interaction)
        self.stop()

    def get_input(self) -> NamelessModalInput[V]:
        return cast(NamelessModalInput[V], self.children[0])

    @property
    def value(self) -> V:
        return self.get_input().input
