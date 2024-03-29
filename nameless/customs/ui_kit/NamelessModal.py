import discord
from discord import ui

__all__ = ["NamelessModal"]


class NamelessModal(ui.Modal):
    def __init__(self, *, title: str, initial_text: str | None = None):
        super().__init__(title=title)

        self.title = title

        if initial_text is not None:
            self.text.default = initial_text

    text: ui.TextInput = ui.TextInput(
        label="...",  # this attribute should be edited per-command
        style=discord.TextStyle.paragraph,
        max_length=2000,
    )

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        await interaction.response.send_message("Hang on, your response should be acknowledged soon!")
