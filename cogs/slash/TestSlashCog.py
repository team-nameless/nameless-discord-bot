import nextcord
from nextcord.ext import commands

from config import Config


class TestSlashCog(commands.Cog):
    """
    This cog is reserved for my future developments

    Copypaste from https://gist.github.com/AbstractUmbra/a9c188797ae194e592efe05fa129c57f
    """
    def __init__(self, bot: commands.AutoShardedBot) -> None:
        self.bot = bot

    # https://github.com/nextcord/nextcord/blob/master/examples/application_commands/sub_commands.py
    @nextcord.slash_command(name="parent", description="This is a parent command", guild_ids=Config.GUILD_IDs)
    async def parent(self, interaction: nextcord.Interaction):
        pass

    @nextcord.slash_command(name="top-command", description="Describe a top level command", guild_ids=Config.GUILD_IDs)
    async def my_top_command(self, interaction: nextcord.Interaction) -> None:
        """ /top-command """
        await interaction.response.send_message("Hello from top level command!", ephemeral=True)

    @parent.subcommand(name="sub-command", description="Describe a sub command")
    async def my_sub_command(self, interaction: nextcord.Interaction) -> None:
        """ /parent sub-command """
        await interaction.response.send_message("Hello from the sub command!", ephemeral=True)
