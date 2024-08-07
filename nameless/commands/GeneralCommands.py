import datetime
import logging
from platform import python_implementation, python_version
from typing import cast

import discord
from discord import NotFound, app_commands
from discord.ext import commands

from nameless import Nameless
import nameless.runtime_config as runtime_config
from NamelessConfig import NamelessConfig

__all__ = ["GeneralCommands"]


class GeneralCommands(commands.Cog):
    def __init__(self, bot: Nameless) -> None:
        super().__init__()
        self.bot = bot

    @app_commands.command()
    @app_commands.describe(member="Target member, default to you.")
    async def user(self, interaction: discord.Interaction, member: discord.Member | None):
        """View someone's information."""
        await interaction.response.defer()

        member = member if member else cast(discord.Member, interaction.user)

        account_create_date = member.created_at
        join_date = member.joined_at

        flags = [flag.replace("_", " ").title() for flag, has in member.public_flags if has]
        embed: discord.Embed = (
            discord.Embed(
                description=f"ℹ️ User ID: `{member.id}` - Public handle: `@{member.name}`",
                timestamp=datetime.datetime.now(),
                title=f"@{member.display_name} - "
                + ("[👑]" if isinstance(member, discord.Member) and member.guild.owner == member else "[😎]")
                + ("[🤖]" if member.bot else ""),
                color=discord.Color.orange(),
            )
            .set_thumbnail(url=member.display_avatar.url)
            .add_field(name="📆 Account created since", value=f"<t:{int(account_create_date.timestamp())}:R>")
            .add_field(name="🤝 Membership since", value=f"<t:{int(join_date.timestamp())}:R>")
            .add_field(name="🌟 Badges", value=", ".join(flags) if flags else "None", inline=False)
        )

        await interaction.followup.send(embed=embed)

    @app_commands.command()
    @app_commands.guild_only()
    async def guild(self, interaction: discord.Interaction):
        """View this guild's information"""
        await interaction.response.defer()

        guild = interaction.guild

        guild_create_date = guild.created_at
        members = guild.members

        bots_count = len([member for member in members if member.bot])
        humans_count = len([member for member in members if not member.bot])
        total_count = bots_count + humans_count
        public_threads_count = len([thread for thread in guild.threads])
        events = guild.scheduled_events
        boosts_count = guild.premium_subscription_count

        embed = (
            discord.Embed(
                description=f"ℹ️ Guild ID: `{guild.id}` - Owner: {guild.owner.mention}",
                timestamp=datetime.datetime.now(),
                title=guild.name,
                color=discord.Color.orange(),
            )
            .set_thumbnail(url=guild.icon.url if guild.icon else "")
            .add_field(
                name="⏰ Creation date",
                value=f"<t:{int(guild_create_date.timestamp())}:R> (<t:{int(guild_create_date.timestamp())}:f>)",
                inline=False,
            )
            .add_field(name=f"👋 Headcount: {total_count}", value=f"BOT: {bots_count}, Human: {humans_count}")
            .add_field(name="💬 Channels", value=f"{len(guild.channels)} channel(s) - {public_threads_count} thread(s)")
            .add_field(name="⭐ Roles", value=f"{len(guild.roles)}")
            .add_field(name="📆 Events", value=f"{len(events)}")
            .add_field(name="⬆️ Boosts", value=f"{boosts_count} boost(s)")
            .set_image(url=guild.banner.url if guild.banner else "")
        )

        await interaction.followup.send(embed=embed)

    @app_commands.command()
    async def the_bot(self, interaction: discord.Interaction):
        """So, you would like to know me?"""
        await interaction.response.defer()

        servers_count = len(interaction.client.guilds)
        total_members_count = sum(len(guild.members) for guild in interaction.client.guilds)
        uptime = int(runtime_config.launch_time.timestamp())
        bot_inv = discord.utils.oauth_url(
            interaction.client.user.id, permissions=self.bot.needed_permissions, scopes=["bot", "applications.commands"]
        )

        nameless_meta = NamelessConfig.META
        github_link = nameless_meta.SOURCE_CODE_URL
        support_inv = ""

        try:
            if sp_url := nameless_meta.SUPPORT_SERVER_URL:
                inv = await self.bot.fetch_invite(sp_url)
                support_inv = inv.url
        except NotFound:
            pass

        embed: discord.Embed = (
            discord.Embed(
                title="So... you would like to know me, right 😳",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now(),
                description="*Not much thing, I know.*",
            )
            .set_thumbnail(url=interaction.client.user.display_avatar.url)
            .add_field(
                name="⭐ Biography",
                value=NamelessConfig.__description__.replace("{github_link}", github_link),
                inline=False,
            )
            .add_field(
                name="🫡 Service status",
                value=f"Serving {servers_count} servers for a total of {total_members_count} users.",
                inline=False,
            )
            .add_field(name="👋 Online since", value=f"<t:{uptime}:F> (UTC+0)", inline=False)
            .add_field(name="ℹ️ Version", value=NamelessConfig.__version__)
            .add_field(
                name="💻 Runtime",
                value=f"**discord.py {discord.__version__}** on **{python_implementation()} {python_version()}**",
            )
        )

        buttons = discord.ui.View()

        if interaction.client.application.bot_public:
            buttons.add_item(
                discord.ui.Button(label="Invite me!", style=discord.ButtonStyle.url, url=bot_inv, emoji="😳")
            )

        if support_inv:
            buttons.add_item(
                discord.ui.Button(label="Support server", style=discord.ButtonStyle.url, url=support_inv, emoji="🤝")
            )

        buttons.add_item(
            discord.ui.Button(label="Source code", style=discord.ButtonStyle.url, url=github_link, emoji="📃")
        )

        await interaction.followup.send(embed=embed, view=buttons)


async def setup(bot: Nameless):
    await bot.add_cog(GeneralCommands(bot))
    logging.info("%s cog added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog(GeneralCommands.__cog_name__)
    logging.warning("%s cog removed!", __name__)
