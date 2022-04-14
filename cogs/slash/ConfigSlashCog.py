import nextcord
from nextcord import SlashOption, ChannelType
from nextcord.ext import commands, application_checks

from config import Config
from database import DbGuild
from globals import postgres_database


class ConfigSlashCog(commands.Cog):
    def __init__(self, bot: nextcord.AutoShardedClient):
        self.bot = bot

    @nextcord.slash_command(description="Guild configuration commands", guild_ids=Config.GUILD_IDs)
    async def config(self, _: nextcord.Interaction):
        pass

    @config.subcommand(description="Change welcome message")
    @application_checks.has_guild_permissions(manage_guild=True)
    async def set_welcome_message(self, interaction: nextcord.Interaction,
                                  message: str = SlashOption(description="Welcome message")):
        await interaction.response.defer()
        dbg, _ = postgres_database.get_or_create_guild_record(interaction.guild)
        dbg.welcome_message = message
        await interaction.edit_original_message(content="Done updating welcome message")

    @config.subcommand(description="Change goodbye message")
    @application_checks.has_guild_permissions(manage_guild=True)
    async def set_goodbye_message(self, interaction: nextcord.Interaction,
                                  message: str = SlashOption(description="Goodbye message")):
        await interaction.response.defer()
        dbg, _ = postgres_database.get_or_create_guild_record(interaction.guild)
        dbg.goodbye_message = message
        await interaction.edit_original_message(content="Done updating goodbye message")

    @config.subcommand(description="Change welcome message dumping channel")
    @application_checks.has_guild_permissions(manage_guild=True)
    async def set_welcome_channel(self, interaction: nextcord.Interaction,
                                  channel: nextcord.abc.GuildChannel = SlashOption(
                                      description="Destination channel",
                                      channel_types=[
                                          ChannelType.text,
                                          ChannelType.news,
                                          ChannelType.news_thread,
                                          ChannelType.public_thread,
                                          ChannelType.private_thread
                                      ]
                                  )):
        await interaction.response.defer()
        dbg, _ = postgres_database.get_or_create_guild_record(interaction.guild)
        dbg.goodbye_channel_id = channel.id
        await interaction.edit_original_message(content=f"Done updating welcome channel to {channel.mention}")

    @config.subcommand(description="Change goodbye message dumping channel")
    @application_checks.has_guild_permissions(manage_guild=True)
    async def set_goodbye_channel(self, interaction: nextcord.Interaction,
                                  channel: nextcord.abc.GuildChannel = SlashOption(
                                      description="Destination channel",
                                      channel_types=[
                                          ChannelType.text,
                                          ChannelType.news,
                                          ChannelType.news_thread,
                                          ChannelType.public_thread,
                                          ChannelType.private_thread
                                      ]
                                  )):
        await interaction.response.defer()
        dbg, _ = postgres_database.get_or_create_guild_record(interaction.guild)
        dbg.goodbye_channel_id = channel.id
        await interaction.edit_original_message(content=f"Done updating goodbye channel to {channel.mention}")

    @config.subcommand(description="Toggle welcome allowance")
    @application_checks.has_guild_permissions(manage_guild=True)
    async def toggle_welcome(self, interaction: nextcord.Interaction):
        await interaction.response.defer()
        dbg, _ = postgres_database.get_or_create_guild_record(interaction.guild)
        dbg.is_welcome_enabled = not DbGuild.is_welcome_enabled
        await interaction.edit_original_message(content=f"Welcome message sending is now "
                                                        f"{'enabled' if dbg.is_welcome_enabled else 'disabled'}")

    @config.subcommand(description="Toggle goodbye allowance")
    @application_checks.has_guild_permissions(manage_guild=True)
    async def toggle_goodbye(self, interaction: nextcord.Interaction):
        await interaction.response.defer()
        dbg, _ = postgres_database.get_or_create_guild_record(interaction.guild)
        dbg.is_goodbye_enabled = not DbGuild.is_goodbye_enabled
        await interaction.edit_original_message(content=f"Goodbye message sending is now "
                                                        f"{'enabled' if dbg.is_welcome_enabled else 'disabled'}")

    @config.subcommand(description="View available placeholders")
    async def view_placeholders(self, interaction: nextcord.Interaction):
        await interaction.response.defer()

        placeholders = {
            "{guild}": "The name of the guild.\nAvailability: Welcome+Goodbye.",
            "{@user}": "Mention that user.\nAvailability: Welcome.",
            "{name}": "Display name of that member.\nAvailability: Welcome+Goodbye.",
            "{tag}": "The 4-digit after #.\nAvailability: Welcome+Goodbye.",
        }

        await interaction.edit_original_message(content=
                                                '\n'.join(f'**{key}**\n{value}\n'
                                                          for key, value in placeholders.items()))
