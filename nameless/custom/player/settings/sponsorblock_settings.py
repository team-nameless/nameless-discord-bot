# pyright: reportPrivateUsage=false

from typing import cast, final, override

import discord
from discord.ext import commands
from prisma.models import PlayerSettings

from nameless import Nameless
from nameless.custom.player.settings.base import BaseSettingsView
from nameless.custom.ui.dropdown import NamelessDropdown


@final
class SponsorBlockFlags:
    SPONSOR = 1 << 0  # 1
    SELFPROMO = 1 << 1  # 2
    PREVIEW = 1 << 2  # 4
    MUSIC_OFFTOPIC = 1 << 3  # 8


@final
class SettingsDropdown(NamelessDropdown):
    def __init__(self):
        super().__init__(custom_id="settings_dropdown", placeholder="Select a setting")

        self.add_option(label="Sponsor", value=str(SponsorBlockFlags.SPONSOR))
        self.add_option(label="Selfpromo", value=str(SponsorBlockFlags.SELFPROMO))
        self.add_option(label="Preview", value=str(SponsorBlockFlags.PREVIEW))
        self.add_option(
            label="Music Offtopic", value=str(SponsorBlockFlags.MUSIC_OFFTOPIC)
        )

    def get_selected_flag(self) -> int:
        return int(self.values[0])

    def get_field_index(self) -> int:
        return self.get_selected_flag() >> 1


@final
class SponsorBlockSettings:
    def __init__(self, flags: int):
        self.flags = flags

        self.sponsor = (flags & SponsorBlockFlags.SPONSOR) == SponsorBlockFlags.SPONSOR
        self.selfpromo = (
            flags & SponsorBlockFlags.SELFPROMO
        ) == SponsorBlockFlags.SELFPROMO
        self.preview = (flags & SponsorBlockFlags.PREVIEW) == SponsorBlockFlags.PREVIEW
        self.music_offtopic = (
            flags & SponsorBlockFlags.MUSIC_OFFTOPIC
        ) == SponsorBlockFlags.MUSIC_OFFTOPIC

    @classmethod
    async def get_from_database(
        cls, guild: discord.Guild | None = None
    ) -> "SponsorBlockSettings":
        assert guild is not None
        return cls(
            (
                await PlayerSettings.prisma().find_first_or_raise(
                    where={"GuildId": guild.id}
                )
            ).SponsorblockFlag
        )


class SettingsView(BaseSettingsView):
    def __init__(self, author: discord.Member | discord.User, message: discord.Message):
        super().__init__(author, message)
        self.add_item(SettingsDropdown())

    @override
    def get_dropdown(self) -> SettingsDropdown:
        return cast(SettingsDropdown, self.children[0])


async def make(ctx: commands.Context[Nameless]):
    assert ctx.guild is not None
    guild_record = await PlayerSettings.prisma().find_first_or_raise(
        where={"GuildId": ctx.guild.id}
    )

    def toggle_flag(flag: int) -> str:
        return "Enable" if guild_record.SponsorblockFlag & flag == flag else "Disable"

    embed = (
        discord.Embed(
            title="SponsorBlock Settings",
            description="Select the setting you want to change.",
            color=discord.Color.orange(),
        )
        .add_field(
            name="Sponsor", value=toggle_flag(SponsorBlockFlags.SPONSOR), inline=False
        )
        .add_field(
            name="Selfpromo",
            value=toggle_flag(SponsorBlockFlags.SELFPROMO),
            inline=False,
        )
        .add_field(
            name="Preview", value=toggle_flag(SponsorBlockFlags.PREVIEW), inline=False
        )
        .add_field(
            name="Music Offtopic",
            value=toggle_flag(SponsorBlockFlags.MUSIC_OFFTOPIC),
            inline=False,
        )
    )
    message = await ctx.send(embed=embed)
    view = SettingsView(ctx.author, message)
    while True:
        await message.edit(view=view, embed=embed)

        if await view.wait():
            await message.edit(view=None)
            return

        selected_flag = view.get_dropdown().get_selected_flag()
        field_index = view.get_dropdown().get_field_index()
        embed._fields[field_index]["value"] = (
            "Disabled"
            if embed._fields[field_index]["value"] == "Enabled"
            else "Enabled"
        )
        guild_record.SponsorblockFlag ^= selected_flag
