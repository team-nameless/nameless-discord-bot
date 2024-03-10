import contextlib
import datetime
import io
import logging
import os
import sys
import textwrap
import time

import discord
import discord.ui
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown

from nameless import Nameless
from nameless.cogs.checks import BaseCheck
from nameless.customs import shared_variables
from nameless.customs.ui_kit import NamelessModal

__all__ = ["OwnerCog"]


class OwnerCog(commands.Cog):
    def __init__(self, bot: Nameless):
        self.bot = bot

    async def pending_module_autocomplete(self, _: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """An autocomplete for pending (not loaded) modules."""
        choices = shared_variables.rejected_modules
        return [
            app_commands.Choice(name=choice, value=choice) for choice in choices if current.lower() in choice.lower()
        ]

    async def available_module_autocomplete(
        self, _: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """An autocomplete for available (loaded) modules."""
        choices = shared_variables.loaded_modules
        return [
            app_commands.Choice(name=choice, value=choice) for choice in choices if current.lower() in choice.lower()
        ]

    @app_commands.command()
    @app_commands.guild_only()
    @BaseCheck.owns_the_bot()
    async def shutdown(self, interaction: discord.Interaction):
        """Shutdown the bot."""
        await interaction.response.defer()

        await interaction.followup.send("Bye owo!")
        await self.bot.close()

    @app_commands.command()
    @app_commands.guild_only()
    @BaseCheck.owns_the_bot()
    @app_commands.autocomplete(module_name=available_module_autocomplete)
    @app_commands.describe(module_name="The Python-qualified module name")
    async def reload_module(self, interaction: discord.Interaction, module_name: str):
        """Reload a module"""
        await interaction.response.defer()

        await self.bot.reload_extension(module_name)
        await interaction.followup.send(f"Done reloading {module_name}")

    @app_commands.command()
    @app_commands.guild_only()
    @BaseCheck.owns_the_bot()
    @app_commands.autocomplete(module_name=pending_module_autocomplete)
    @app_commands.describe(module_name="The Python-qualified module name")
    async def load_module(self, interaction: discord.Interaction, module_name: str):
        """Load a module."""
        await interaction.response.defer()

        await self.bot.load_extension(module_name)
        shared_variables.loaded_modules.append(module_name)
        shared_variables.rejected_modules.remove(module_name)

        await interaction.followup.send(f"Done loading {module_name}")

    @app_commands.command()
    @app_commands.guild_only()
    @BaseCheck.owns_the_bot()
    @app_commands.autocomplete(module_name=available_module_autocomplete)
    @app_commands.describe(module_name="The Python-qualified module name")
    async def eject_module(self, interaction: discord.Interaction, module_name: str):
        """Eject a module."""
        await interaction.response.defer()

        await self.bot.unload_extension(module_name)
        shared_variables.loaded_modules.remove(module_name)
        shared_variables.rejected_modules.append(module_name)

        await interaction.followup.send(f"Done unloading {module_name}")

    @app_commands.command()
    @app_commands.guild_only()
    @BaseCheck.owns_the_bot()
    async def restart(self, interaction: discord.Interaction):
        """Restart the bot."""
        await interaction.response.defer()
        await interaction.followup.send("See you soon!")

        os.execl(sys.executable, sys.executable, *sys.argv)

    @app_commands.command()
    @app_commands.guild_only()
    @BaseCheck.owns_the_bot()
    async def run_python_code(self, interaction: discord.Interaction):
        """Evaluate Python code."""
        # await interaction.response.defer()

        modal = NamelessModal(title="Python code", initial_text="print('Hello world!')")
        modal.text.label = "Python code"
        modal.text.required = True

        await interaction.response.send_modal(modal)
        await modal.wait()

        code = modal.text.value

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
            .add_field(name="Elapsed time", value=f"{round(end_time - start_time, 5)} second(s)", inline=False)
        )

        await interaction.followup.send(embed=embed)

    @app_commands.command()
    @app_commands.guild_only()
    @BaseCheck.owns_the_bot()
    async def refresh_command_list(self, interaction: discord.Interaction):
        """Refresh command list, mostly for deduplication. Should take a long time."""
        await interaction.response.defer()

        for guild in interaction.client.guilds:
            self.bot.tree.clear_commands(guild=guild)
            await self.bot.tree.sync(guild=guild)

        self.bot.tree.clear_commands(guild=None)
        await self.bot.tree.sync(guild=None)

        await interaction.followup.send("Command cleaning done, you should restart me to update the new commands")


async def setup(bot: Nameless):
    await bot.add_cog(OwnerCog(bot))
    logging.info("%s cog added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog(OwnerCog.__cog_name__)
    logging.warning("%s cog removed!", __name__)
