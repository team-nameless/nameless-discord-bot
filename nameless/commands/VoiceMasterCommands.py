import logging
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

import nameless
from nameless import Nameless
from nameless.database import CRUD

__all__ = ["VoiceMasterCommands"]


class VoiceMasterCommands(commands.GroupCog, name="voicemaster"):
    def __init__(self, bot: nameless.Nameless):
        super().__init__()
        self.bot = bot

        # user_id -> voice_channel_id
        self.channel_track: dict[int, int] = {}

        # voice_channel_id -> user_id
        self.channel_owner: dict[int, int] = {}

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        db_guild = CRUD.get_or_create_guild_record(member.guild)

        if db_guild.voice_room_channel_id == 0:
            return

        is_a_join = before.channel is None and after.channel is not None
        is_a_leave = before.channel is not None and after.channel is None

        # If join to master channel, create the voice channel for that person, or just put them there.
        if is_a_join and after.channel.id == db_guild.voice_room_channel_id:
            target_vc_id = self.channel_track.get(member.id, None)
            vc: discord.VoiceChannel

            if target_vc_id is None:
                current_category = after.channel.category
                current_position = after.channel.position
                vc = await after.channel.guild.create_voice_channel(
                    f"@{member.name}'s Voice", category=current_category, position=current_position + 1
                )
                self.channel_track[member.id] = vc.id
                self.channel_owner[vc.id] = member.id
            else:
                vc = cast(discord.VoiceChannel, after.channel.guild.get_channel(target_vc_id))

            await member.move_to(vc)

        # If the left channel has no member, and is owned by someone, revoke.
        if (
            is_a_leave
            # Did d.py had a bug???
            and len(before.channel.members) == 0
            and self.channel_owner.get(before.channel.id, None) is not None
        ):
            vc = cast(discord.VoiceChannel, before.channel.guild.get_channel(before.channel.id))
            await vc.delete()

            del self.channel_track[member.id]
            del self.channel_owner[before.channel.id]

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def create_channel(self, interaction: discord.Interaction):
        """Create and set voice room master channel."""
        await interaction.response.defer()

        vc = await interaction.guild.create_voice_channel("Create your own VC!")

        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        db_guild.voice_room_channel_id = vc.id

        await interaction.followup.send(f"Done creating voice room: {vc.mention}. You can put it anywhere you like!")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(dest_channel="Target voice channel to watch for changes.")
    async def set_channel(self, interaction: discord.Interaction, dest_channel: discord.VoiceChannel):
        """Set voice room master channel."""
        await interaction.response.defer()
        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        db_guild.voice_room_channel_id = dest_channel.id

        await interaction.followup.send(f"Done setting voice room to {dest_channel.mention}")


async def setup(bot: Nameless):
    await bot.add_cog(VoiceMasterCommands(bot))
    logging.info("%s added!", __name__)


async def teardown(bot: nameless.Nameless):
    await bot.remove_cog(VoiceMasterCommands.__cog_name__)
    logging.warning("%s removed!", __name__)
