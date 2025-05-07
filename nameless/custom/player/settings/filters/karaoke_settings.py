# pyright: reportCallIssue=false

from enum import Enum
from typing import TypedDict, cast, final, override

import discord
import wavelink
from discord.ext import commands
from wavelink.types.filters import Karaoke as KaraokePayload

from nameless import Nameless
from nameless.custom.player.settings.filters.base import FilterModal, FilterView
from nameless.custom.ui import NamelessDropdown
from nameless.custom.ui.modal import NamelessModalInput


class KaraokeFlags(Enum):
    LEVEL = "level"
    MONO_LEVEL = "mono_level"
    FILTER_BAND = "filter_band"
    FILTER_WIDTH = "filter_width"
    EXIT = "exit"
    SAVE = "save"


class LevelView(FilterModal):
    @override
    def on_create(self):
        self.add_item(
            NamelessModalInput(
                label="Level", custom_id="level_input", default="0", convert=int
            )
        )


class MonoLevelView(FilterModal):
    @override
    def on_create(self):
        self.add_item(
            NamelessModalInput(
                label="Mono Level",
                custom_id="mono_level_input",
                default="0",
                convert=int,
            )
        )


class FilterBandView(FilterModal):
    @override
    def on_create(self):
        self.add_item(
            NamelessModalInput(
                label="Filter Band",
                custom_id="filter_band_input",
                default="0",
                convert=int,
            )
        )


class FilterWidthView(FilterModal):
    @override
    def on_create(self):
        self.add_item(
            NamelessModalInput(
                label="Filter Width",
                custom_id="filter_width_input",
                default="0",
                convert=int,
            )
        )


class OptionsType(TypedDict):
    view_class: type[FilterModal]
    title: str
    description: str
    message: str


OPTION_MAPPING: dict[KaraokeFlags, OptionsType] = {
    KaraokeFlags.LEVEL: {
        "view_class": LevelView,
        "title": "Karaoke Level",
        "description": "Enter a new level",
        "message": "Level set to {value}",
    },
    KaraokeFlags.MONO_LEVEL: {
        "view_class": MonoLevelView,
        "title": "Karaoke Mono Level",
        "description": "Enter a new mono level",
        "message": "Mono level set to {value}",
    },
    KaraokeFlags.FILTER_BAND: {
        "view_class": FilterBandView,
        "title": "Karaoke Filter Band",
        "description": "Enter a new filter band",
        "message": "Filter band set to {value}",
    },
    KaraokeFlags.FILTER_WIDTH: {
        "view_class": FilterWidthView,
        "title": "Karaoke Filter Width",
        "description": "Enter a new filter width",
        "message": "Filter width set to {value}",
    },
}


@final
class KaraokeSettingDropdown(NamelessDropdown):
    def __init__(self, filters: wavelink.Filters):
        super().__init__(custom_id="karaoke_dropdown", placeholder="Select a setting")

        for flag in KaraokeFlags:
            self.add_option(label=flag.name.replace("_", " ").title(), value=flag.value)

        self._modal: FilterModal | None = None
        self._output_message: str | None = None

        self.filters = filters

    def get_selected_flag(self) -> KaraokeFlags:
        return KaraokeFlags(self.values[0])

    def get_field_index(self) -> str:
        return self.get_selected_flag().value

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

        selected_flag = self.get_selected_flag()
        if selected_flag in {KaraokeFlags.EXIT, KaraokeFlags.SAVE}:
            getattr(view, selected_flag.value)()  # damn, super hack
            return

        option = OPTION_MAPPING.get(selected_flag)

        if not option:
            return await interaction.response.send_message("Invalid option selected")

        view_class = option["view_class"]
        title = option["title"]
        self._output_message = option["message"]

        self._modal = view_class(title=title, filters=self.filters)
        await interaction.response.send_modal(self._modal)
        if await self._modal.wait():
            return

        cast(FilterView, self.view).set_filter(
            "karaoke", selected_flag.value, self._modal.value
        )
        view.stop()


class KaraokeSettingView(FilterView):
    def __init__(
        self,
        author: discord.Member | discord.User,
        message: discord.Message,
        filters: wavelink.Filters,
    ):
        super().__init__(author, message, filters)
        self.add_item(KaraokeSettingDropdown(filters))

    @override
    def get_dropdown(self) -> KaraokeSettingDropdown:
        return cast(KaraokeSettingDropdown, self.children[0])


def make_embed(payload: KaraokePayload) -> discord.Embed:
    return (
        discord.Embed(
            title="Karaoke Settings",
            description="Select a setting to change",
            color=discord.Color.blurple(),
        )
        .add_field(
            name=f"Level {payload.get('level', 0)}",
            value="Change the level of the karaoke effect",
            inline=False,
        )
        .add_field(
            name=f"Mono Level {payload.get('monoLevel', 0)}",
            value="Change the mono level of the karaoke effect",
            inline=False,
        )
        .add_field(
            name=f"Filter Band {payload.get('filterBand', 0)}",
            value="Change the filter band of the karaoke effect",
            inline=False,
        )
        .add_field(
            name=f"Filter Width {payload.get('filterWidth', 0)}",
            value="Change the filter width of the karaoke effect",
            inline=False,
        )
    )


async def make(
    ctx: commands.Context[Nameless],
    message: discord.Message,
    filters: wavelink.Filters,
    voice_client: wavelink.Player,
):
    if not any(filters.karaoke.payload):
        filters.karaoke.reset()

    while True:
        view = KaraokeSettingView(ctx.author, message, filters)
        await message.edit(view=view, embed=make_embed(filters.karaoke.payload))

        if await view.wait():
            return

        if view.is_exit():
            break

        if view.is_save():
            await voice_client.set_filters(filters)
            return

    await ctx.send("Karaoke settings not saved", ephemeral=True, delete_after=5)
