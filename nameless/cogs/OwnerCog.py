import contextlib
import datetime
import io
import logging
import os
import re
import sys
import textwrap
import time

import discord
import discord.ui
from cogs.checks import BaseCheck
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown

from nameless import Nameless, shared_vars
from nameless.customs import Autocomplete

__all__ = ["OwnerCog"]


class OwnerCog(commands.Cog):
    def __init__(self, bot: Nameless):
        self.bot = bot

    @app_commands.command()
    @app_commands.guild_only()
    @BaseCheck.owns_the_bot()
    async def shutdown(self, interaction: discord.Interaction):
        """Shutdown the bot"""
        await interaction.response.defer()

        await interaction.followup.send("Bye owo!")
        await self.bot.close()

    @app_commands.command()
    @app_commands.guild_only()
    @BaseCheck.owns_the_bot()
    @app_commands.autocomplete(module_name=Autocomplete.module_complete)
    @app_commands.describe(module_name="The Python-qualified module name")
    async def reload(self, interaction: discord.Interaction, module_name: str):
        """Reload a module"""
        await interaction.response.defer()

        await self.bot.reload_extension(module_name)
        await interaction.followup.send(f"Done reloading {module_name}")

    @app_commands.command()
    @app_commands.guild_only()
    @BaseCheck.owns_the_bot()
    @app_commands.autocomplete(module_name=Autocomplete.load_module_complete)
    @app_commands.describe(module_name="The Python-qualified module name")
    async def load(self, interaction: discord.Interaction, module_name: str):
        """Load a module"""
        await interaction.response.defer()

        await self.bot.load_extension(module_name)
        shared_vars.loaded_cogs_list.append(module_name)
        shared_vars.unloaded_cogs_list.remove(module_name)

        await interaction.followup.send(f"Done loading {module_name}")

    @app_commands.command()
    @app_commands.guild_only()
    @BaseCheck.owns_the_bot()
    @app_commands.autocomplete(module_name=Autocomplete.module_complete)
    @app_commands.describe(module_name="The Python-qualified module name")
    async def unload(self, interaction: discord.Interaction, module_name: str):
        """Unload a module"""
        await interaction.response.defer()

        await self.bot.unload_extension(module_name)
        shared_vars.loaded_cogs_list.remove(module_name)
        shared_vars.unloaded_cogs_list.append(module_name)

        await interaction.followup.send(f"Done unloading {module_name}")

    @app_commands.command()
    @app_commands.guild_only()
    @BaseCheck.owns_the_bot()
    async def restart(self, interaction: discord.Interaction):
        """Restart the bot"""
        await interaction.response.defer()
        await interaction.followup.send("See you soon!")

        os.execl(sys.executable, sys.executable, *sys.argv)

    @app_commands.command()
    @app_commands.guild_only()
    @BaseCheck.owns_the_bot()
    async def run_python_code(self, interaction: discord.Interaction, *, code: str):
        """Evaluate some pieces of Python code"""
        await interaction.response.defer()

        groups = re.search(r"```(?:python|py)?\n([\w\W\r\n]*)\n?```", code)

        if not groups:
            groups = re.search(r"`*([\w\W]*[^`])`*", code)

        code = groups.group(1) if groups else ""

        if not code:
            await interaction.followup.send("No code to run")
            return

        pending_message = await interaction.followup.send("Running...")

        start_time = time.time()
        stdout_result, stderr_result = None, None

        try:
            with contextlib.redirect_stdout(out := io.StringIO()), contextlib.redirect_stderr(err := io.StringIO()):
                exec(
                    f"async def func():\n{textwrap.indent(code, '    ')}",
                    (
                        t := {
                            "discord": discord,
                            "commands": commands,
                            "bot": self.bot,
                            "interaction": interaction,
                            "channel": interaction.channel,
                            "user": interaction.user,
                            "guild": interaction.guild,
                            "message": interaction.message,
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
                title=f"Python code evaluation result for {interaction.user}",
                description=f"**Source code**\n```python\n{code}\n```",
                timestamp=datetime.datetime.now(),
                color=discord.Color.orange(),
            )
            .add_field(name="stdout", value=f"```\n{stdout_result}\n```", inline=False)
            .add_field(name="stderr", value=f"```\n{stderr_result}\n```", inline=False)
            .add_field(name="Elapsed time", value=f"{round(end_time - start_time, 3)} second(s)", inline=False)
        )

        await pending_message.edit(content=None, embed=embed)

    @app_commands.command()
    @app_commands.guild_only()
    @BaseCheck.owns_the_bot()
    async def refresh_command_list(self, interaction: discord.Interaction):
        """Refresh command list, mostly for deduplication"""
        await interaction.response.defer()

        for guild in interaction.client.guilds:
            self.bot.tree.clear_commands(guild=guild)

        self.bot.tree.clear_commands(guild=None)

        await interaction.followup.send("Command cleaning done, you should restart me to update the new commands")


async def setup(bot: Nameless):
    await bot.add_cog(OwnerCog(bot))
    logging.info("%s cog added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog("OwnerCog")
    logging.warning("%s cog removed!", __name__)
