import nextcord
from nextcord import SlashOption
from nextcord.ext import commands, application_checks

from config import Config


class TestSlashCog(commands.Cog):
    """
    - This cog is reserved for my future developments
    - Copypasta:
    https://gist.github.com/AbstractUmbra/a9c188797ae194e592efe05fa129c57f
    https://github.com/nextcord/nextcord/blob/master/examples/application_commands/sub_commands.py
    """
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot

    @nextcord.slash_command(description="This is a parent command", guild_ids=Config.GUILD_IDs)
    async def parent(self, _: nextcord.Interaction):
        pass

    @nextcord.slash_command(description="Describe a top level command", guild_ids=Config.GUILD_IDs)
    async def top_command(self, interaction: nextcord.Interaction):
        """ /top-command """
        await interaction.response.send_message("Hello from top level command!", ephemeral=True)

    @parent.subcommand(description="Describe a sub command")
    async def sub_command(self, interaction: nextcord.Interaction):
        """ /parent sub-command """
        await interaction.response.send_message("Hello from the sub command!", ephemeral=True)
