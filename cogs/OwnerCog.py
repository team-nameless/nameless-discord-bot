import logging

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

    @commands.is_owner()
    @commands.hybrid_command()
    @app_commands.guilds(*Config.GUILD_IDs)
    @app_commands.describe(module_name="The Python-qualified module name")
    async def reload(self, ctx: commands.Context, module_name: str):
        """Reload a module"""
        await ctx.defer()

        try:
            await self.bot.reload_extension(module_name)
            await ctx.send(f"Done reloading {module_name}")
        except commands.ExtensionNotFound:
            await ctx.send(f"{module_name} was not found in the code")
        except commands.ExtensionNotLoaded:
            await ctx.send(f"{module_name} was not loaded before")

    @commands.is_owner()
    @commands.hybrid_command()
    @app_commands.guilds(*Config.GUILD_IDs)
    @app_commands.describe(module_name="The Python-qualified module name")
    async def load(self, ctx: commands.Context, module_name: str):
        """Load a module"""
        await ctx.defer()

        try:
            await self.bot.load_extension(module_name)
            await ctx.send(f"Done loading {module_name}")
        except commands.ExtensionNotFound:
            await ctx.send(f"{module_name} was not found in the code")
        except commands.ExtensionAlreadyLoaded:
            await ctx.send(f"{module_name} was loaded before")

    @commands.is_owner()
    @commands.hybrid_command()
    @app_commands.guilds(*Config.GUILD_IDs)
    @app_commands.describe(module_name="The Python-qualified module name")
    async def unload(self, ctx: commands.Context, module_name: str):
        """Unload a module"""
        await ctx.defer()

        try:
            await self.bot.unload_extension(module_name)
            await ctx.send(f"Done unloading {module_name}")
        except commands.ExtensionNotFound:
            await ctx.send(f"{module_name} was not found in the code")
        except commands.ExtensionNotLoaded:
            await ctx.send(f"{module_name} was not loaded before")


async def setup(bot: commands.AutoShardedBot):
    await bot.add_cog(OwnerCog(bot))
    logging.info(f"Cog of {__name__} added!")


async def teardown(bot: commands.AutoShardedBot):
    await bot.remove_cog("OwnerCog")
    logging.info(f"Cog of {__name__} removed!")
