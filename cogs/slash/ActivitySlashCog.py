import nextcord
from nextcord import SlashOption
from nextcord.ext import commands

from discord_together import DiscordTogether, discordTogetherMain

from config import Config


class ActivitySlashCog(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot) -> None:
        self.bot = bot

    @nextcord.slash_command(description="Embedded activity commands", guild_ids=Config.GUILD_IDs)
    async def activity(self, _: nextcord.Interaction):
        pass

    @activity.subcommand(description="Create a embedded activity")
    async def create(self,
                     interaction: nextcord.Interaction,
                     activity: str = SlashOption(description="Your desired activity",
                                                 choices=discordTogetherMain.defaultApplications)):
        await interaction.response.send_message("Generating link")

        if not interaction.user.voice:
            await interaction.edit_original_message(content="You need to be in a voice channel")
            return

        together: DiscordTogether = await DiscordTogether(Config.TOKEN)
        link: str = await together.create_link(interaction.user.voice.channel.id, activity)

        await interaction.edit_original_message(content=f"Here is your link: {link}")
