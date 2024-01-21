import datetime
import logging

import discord
from discord import app_commands
from discord.ext import commands

import nameless
from nameless.cogs.checks import BaseCheck
from nameless.database import CRUD
from nameless.ui_kit import NamelessModal

__all__ = ["ConfigCog"]


class ConfigCog(commands.GroupCog, name="config"):
    def __init__(self, bot: nameless.Nameless):
        super().__init__()
        self.bot = bot

    async def _send_greeter(
        self,
        content: str,
        member: discord.Member,
        send_target: discord.abc.GuildChannel | discord.Member | discord.Thread | None,
    ):
        if send_target is not None and (isinstance(send_target, discord.TextChannel | discord.Thread | discord.Member)):
            await send_target.send(
                content=content.replace("{guild}", member.guild.name)
                .replace("{name}", member.display_name)
                .replace("{tag}", member.discriminator)
            )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        db_guild = CRUD.get_or_create_guild_record(member.guild)

        if db_guild.voice_room_channel_id == 0:
            return

        is_a_join = before.channel is None and after.channel is not None
        joined_the_master = after.channel.id == db_guild.voice_room_channel_id

        if is_a_join and joined_the_master:
            current_category = after.channel.category
            current_position = after.channel.position
            vc = await after.channel.guild.create_voice_channel(
                f"@{member.name}'s Voice", category=current_category, position=current_position + 1
            )
            await member.move_to(vc)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        db_guild = CRUD.get_or_create_guild_record(member.guild)

        if db_guild.is_goodbye_enabled and db_guild.goodbye_message != "":
            if member.bot and not db_guild.is_bot_greeting_enabled:
                return

            send_target = member.guild.get_channel_or_thread(db_guild.goodbye_channel_id)

            await self._send_greeter(db_guild.goodbye_message, member, send_target)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        db_guild = CRUD.get_or_create_guild_record(member.guild)

        if db_guild.is_welcome_enabled and db_guild.welcome_message != "":
            if member.bot and not db_guild.is_bot_greeting_enabled:
                return

            send_target = member.guild.get_channel_or_thread(db_guild.welcome_channel_id)

            if db_guild.is_dm_preferred:
                send_target = member

            await self._send_greeter(db_guild.goodbye_message, member, send_target)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def view(self, interaction: discord.Interaction):
        """View configured properties"""
        await interaction.response.defer()

        db_guild = CRUD.get_or_create_guild_record(interaction.guild)

        wc_chn = interaction.guild.get_channel(db_guild.welcome_channel_id)
        gb_chn = interaction.guild.get_channel(db_guild.goodbye_channel_id)
        vc_chn = interaction.guild.get_channel(db_guild.voice_room_channel_id)
        mute_role = interaction.guild.get_role(db_guild.mute_role_id)
        reaction = [":x:", ":white_check_mark:"]
        dm = db_guild.is_dm_preferred

        embed: discord.Embed = (
            discord.Embed(color=discord.Color.orange(), timestamp=datetime.datetime.now())
            .set_thumbnail(url=interaction.guild.icon.url)
            .set_author(
                icon_url=interaction.client.user.display_avatar.url,
                name=f"Configured properties for '{interaction.guild.name}'",
            )
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
        ).add_field(name="Greeting to BOTs", value=db_guild.is_bot_greeting_enabled, inline=False)

        embed.add_field(
            name=":police_officer: Server utilities",
            value="```\n"
            "These are the settings related to server utilities such as using native 'Timeout' "
            "in replace for traditional 'Mute role', ... "
            "\n```",
            inline=False,
        ).add_field(name="Use native timeout feature", value=db_guild.is_timeout_preferred, inline=False).add_field(
            name="Max warning count", value=db_guild.max_warn_count
        ).add_field(name="Mute role", value=mute_role.mention if mute_role else "Unset").add_field(
            name="Voice room", value=vc_chn.mention if vc_chn else "Unset"
        )

        await interaction.followup.send(embeds=[embed])

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(edit_text="Whether you want to edit on the old message.")
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def set_welcome_message(self, interaction: discord.Interaction, edit_text: bool = True):
        """Change greeter welcome message"""
        db_guild = CRUD.get_or_create_guild_record(interaction.guild)

        modal = NamelessModal(title="New welcome text", initial_text=db_guild.welcome_message if edit_text else None)
        modal.text.label = "Greeter welcome text"

        await interaction.response.send_modal(modal)
        await modal.wait()

        db_guild.welcome_message = modal.text.value

        await interaction.followup.send(content=f"Your new welcome text:\n\n{db_guild.welcome_message}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(edit_text="Whether you want to edit on the old message.")
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def set_goodbye_message(self, interaction: discord.Interaction, edit_text: bool = True):
        """Change goodbye message"""
        db_guild = CRUD.get_or_create_guild_record(interaction.guild)

        modal = NamelessModal(title="New goodbye text", initial_text=db_guild.goodbye_message if edit_text else None)
        modal.text.label = "Greeter goodbye text"

        await interaction.response.send_modal(modal)
        await modal.wait()

        db_guild.goodbye_message = modal.text.value

        await interaction.followup.send(f"Your new goodbye text:\n\n{db_guild.goodbye_message}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(dest_channel="Goodbye message delivery channel")
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def set_goodbye_channel(
        self, interaction: discord.Interaction, dest_channel: discord.TextChannel | discord.Thread
    ):
        """Change goodbye message delivery channel"""
        await interaction.response.defer()
        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        db_guild.goodbye_channel_id = dest_channel.id

        await interaction.followup.send(f"Done updating goodbye channel to {dest_channel.mention}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(dest_channel="Welcome message delivery channel")
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def set_welcome_channel(
        self, interaction: discord.Interaction, dest_channel: discord.TextChannel | discord.Thread
    ):
        """Change welcome message delivery channel"""
        await interaction.response.defer()
        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        db_guild.welcome_channel_id = dest_channel.id

        await interaction.followup.send(f"Done updating welcome channel to {dest_channel.mention}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def toggle_welcome(self, interaction: discord.Interaction):
        """Toggle welcome message delivery allowance"""
        await interaction.response.defer()
        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        db_guild.is_welcome_enabled = not db_guild.is_welcome_enabled

        await interaction.followup.send(f"Welcome message delivery: {'on' if db_guild.is_welcome_enabled else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def toggle_goodbye(self, interaction: discord.Interaction):
        """Toggle goodbye message delivery allowance"""
        await interaction.response.defer()
        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        db_guild.is_goodbye_enabled = not db_guild.is_goodbye_enabled

        await interaction.followup.send(f"Goodbye message delivery: {'on' if db_guild.is_goodbye_enabled else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def toggle_bot_greeter(self, interaction: discord.Interaction):
        """Toggle greeting delivery allowance to BOTs"""
        await interaction.response.defer()
        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        db_guild.is_bot_greeting_enabled = not db_guild.is_bot_greeting_enabled

        await interaction.followup.send(f"BOTs greeter delivery: {'on' if db_guild.is_bot_greeting_enabled else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(BaseCheck.require_interaction_intents([discord.Intents.members]))
    async def toggle_dm_instead_of_channel(self, interaction: discord.Interaction):
        """Toggle greeting delivery to user's DM instead of the channel."""
        await interaction.response.defer()
        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        db_guild.is_dm_preferred = not db_guild.is_dm_preferred

        await interaction.followup.send(f"DM greeter delivery: {'on' if db_guild.is_dm_preferred else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(dest_channel="Target room channel")
    async def set_voice_room_channel(self, interaction: discord.Interaction, dest_channel: discord.VoiceChannel):
        """Change welcome message delivery channel"""
        await interaction.response.defer()
        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        db_guild.voice_room_channel_id = dest_channel.id

        await interaction.followup.send(f"Done setting voice room to {dest_channel.mention}")

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


async def setup(bot: nameless.Nameless):
    await bot.add_cog(ConfigCog(bot))
    logging.info("%s added!", __name__)


async def teardown(bot: nameless.Nameless):
    await bot.remove_cog("ConfigCog")
    logging.warning("%s removed!", __name__)
