import nextcord
from nextcord import SlashOption
from nextcord.ext import commands, activities

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
                     target: str = SlashOption(description="Your desired activity",
                                                 choices={
                                                     str(i.name): str(i.value) for i in activities.enums.Activity
                                                 }),
                     voice_channel: nextcord.abc.GuildChannel = SlashOption(description="Target voice channel",
                                                                        channel_types=[nextcord.ChannelType.voice])):
        await interaction.response.send_message("Generating link")

        # voice_channel: nextcord.VoiceChannel
        # voice_channel.create_activity_invite = activities.create_activity_invite
        inv = await voice_channel.create_activity_invite(activities.Activity.custom, activity_id=int(target))

        await interaction.edit_original_message(content=f"Here is your link: {inv.url}")
