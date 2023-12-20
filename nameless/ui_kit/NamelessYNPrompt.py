import discord

__all__ = ["NamelessYNPrompt"]


class NamelessYNPrompt(discord.ui.View):
    def __init__(self, timeout: int = 15):
        super().__init__(timeout=timeout)
        self.is_confirmed = False

    @discord.ui.button(label="Yep!", style=discord.ButtonStyle.green)  # pyright: ignore
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.is_confirmed = True
        self.stop()

    @discord.ui.button(label="Nope!", style=discord.ButtonStyle.red)  # pyright: ignore
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        await interaction.response.defer()
        return await super().interaction_check(interaction)
