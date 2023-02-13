import contextlib
import datetime
import io
import logging
import os
import re
import subprocess
import sys
import textwrap
import time

import discord
import discord.ui
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from discord.utils import escape_markdown

from nameless import Nameless, shared_vars
from NamelessConfig import NamelessConfig


__all__ = ["OwnerCog"]

cogs_list = list(
    "nameless.cogs." + z.replace(".py", "")
    for z in filter(shared_vars.cogs_regex.match, os.listdir(f"{os.path.dirname(__file__)}"))
)


class OwnerCog(commands.Cog):
    def __init__(self, bot: Nameless):
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
        logging.warning("Restarting using `%s %s`", sys.executable, " ".join(sys.argv))
        subprocess.run([sys.executable, *sys.argv], check=False)

    @commands.is_owner()
    @commands.hybrid_command(name="eval")
    @app_commands.guilds(*getattr(NamelessConfig, "GUILD_IDs", []))
    async def _eval(self, ctx: commands.Context, *, code: str):
        """Evaluate some pieces of Python code"""
        await ctx.defer()

        groups = re.search(r"```(?:python|py)?\n([\w\W\r\n]*)\n?```", code)

        if not groups:
            groups = re.search(r"`*([\w\W]*[^`])`*", code)

        code = groups.group(1) if groups else ""
        returns = ""

        if not code:
            await ctx.send("No code to run")
            return

        pending_message = await ctx.send("Running...")

        start_time = time.time()
        stdout_result, stderr_result = None, None

        try:
            with contextlib.redirect_stdout(out := io.StringIO()):
                with contextlib.redirect_stderr(err := io.StringIO()):
                    exec(
                        f"async def func():\n{textwrap.indent(code, '    ')}",
                        (
                            t := {
                                "discord": discord,
                                "commands": commands,
                                "bot": self.bot,
                                "ctx": ctx,
                                "channel": ctx.channel,
                                "author": ctx.author,
                                "guild": ctx.guild,
                                "message": ctx.message,
                            }
                        ),
                    )

                    returns = await t["func"]()
                    stdout_result = f"{out.getvalue()}"
                    stderr_result = f"{err.getvalue()}"
        except RuntimeError as e:
            stderr_result = e

        end_time = time.time()

        stdout_result = escape_markdown(str(stdout_result))[:1000] if stdout_result else "Nothing in stdout"
        stderr_result = escape_markdown(str(stderr_result))[:1000] if stderr_result else "Nothing in stderr"
        returns = escape_markdown(str(returns))[:1000] if returns else "No returned value"

        embed = (
            discord.Embed(
                title=f"Python code evaluation result for {ctx.author}",
                description=f"**Source code**\n```python\n{code}\n```",
                timestamp=datetime.datetime.now(),
                color=discord.Color.orange(),
            )
            .add_field(name="stdout", value=f"```\n{stdout_result}\n```", inline=False)
            .add_field(name="stderr", value=f"```\n{stderr_result}\n```", inline=False)
            .add_field(name="Return value", value=f"```\n{returns}\n```", inline=False)
            .add_field(name="Elapsed time", value=f"{round(end_time - start_time, 3)} second(s)", inline=False)
        )

        await pending_message.edit(content=None, embed=embed)


async def setup(bot: Nameless):
    await bot.add_cog(OwnerCog(bot))
    logging.info("Cog of %s added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog("OwnerCog")
    logging.warning("Cog of %s removed!", __name__)
