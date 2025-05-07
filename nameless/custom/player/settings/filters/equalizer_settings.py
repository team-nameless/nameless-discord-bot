# pyright: reportCallIssue=false

from collections.abc import Iterable
from typing import cast, final, override

import discord
import wavelink
from discord.ext import commands
from wavelink.types.filters import Equalizer as EqualizerPayload

from nameless import Nameless
from nameless.custom.player.settings.filters.base import FilterView
from nameless.custom.ui import NamelessDropdown
from nameless.custom.ui.modal import NamelessModal, NamelessModalInput


def plot_eq(
    values: Iterable[EqualizerPayload], offset: float = 0.25, multiplier: int = 4
):
    gains = [(value["gain"] + offset) * multiplier for value in values]
    cells = [f"{i}  " + "▌" * int(value) for i, value in enumerate(gains, start=1)]
    return "\n".join(cells)


class EqualizerInput(NamelessModalInput[float]):
    @override
    async def callback(self, interaction: discord.Interaction): ...


class EqualizerModal(NamelessModal[float]):
    def __init__(self, title: str, filters: wavelink.Filters) -> None:
        super().__init__(title)
        self.add_item(
            NamelessModalInput(
                label="Gain", custom_id="gain_eq", default="0", convert=float
            )
        )


@final
class EqualizerSettingDropdown(NamelessDropdown):
    def __init__(self, filters: wavelink.Filters):
        super().__init__(custom_id="equalizer_dropdown", placeholder="Select a band")

        for eq in filters.equalizer.payload.values():
            self.add_option(
                label=f"Band {eq['band']}",
                value=str(eq["band"]),
                description=f"{'+' if eq['gain'] >= 0 else ''}{eq['gain']}",
            )
        self.add_option(label="Exit", value="-1")
        self.add_option(label="Save", value="-2")

        self._modal: EqualizerModal | None = None
        self._output_message: str | None = None

        self.filters = filters

    def get_field_index(self) -> int:
        return int(self.values[0])

    @property
    def output_message(self) -> str:
        if not self._output_message:
            return "No message"
        return self._output_message

    @property
    def input_value(self):
        if not self._modal:
            return 0
        return self._modal.value

    @override
    async def callback(self, interaction: discord.Interaction[discord.Client]):
        assert self.view
        view = cast(FilterView, self.view)

        get_index = self.get_field_index()
        if get_index == -1:
            return view.exit()
        elif get_index == -2:
            return view.save()

        self._modal = EqualizerModal(
            title=f"Change gain for band {get_index}", filters=self.filters
        )
        await interaction.response.send_modal(self._modal)
        if await self._modal.wait():
            return

        cast(FilterView, self.view).set_filter("equalizer", "bands")
        view.stop()


class EqualizerSettingView(FilterView):
    def __init__(
        self,
        author: discord.Member | discord.User,
        message: discord.Message,
        filters: wavelink.Filters,
    ):
        super().__init__(author, message, filters)
        self.add_item(EqualizerSettingDropdown(filters))

    @override
    def get_dropdown(self) -> EqualizerSettingDropdown:
        return cast(EqualizerSettingDropdown, self.children[0])


def make_embed(payload: dict[int, EqualizerPayload]) -> discord.Embed:
    return discord.Embed(
        title="Equalizer Settings",
        description="Select a setting to change",
        color=discord.Color.blurple(),
    ).add_field(
        name="Current settings",
        value=f"```{plot_eq(payload.values())}```",
        inline=False,
    )


async def make(
    ctx: commands.Context[Nameless],
    message: discord.Message,
    filters: wavelink.Filters,
    voice_client: wavelink.Player,
):
    if not any(filters.equalizer.payload):
        filters.equalizer.reset()

    while True:
        view = EqualizerSettingView(ctx.author, message, filters)
        await message.edit(view=view, embed=make_embed(filters.equalizer.payload))

        if await view.wait():
            return

        if view.is_exit():
            break

        if view.is_save():
            await voice_client.set_filters(filters)
            return

    await ctx.send("Equalizer settings not saved", ephemeral=True, delete_after=5)
