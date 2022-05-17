import datetime
from dis import dis
from typing import Union

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from global_deps import crud_database

__all__ = ["ConfigCog"]


class ConfigCog(commands.Cog):
    def __init__(self, bot: discord.AutoShardedClient):
        self.bot = bot

    @commands.hybrid_group(fallback="get")
    @app_commands.guilds(*Config.GUILD_IDs)
    async def config(self, ctx: commands.Context):
        """View configured properties"""
        await ctx.defer()
        dbg, _ = crud_database.get_or_create_guild_record(ctx.guild)
        wc_chn = ctx.guild.get_channel(dbg.welcome_channel_id)
        gb_chn = ctx.guild.get_channel(dbg.goodbye_channel_id)

        embed = (
            discord.Embed(
                title="Configured properties",
                color=discord.Color.purple(),
                timestamp=datetime.datetime.now(),
            )
            .add_field(
                name="Welcome message",
                value=dbg.welcome_message if dbg.welcome_message else "Unset",
            )
            .add_field(
                name="Welcome message delivery channel",
                value=wc_chn.mention if wc_chn else "Unset",
            )
            .add_field(
                name="Welcome message delivery allowance", value=dbg.is_welcome_enabled
            )
            .add_field(
                name="Goodbye message",
                value=dbg.goodbye_message if dbg.goodbye_message else "Unset",
            )
            .add_field(
                name="Welcome message delivery channel",
                value=gb_chn.mention if gb_chn else "Unset",
            )
            .add_field(
                name="Welcome message delivery allowance", value=dbg.is_goodbye_enabled
            )
        )
        await ctx.send(embeds=[embed])

    @config.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(message="New welcome message")
    async def set_welcome_message(
        self,
        ctx: commands.Context,
        message: str,
    ):
        """Change welcome message"""
        await ctx.defer()
        dbg, _ = crud_database.get_or_create_guild_record(ctx.guild)
        dbg.welcome_message = message
        crud_database.save_changes(guild_record=dbg)
        await ctx.send("Done updating welcome message")

    @config.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(message="New goodbye message")
    async def set_goodbye_message(
        self,
        ctx: commands.Context,
        message: str,
    ):
        """Change goodbye message"""
        await ctx.defer()
        dbg, _ = crud_database.get_or_create_guild_record(ctx.guild)
        dbg.goodbye_message = message
        crud_database.save_changes(guild_record=dbg)
        await ctx.send("Done updating goodbye message")

    @config.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(dest_channel="Goodbye message delivery channel")
    async def set_goodbye_channel(
        self,
        ctx: commands.Context,
        dest_channel: Union[discord.TextChannel, discord.Thread],
    ):
        """Change goodbye message delivery channel"""
        await ctx.defer()
        dbg, _ = crud_database.get_or_create_guild_record(ctx.guild)
        dbg.goodbye_channel_id = dest_channel.id
        crud_database.save_changes(guild_record=dbg)
        await ctx.send(f"Done updating goodbye channel to {dest_channel.mention}")

    @config.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(dest_channel="Welcome message delivery channel")
    async def set_welcome_channel(
        self,
        ctx: commands.Context,
        dest_channel: Union[discord.TextChannel, discord.Thread],
    ):
        """Change welcome message delivery channel"""
        await ctx.defer()
        dbg, _ = crud_database.get_or_create_guild_record(ctx.guild)
        dbg.welcome_channel_id = dest_channel.id
        crud_database.save_changes(guild_record=dbg)
        await ctx.send(f"Done updating welcome channel to {dest_channel.mention}")

    @config.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle_welcome(self, ctx: commands.Context):
        """Toggle welcome message delivery allowance"""
        await ctx.defer()
        dbg, _ = crud_database.get_or_create_guild_record(ctx.guild)
        dbg.is_welcome_enabled = not dbg.is_welcome_enabled
        crud_database.save_changes(guild_record=dbg)
        await ctx.send(
            f"Welcome message delivery is now {'enabled' if dbg.is_welcome_enabled else 'disabled'}"
        )

    @config.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle_goodbye(self, ctx: commands.Context):
        """Toggle goodbye message delivery allowance"""
        await ctx.defer()
        dbg, _ = crud_database.get_or_create_guild_record(ctx.guild)
        dbg.is_goodbye_enabled = not dbg.is_goodbye_enabled
        crud_database.save_changes(guild_record=dbg)
        await ctx.send(
            f"Goodbye message delivery is now {'enabled' if dbg.is_welcome_enabled else 'disabled'}"
        )

    @config.command()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def view_placeholders(self, ctx: commands.Context):
        """View available placeholders"""
        await ctx.defer()
        placeholders = {
            "{guild}": "The name of the guild.\nAvailability: Welcome+Goodbye.",
            "{@user}": "Mention that user.\nAvailability: Welcome.",
            "{name}": "Display name of that member.\nAvailability: Welcome+Goodbye.",
            "{tag}": "The 4-digit after #.\nAvailability: Welcome+Goodbye.",
        }

        await ctx.send(
            "\n".join(f"**{key}**\n{value}\n" for key, value in placeholders.items())
        )
