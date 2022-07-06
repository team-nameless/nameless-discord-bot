import logging
import os
import subprocess
import sys

from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from NamelessConfig import NamelessConfig
from nameless import shared_vars

__all__ = ["OwnerCog"]
cogs_list = list(
    "nameless.cogs." + z.replace(".py", "")
    for z in filter(shared_vars.cogs_regex.match, os.listdir("cogs"))
)


class OwnerCog(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot

    @commands.is_owner()
    @commands.hybrid_command()
    @app_commands.guilds(*getattr(NamelessConfig, "GUILD_IDs", []))
    async def shutdown(self, ctx: commands.Context):
        """Shutdown the bot"""
        await ctx.send("Bye owo!")
        await self.bot.close()

    @commands.is_owner()
    @commands.hybrid_command()
    @app_commands.guilds(*getattr(NamelessConfig, "GUILD_IDs", []))
    @app_commands.choices(module_name=[Choice(name=c, value=c) for c in cogs_list])
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
    @app_commands.guilds(*getattr(NamelessConfig, "GUILD_IDs", []))
    @app_commands.choices(module_name=[Choice(name=c, value=c) for c in cogs_list])
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
    @app_commands.guilds(*getattr(NamelessConfig, "GUILD_IDs", []))
    @app_commands.choices(module_name=[Choice(name=c, value=c) for c in cogs_list])
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

    @commands.is_owner()
    @commands.hybrid_command()
    @app_commands.guilds(*getattr(NamelessConfig, "GUILD_IDs", []))
    async def restart(self, ctx: commands.Context):
        """Restart the bot"""
        await ctx.defer()
        await ctx.send("See you soon!")
        logging.warning("Restarting using [%s %s]", sys.executable, " ".join(sys.argv))
        subprocess.run([sys.executable, *sys.argv], check=False)


async def setup(bot: commands.AutoShardedBot):
    await bot.add_cog(OwnerCog(bot))
    logging.info("Cog of %s added!", __name__)


async def teardown(bot: commands.AutoShardedBot):
    await bot.remove_cog("OwnerCog")
    logging.warning("Cog of %s removed!", __name__)
