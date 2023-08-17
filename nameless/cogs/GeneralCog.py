import datetime
import logging
from platform import python_implementation, python_version
from typing import List, Optional, Union

import discord
from discord import NotFound, app_commands
from discord.ext import commands

from nameless import Nameless, shared_vars
from NamelessConfig import NamelessConfig


__all__ = ["GeneralCog"]


class GeneralCog(commands.Cog):
    def __init__(self, bot: Nameless) -> None:
        super().__init__()
        self.bot = bot

    @app_commands.command()
    @app_commands.describe(member="Target member to view, you as default.")
    async def view_user(
        self,
        interaction: discord.Interaction,
        member: Optional[Union[discord.Member, discord.User]],
    ):
        """View someone's information"""
        await interaction.response.defer()

        member = member if member else interaction.user

        account_create_date = member.created_at
        join_date = member.joined_at  # pyright: ignore

        flags = [flag.replace("_", " ").title() for flag, has in member.public_flags if has]

        mutual_guilds: List[str] = [g.name for g in interaction.user.mutual_guilds]

        embed: discord.Embed = (
            discord.Embed(
                description=f"User ID: {member.id}",
                timestamp=datetime.datetime.now(),
                title=f"Something about @{member.display_name}"
                + (" (👑)" if isinstance(member, discord.Member) and member.guild.owner == member else "")
                + (" (🤖)" if member.bot else ""),
                color=discord.Color.orange(),
            )
            .set_thumbnail(url=member.display_avatar.url)
            .add_field(
                name="Created since",
                value=f"<t:{int(account_create_date.timestamp())}:R> (<t:{int(account_create_date.timestamp())}:f>)",
            )
            .add_field(
                name="Membership since",
                value=f"<t:{int(join_date.timestamp())}:R> (<t:{int(join_date.timestamp())}:f>)",  # pyright: ignore
            )
            .add_field(name="Badges", value=", ".join(flags) if flags else "None", inline=False)
            .add_field(
                name="Mutual guilds with you",
                value=", ".join(mutual_guilds) if mutual_guilds else "None",
            )
        )

        await interaction.followup.send(embed=embed)

    @app_commands.command()
    @app_commands.guild_only()
    async def view_guild(self, interaction: discord.Interaction):
        """View this guild's information"""
        await interaction.response.defer()

        guild = interaction.guild

        guild_create_date = guild.created_at
        members = guild.members

        bots_count = len([member for member in members if member.bot])
        humans_count = len([member for member in members if not member.bot])
        total_count = bots_count + humans_count
        public_threads_count = len([thread for thread in guild.threads if not thread.is_private()])
        events = guild.scheduled_events
        boosters_count = len(guild.premium_subscribers)
        boosts_count = guild.premium_subscription_count
        boost_lvl = guild.premium_tier
        is_boosted = boosts_count > 0

        embed = (
            discord.Embed(
                description=f"Guild ID: {guild.id} - Owner {guild.owner} - Shard #{guild.shard_id}",
                timestamp=datetime.datetime.now(),
                title=f"Something about '{guild.name}'",
                color=discord.Color.orange(),
            )
            .set_thumbnail(url=guild.icon.url if guild.icon else "")
            .add_field(
                name="Creation date",
                value=f"<t:{int(guild_create_date.timestamp())}:R> <t:{int(guild_create_date.timestamp())}:f>",
            )
            .add_field(
                name="Members",
                value=f"Bot(s): {bots_count}\n" f"Human(s): {humans_count}\n" f"Total: {total_count}",
            )
            .add_field(
                name="Channels",
                value=f"{len(guild.channels)} channel(s) - {public_threads_count} public thread(s)",
            )
            .add_field(name="Roles", value=str(len(guild.roles)))
            .add_field(name="Events", value=f"{len(events)} pending event(s)")
            .add_field(
                name="Boosts",
                value=f"{boosts_count} boost(s) from {boosters_count} booster(s) - Level {boost_lvl}"
                if is_boosted
                else "Not boosted",
            )
            .set_image(url=guild.banner.url if guild.banner else "")
        )

        await interaction.followup.send(embed=embed)

    @app_commands.command()
    async def view_the_bot(self, interaction: discord.Interaction):
        """View my information"""
        await interaction.response.defer()

        servers_count = len(interaction.client.guilds)
        total_members_count = sum(len(guild.members) for guild in interaction.client.guilds)
        uptime = int(shared_vars.start_time.timestamp())
        bot_inv = (
            f"https://discord.com/api/oauth2/authorize"
            f"?client_id={interaction.client.user.id}"
            f"&permissions={shared_vars.needed_permissions.value}"
            f"&scope=bot%20applications.commands"
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
                title="Something about me!",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now(),
                description=NamelessConfig.__description__.replace("{github_link}", github_link),
            )
            .set_thumbnail(url=interaction.client.user.display_avatar.url)
            .add_field(name="Servers count", value=f"{servers_count}")
            .add_field(name="Members count", value=f"{total_members_count}")
            .add_field(name="Last launch/Uptime", value=f"<t:{uptime}:R>")
            .add_field(
                name="Bot version",
                value=NamelessConfig.__version__,
            )
            .add_field(name="Library version", value=f"discord.py v{discord.__version__}")
            .add_field(
                name="Python version",
                value=f"{python_implementation()} {python_version()}",
            )
            .add_field(name="Commands count", value=f"{len(list(self.bot.walk_commands()))}")
            .add_field(
                name="Invite link",
                value=f"[Click this]({bot_inv}) or click me then 'Add to Server'"
                if interaction.client.application.bot_public
                else "N/A",
            )
            .add_field(
                name="Support server",
                value=f"[Click me!]({support_inv})" if support_inv else "N/A",
            )
        )

        await interaction.followup.send(embed=embed)


async def setup(bot: Nameless):
    await bot.add_cog(GeneralCog(bot))
    logging.info("%s cog added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog("GeneralCog")
    logging.warning("%s cog removed!", __name__)
