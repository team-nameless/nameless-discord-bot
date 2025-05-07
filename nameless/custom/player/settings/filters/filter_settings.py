from enum import Enum
from typing import cast, override

import discord
import wavelink
from discord.ext import commands

from nameless import Nameless
from nameless.custom.player.settings.base import BaseSettingsView
from nameless.custom.player.settings.filters.karaoke_settings import (
    make as karaoke_make,
)
from nameless.custom.ui import NamelessDropdown

__all__ = ["make"]


class FilterFlags(Enum):
    EXIT = "-1"
    EQUALIZER = "0"
    KARAOKE = "1"
    TIMESCALE = "2"
    TREMOLO = "3"
    VIBRATO = "4"
    DISTORTION = "5"
    ROTATION = "6"


class FilterDropdown(NamelessDropdown):
    def __init__(self, custom_id: str = "filter_dropdown"):
        super().__init__(custom_id=custom_id, placeholder="Select a setting")

        for flag in FilterFlags:
            self.add_option(label=flag.name.capitalize(), value=flag.value)

    def get_selected_flag(self) -> FilterFlags:
        return FilterFlags(self.values[0])


class SettingsView(BaseSettingsView):
    def __init__(self, author: discord.Member | discord.User, message: discord.Message):
        super().__init__(author, message)
        self.add_item(FilterDropdown())

    @override
    def get_dropdown(self) -> FilterDropdown:
        return cast(FilterDropdown, self.children[0])


async def make(ctx: commands.Context[Nameless]):
    assert ctx.guild is not None

    embed = (
        discord.Embed(
            title="Filter Settings",
            description="Select a filter setting to change",
            color=discord.Color.blurple(),
        )
        .add_field(name="Equalizer", value="Change the equalizer settings")
        .add_field(name="Karaoke", value="Change the karaoke settings")
        .add_field(name="Timescale", value="Change the timescale settings")
        .add_field(name="Tremolo", value="Change the tremolo settings")
        .add_field(name="Vibrato", value="Change the vibrato settings")
        .add_field(name="Distortion", value="Change the distortion settings")
        .add_field(name="Rotation", value="Change the rotation settings")
    )

    voice_client = cast(wavelink.Player, ctx.guild.voice_client)
    filters = voice_client.filters
    message = await ctx.send(embed=embed)

    while True:
        view = SettingsView(ctx.author, message)
        await message.edit(view=view, embed=embed)

        if await view.wait():
            await message.edit(view=None)
            return

        selected_flag = view.get_dropdown().get_selected_flag()
        match selected_flag:
            case FilterFlags.KARAOKE:
                await karaoke_make(ctx, message, filters, voice_client)
            case FilterFlags.EXIT:
                await message.edit(view=None)
                return
            case _:
                await ctx.send(f"Currently not supported: {selected_flag.name}")
