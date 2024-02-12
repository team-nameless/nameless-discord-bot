from discord.app_commands import CommandTree
from discord.interactions import Interaction

from nameless.nameless import Nameless

__all__ = ["NamelessCommandTree"]


class NamelessCommandTree(CommandTree[Nameless]):
    def __init__(self, client: Nameless, *, fallback_to_global: bool = True):
        super().__init__(client, fallback_to_global=fallback_to_global)

    async def interaction_check(self, interaction: Interaction) -> bool:
        user = interaction.user
        guild = interaction.guild

        return not await self.client.is_blacklisted(user=user, guild=guild)
