import discord
import discord_together
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from discord_together.discordTogetherMain import defaultApplications

from config import Config

__all__ = ["ActivityCog"]


class ActivityCog(commands.Cog):
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
    async def activity(
        self,
        ctx: commands.Context,
        voice_channel: discord.VoiceChannel,
        target: str = "youtube",
    ):
        """Generate an embedded activity link"""

        msg = await ctx.send("Generating link")

        inv = await (
            await discord_together.DiscordTogether(Config.TOKEN, debug=Config.LAB)
        ).create_link(voice_channel.id, target)

        await msg.edit(content=f"Here is your link: {inv}")
