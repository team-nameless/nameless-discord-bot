import datetime
import logging
from typing import Union

import discord
from discord import app_commands
from discord.ext import commands

import nameless
from nameless.cogs.checks import BaseCheck
from nameless.shared_vars import crud_database
from nameless.ui_kit import GreeterMessageModal


__all__ = ["ConfigCog"]


class ConfigCog(commands.GroupCog, name="config"):
    def __init__(self, bot: nameless.Nameless):
        super().__init__()
        self.bot = bot

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def view(self, interaction: discord.Interaction):
        """View configured properties"""
        await interaction.response.defer()

        db_guild = crud_database.get_or_create_guild_record(interaction.guild)

        wc_chn = interaction.guild.get_channel(db_guild.welcome_channel_id)  # pyright: ignore
        gb_chn = interaction.guild.get_channel(db_guild.goodbye_channel_id)  # pyright: ignore
        mute_role = interaction.guild.get_role(db_guild.mute_role_id)  # pyright: ignore
        reaction = [":x:", ":white_check_mark:"]
        dm = db_guild.is_dm_preferred

        embed: discord.Embed = (
            discord.Embed(
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now(),
            )
            .set_thumbnail(url=interaction.guild.icon.url)
            .set_author(icon_url=interaction.client.user.display_avatar.url, name="Configured properties")
        )

        embed.add_field(
            name=":star: Greeters",
            value="```\n"
            "These are the settings related to greeters such as welcome/goodbye setup, BOTs "
            "checks, fail fast to DM if available, etc. You should use '/config placeholders' in "
            "addition to the setup process."
            "\n```",
            inline=False,
        ).add_field(
            name=f"Welcome message {reaction[db_guild.is_welcome_enabled]}",
            value=f"**[Destination]** {wc_chn.mention if wc_chn and not dm else 'DM' if dm else 'Nowhere'}\n"
            "**[Content]**\n" + db_guild.welcome_message
            if db_guild.welcome_message
            else "Unset",
        ).add_field(
            name=f"Goodbye message {reaction[db_guild.is_goodbye_enabled]}",
            value=f"**[Destination]** {gb_chn.mention if gb_chn and not dm else 'DM' if dm else 'Nowhere'}\n"
            "**[Content]**\n" + db_guild.goodbye_message
            if db_guild.goodbye_message
            else "Unset",
        ).add_field(
            name="Greeting to BOTs", value=db_guild.is_bot_greeting_enabled, inline=False
        )

        embed.add_field(
            name=":police_officer: Server utilities",
            value="```\n"
            "These are the settings related to server utilities such as using native 'Timeout' "
            "in replace for traditional 'Mute role', ... "
            "\n```",
            inline=False,
        ).add_field(name="Use native timeout feature", value=db_guild.is_timeout_preferred, inline=False).add_field(
            name="Max warning count", value=db_guild.max_warn_count
        ).add_field(
            name="Mute role", value=mute_role.mention if mute_role else "Unset"
        )

        await interaction.followup.send(embeds=[embed])

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(edit_text="Whether you want to edit on the old message.")
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def set_welcome_message(self, interaction: discord.Interaction, edit_text: bool = True):
        """Change greeter welcome message"""
        db_guild = crud_database.get_or_create_guild_record(interaction.guild)

        modal = GreeterMessageModal(db_guild.welcome_message if edit_text else None)
        modal.text.label = "Greeter welcome text"

        await interaction.response.send_modal(modal)
        await modal.wait()

        db_guild.welcome_message = modal.text.value
        crud_database.save_changes()

        await interaction.followup.send("Updated the new welcome message successfully!")
        await interaction.followup.send(f"Your new welcome text:\n\n{db_guild.welcome_message}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(edit_text="Whether you want to edit on the old message.")
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def set_goodbye_message(self, interaction: discord.Interaction, edit_text: bool = True):
        """Change goodbye message"""
        db_guild = crud_database.get_or_create_guild_record(interaction.guild)

        modal = GreeterMessageModal(db_guild.goodbye_message if edit_text else None)
        modal.text.label = "Greeter goodbye text"

        await interaction.response.send_modal(modal)
        await modal.wait()

        db_guild.goodbye_message = modal.text.value
        crud_database.save_changes()

        await interaction.followup.send("Updated the new goodbye message successfully!")
        await interaction.followup.send(f"Your new goodbye text:\n\n{db_guild.goodbye_message}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(dest_channel="Goodbye message delivery channel")
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def set_goodbye_channel(
        self,
        interaction: discord.Interaction,
        dest_channel: Union[discord.TextChannel, discord.Thread],
    ):
        """Change goodbye message delivery channel"""
        await interaction.response.defer()
        db_guild = crud_database.get_or_create_guild_record(interaction.guild)
        db_guild.goodbye_channel_id = dest_channel.id
        await interaction.followup.send(f"Done updating goodbye channel to {dest_channel.mention}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(dest_channel="Welcome message delivery channel")
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def set_welcome_channel(
        self,
        interaction: discord.Interaction,
        dest_channel: Union[discord.TextChannel, discord.Thread],
    ):
        """Change welcome message delivery channel"""
        await interaction.response.defer()
        db_guild = crud_database.get_or_create_guild_record(interaction.guild)
        db_guild.welcome_channel_id = dest_channel.id
        await interaction.followup.send(f"Done updating welcome channel to {dest_channel.mention}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def toggle_welcome(self, interaction: discord.Interaction):
        """Toggle welcome message delivery allowance"""
        await interaction.response.defer()
        db_guild = crud_database.get_or_create_guild_record(interaction.guild)
        db_guild.is_welcome_enabled = not db_guild.is_welcome_enabled
        await interaction.followup.send(f"Welcome message delivery: {'on' if db_guild.is_welcome_enabled else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def toggle_goodbye(self, interaction: discord.Interaction):
        """Toggle goodbye message delivery allowance"""
        await interaction.response.defer()
        db_guild = crud_database.get_or_create_guild_record(interaction.guild)
        db_guild.is_goodbye_enabled = not db_guild.is_goodbye_enabled
        await interaction.followup.send(f"Goodbye message delivery: {'on' if db_guild.is_goodbye_enabled else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def toggle_bot_greeter(self, interaction: discord.Interaction):
        """Toggle greeting delivery allowance to BOTs"""
        await interaction.response.defer()
        db_guild = crud_database.get_or_create_guild_record(interaction.guild)
        db_guild.is_bot_greeting_enabled = not db_guild.is_bot_greeting_enabled
        await interaction.followup.send(f"BOTs greeter delivery: {'on' if db_guild.is_bot_greeting_enabled else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def toggle_dm_instead_of_channel(self, interaction: discord.Interaction):
        """Toggle greeting delivery to user's DM instead of the channel."""
        await interaction.response.defer()
        db_guild = crud_database.get_or_create_guild_record(interaction.guild)
        db_guild.is_dm_preferred = not db_guild.is_dm_preferred
        await interaction.followup.send(f"DM greeter delivery: {'on' if db_guild.is_dm_preferred else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def view_placeholders(self, interaction: discord.Interaction):
        """View available placeholders"""
        placeholders = {
            "{guild}": "The name of the guild.\nAvailability: Welcome+Goodbye.",
            "{@user}": "Mention that user.\nAvailability: Welcome.",
            "{name}": "Display name of that member.\nAvailability: Welcome+Goodbye.",
            "{tag}": "The 4-digit after #.\nAvailability: Welcome+Goodbye.",
        }

        await interaction.response.send_message(
            "\n".join(f"**{key}**\n{value}\n" for key, value in placeholders.items())
        )

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle_native_timeout(self, interaction: discord.Interaction):
        """Toggle using native 'Timeout' feature instead of using 'Mute role'"""
        await interaction.response.defer()
        db_guild = crud_database.get_or_create_guild_record(interaction.guild)
        db_guild.is_timeout_preferred = not db_guild.is_timeout_preferred
        await interaction.followup.send(
            f"Use native `Timeout` feature: {'on' if db_guild.is_timeout_preferred else 'off'}"
        )


async def setup(bot: nameless.Nameless):
    await bot.add_cog(ConfigCog(bot))
    logging.info("%s added!", __name__)


async def teardown(bot: nameless.Nameless):
    await bot.remove_cog("ConfigCog")
    logging.warning("%s removed!", __name__)
