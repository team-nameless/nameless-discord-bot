from discord.app_commands import CommandTree
from discord.interactions import Interaction

from nameless.nameless import Nameless

__all__ = ["NamelessCommandTree"]


class NamelessCommandTree(CommandTree[Nameless]):
    def __init__(self, client, *, fallback_to_global: bool = True):
        super().__init__(client, fallback_to_global=fallback_to_global)

    async def interaction_check(self, interaction: Interaction) -> bool:
        user = interaction.user
        guild = interaction.guild

        is_user_blacklisted = self.client.is_blacklisted(user=user)
        is_guild_blacklisted = self.client.is_blacklisted(guild=guild)

        if is_user_blacklisted:
            interaction.response.send_message(
                "You have been blacklisted from using me, "
                "please contact the owner for more information.",
                ephemeral=True)
            return False

        if is_guild_blacklisted:
            interaction.response.send_message(
                "This guild has been blacklisted from using me, "
                "please inform the guild owner about this.",
                ephemeral=True)
            return False

        return True
