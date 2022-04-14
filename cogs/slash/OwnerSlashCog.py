import nextcord
from nextcord.ext import commands, application_checks

from config import Config


class OwnerSlashCog(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot) -> None:
        self.bot = bot

    @nextcord.slash_command(description="Shutdown the client", guild_ids=Config.GUILD_IDs)
    @application_checks.is_owner()
    async def shutdown(self, interaction: nextcord.Interaction) -> None:
        await interaction.response.send_message("Bye owo!")
        self.bot.loop.stop()
