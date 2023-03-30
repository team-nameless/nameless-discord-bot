import discord
from discord import ui


__all__ = ["GreeterMessageModal"]


class GreeterMessageModal(ui.Modal, title="New greeter text"):
    def __init__(self, initial_text: str | None = None):
        super().__init__()

        if initial_text is not None:
            self.text.default = initial_text

    text = ui.TextInput(
        label="...",  # this attribute should be edited per-command
        style=discord.TextStyle.paragraph,
        max_length=2000,
        placeholder="If you need some placeholders, use the 'view placeholders' command",
    )

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        await interaction.response.send_message("Hang on, your greeter text should be updated soon!")
