import nextcord
from nextcord.ext import commands, application_checks

import config


class OwnerSlashCog(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot) -> None:
        self.bot = bot

    @nextcord.slash_command(name="shutdown", description="Shutdown the client", guild_ids=config.GUILD_IDs)
    @application_checks.is_owner()
    async def shutdown(self, interaction: nextcord.Interaction) -> None:
        await interaction.response.send_message("Bye owo!")
        exit(-1)
