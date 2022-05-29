import datetime
import logging
from typing import Optional, List

import discord
import discord_together
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from discord_together.discordTogetherMain import defaultApplications

from config import Config

__all__ = ["GeneralCog"]


class GeneralCog(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot) -> None:
        self.bot = bot

    @commands.hybrid_command()
    @app_commands.guilds(*Config.GUILD_IDs)
    @app_commands.describe(
        target="Your desired activity", voice_channel="Target voice channel"
    )
    @app_commands.choices(
        target=[Choice(name=k, value=k) for k, _ in defaultApplications.items()]
    )
    async def create_activity(
        self,
        ctx: commands.Context,
        voice_channel: discord.VoiceChannel,
        target: str = "youtube",
    ):
        """Generate an embedded activity link"""

        msg = await ctx.send("Generating link")

        inv = await (
            await discord_together.DiscordTogether(  # noqa
                Config.TOKEN, debug=Config.LAB
            )
        ).create_link(voice_channel.id, target)

        await msg.edit(content=f"Here is your link: {inv}")

    @commands.hybrid_command()
    @app_commands.guilds(*Config.GUILD_IDs)
    @app_commands.describe(member="Target member, you by default")
    async def user(self, ctx: commands.Context, member: Optional[discord.Member]):
        """View someone's information"""
        await ctx.defer()

        member = member if member else ctx.author

        account_create_date = member.created_at
        join_date = member.joined_at
        flags = [
            flag.replace("_", " ").title() for flag, has in member.public_flags if has
        ]

        # should add to cache if possible
        mutual_guilds: List[str] = [
            guild.name for guild in ctx.bot.guilds if guild.get_member(member.id)
        ]

        embed = (
            discord.Embed(
                description=f"User ID: {member.id}",
                timestamp=datetime.datetime.now(),
                title=f"Something about {member}",
                color=discord.Color.orange(),
            )
            .set_thumbnail(url=member.avatar.url)
            .add_field(
                name="Account creation date",
                value=f"<t:{int(account_create_date.timestamp())}:R>",
            )
            .add_field(
                name="Membership date", value=f"<t:{int(join_date.timestamp())}:R>"
            )
            .add_field(name="Guild owner?", value=member.guild.owner == member)
            .add_field(name="Bot?", value=member.bot)
            .add_field(name="Badges", value=", ".join(flags) if flags else "None")
            .add_field(
                name="Mutual guilds with me",
                value=", ".join(mutual_guilds) if mutual_guilds else "None",
            )
        )

        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guilds(*Config.GUILD_IDs)
    async def guild(self, ctx: commands.Context):
        """View this guild's information"""
        await ctx.defer()

        guild = ctx.guild
        guild_create_date = guild.created_at
        members = guild.members

        bots_count = len([member for member in members if member.bot])
        humans_count = len([member for member in members if not member.bot])
        total_count = bots_count + humans_count
        public_threads_count = len(
            [thread for thread in guild.threads if not thread.is_private()]
        )
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
            .set_thumbnail(url=guild.banner.url if guild.banner else "")
            .add_field(
                name="Guild creation date",
                value=f"<t:{int(guild_create_date.timestamp())}:R>",
            )
            .add_field(
                name="Member(s)",
                value=f"Bot(s): {bots_count}\nHuman(s): {humans_count}\nTotal: {total_count}",
            )
            .add_field(
                name="Channel(s)",
                value=f"{len(guild.channels)} channel(s) - {public_threads_count} public thread(s)",
            )
            .add_field(name="Role(s) count", value=str(len(guild.roles)))
            .add_field(
                name="Pending event(s) count", value=f"{len(events)} pending event(s)"
            )
            .add_field(
                name="Boost(s)",
                value=f"{boosts_count} boost(s) from {boosters_count} booster(s) reaching lvl. {boost_lvl}"
                if is_boosted
                else "Not boosted",
            )
        )

        await ctx.send(embed=embed)


async def setup(bot: commands.AutoShardedBot):
    await bot.add_cog(GeneralCog(bot))
    logging.info(f"Cog of {__name__} added!")


async def teardown(bot: commands.AutoShardedBot):
    await bot.remove_cog("GeneralCog")
    logging.info(f"Cog of {__name__} removed!")
