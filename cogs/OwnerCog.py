from discord import app_commands
from discord.ext import commands

from config import Config

__all__ = ["OwnerCog"]


class OwnerCog(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot

    @commands.is_owner()
    @commands.hybrid_command()
    @app_commands.guilds(*Config.GUILD_IDs)
    async def shutdown(self, ctx: commands.Context):
        """Shutdown the bot"""
        await ctx.send("Bye owo!")
        await self.bot.close()
