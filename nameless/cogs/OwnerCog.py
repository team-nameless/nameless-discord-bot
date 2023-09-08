import contextlib
import datetime
import io
import logging
import re
import subprocess
import sys
import textwrap
import time

import discord
import discord.ui
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown

from nameless import Nameless, shared_vars
from nameless.customs import Autocomplete


__all__ = ["OwnerCog"]


class OwnerCog(commands.Cog):
    def __init__(self, bot: Nameless):
        self.bot = bot

    @commands.is_owner()
    @commands.hybrid_command()
    async def shutdown(self, ctx: commands.Context):
        """Shutdown the bot"""
        await ctx.send("Bye owo!")
        await self.bot.close()

    @commands.is_owner()
    @commands.hybrid_command()
    @app_commands.autocomplete(module_name=Autocomplete.module_complete)
    @app_commands.describe(module_name="The Python-qualified module name")
    async def reload(self, ctx: commands.Context, module_name: str):
        """Reload a module"""
        await ctx.defer()

        await self.bot.reload_extension(module_name)
        await ctx.send(f"Done reloading {module_name}")

    @commands.is_owner()
    @commands.hybrid_command()
    @app_commands.autocomplete(module_name=Autocomplete.load_module_complete)
    @app_commands.describe(module_name="The Python-qualified module name")
    async def load(self, ctx: commands.Context, module_name: str):
        """Load a module"""
        await ctx.defer()

        await self.bot.load_extension(module_name)
        shared_vars.loaded_cogs_list.append(module_name)
        shared_vars.unloaded_cogs_list.remove(module_name)

        await ctx.send(f"Done loading {module_name}")

    @commands.is_owner()
    @commands.hybrid_command()
    @app_commands.autocomplete(module_name=Autocomplete.module_complete)
    @app_commands.describe(module_name="The Python-qualified module name")
    async def unload(self, ctx: commands.Context, module_name: str):
        """Unload a module"""
        await ctx.defer()

        await self.bot.unload_extension(module_name)
        shared_vars.loaded_cogs_list.remove(module_name)
        shared_vars.unloaded_cogs_list.append(module_name)

        await ctx.send(f"Done unloading {module_name}")

    @commands.is_owner()
    @commands.hybrid_command()
    async def restart(self, ctx: commands.Context):
        """Restart the bot"""
        await ctx.defer()
        await ctx.send("See you soon!")
        logging.warning("Restarting using `%s %s`", sys.executable, " ".join(sys.argv))
        subprocess.run([sys.executable, *sys.argv], check=False)

    @commands.is_owner()
    @commands.hybrid_command()
    async def run_python_code(self, ctx: commands.Context, *, code: str):
        """Evaluate some pieces of Python code"""
        await ctx.defer()

        groups = re.search(r"```(?:python|py)?\n([\w\W\r\n]*)\n?```", code)

        if not groups:
            groups = re.search(r"`*([\w\W]*[^`])`*", code)

        code = groups.group(1) if groups else ""

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

                    await t["func"]()
                    stdout_result = f"{out.getvalue()}"
                    stderr_result = f"{err.getvalue()}"
        except RuntimeError as e:
            stderr_result = e

        end_time = time.time()

        stdout_result = escape_markdown(str(stdout_result))[:1000] if stdout_result else "Nothing in stdout"
        stderr_result = escape_markdown(str(stderr_result))[:1000] if stderr_result else "Nothing in stderr"

        embed = (
            discord.Embed(
                title=f"Python code evaluation result for {ctx.author}",
                description=f"**Source code**\n```python\n{code}\n```",
                timestamp=datetime.datetime.now(),
                color=discord.Color.orange(),
            )
            .add_field(name="stdout", value=f"```\n{stdout_result}\n```", inline=False)
            .add_field(name="stderr", value=f"```\n{stderr_result}\n```", inline=False)
            .add_field(name="Elapsed time", value=f"{round(end_time - start_time, 3)} second(s)", inline=False)
        )

        await pending_message.edit(content=None, embed=embed)

    @commands.is_owner()
    @commands.hybrid_command()
    async def refresh_command_list(self, ctx: commands.Context):
        """Refresh command list, mostly for deduplication"""
        await ctx.send("You should restart the bot after running this!")

        for guild in ctx.bot.guilds:
            ctx.bot.tree.clear_commands(guild=guild)

        ctx.bot.tree.clear_commands(guild=None)

        await ctx.send("Command cleaning done, you should restart me to update the new commands")


async def setup(bot: Nameless):
    await bot.add_cog(OwnerCog(bot))
    logging.info("%s cog added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog("OwnerCog")
    logging.warning("%s cog removed!", __name__)
