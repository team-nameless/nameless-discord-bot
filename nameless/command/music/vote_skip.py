from __future__ import annotations

from typing import TYPE_CHECKING, Self, override

import discord

from nameless.custom.ui import NamelessYesNoPrompt

if TYPE_CHECKING:
    from nameless.nameless import Nameless

    from .player import CustomPlayer


__all__ = ["VoteSkipView"]


class VoteSkipView(NamelessYesNoPrompt):
    """Vote skip prompt for skipping the current track."""

    def __init__(
        self,
        player: CustomPlayer,
        initiator_id: int,
        required_votes: int,
        timeout: int = 60,
    ) -> None:
        super().__init__(timeout=timeout)
        self.player = player
        self.initiator_id = initiator_id
        self.required_votes = required_votes
        self.voters: set[int] = {initiator_id}

        # Update button labels
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.style == discord.ButtonStyle.green:
                    item.label = "Skip"
                    item.emoji = "⏭️"
                elif item.style == discord.ButtonStyle.red:
                    item.label = "Keep Playing"
                    item.emoji = "▶️"

    @discord.ui.button(label="Skip", emoji="⏭️", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction[Nameless], _btn: discord.ui.Button[Self]) -> None:
        if interaction.user.id in self.voters:
            await interaction.followup.send("You have already voted!", ephemeral=True)
            return

        self.voters.add(interaction.user.id)
        self.player.votes.add(interaction.user.id)

        if len(self.voters) >= self.required_votes:
            self.is_a_yes = True
            await interaction.followup.send("✅ Vote passed! Skipping track...", ephemeral=True)
            await self.player.stop()
            self.stop()
        else:
            await interaction.followup.send(
                f"✅ Vote recorded! **{len(self.voters)}/{self.required_votes}** votes to skip.",
                ephemeral=True,
            )

    @discord.ui.button(label="Keep Playing", emoji="▶️", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction[Nameless], _btn: discord.ui.Button[Self]) -> None:
        await interaction.followup.send("Vote recorded!", ephemeral=True)

    @override
    async def on_timeout(self) -> None:
        # Disable all buttons when timeout occurs
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
