from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Self, override

import discord

if TYPE_CHECKING:
    from nameless.nameless import Nameless

    from .player import CustomPlayer


__all__ = ["VoteSkipView"]


class VoteSkipView(discord.ui.View):
    """Vote skip prompt for skipping the current track."""

    def __init__(
        self,
        player: CustomPlayer,
        initiator_id: int,
        required_votes: int,
        timeout: int = 60,
    ) -> None:
        super().__init__(timeout=timeout)
        self._result: bool = False
        self._message: discord.Message | None = None

        self.player = player
        self.initiator_id = initiator_id
        self.required_votes = required_votes
        self.yes_voters: set[int] = {initiator_id}
        self.no_voters: set[int] = set()

        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.style == discord.ButtonStyle.green:
                    item.label = "Skip"
                    item.emoji = "⏭️"
                elif item.style == discord.ButtonStyle.red:
                    item.label = "Keep Playing"
                    item.emoji = "▶️"

    @property
    def result(self) -> bool:
        return self._result

    @property
    def voters(self) -> set[int]:
        return self.yes_voters | self.no_voters

    def set_message(self, message: discord.Message) -> None:
        self._message = message

    def create_embed(self, track_title: str, initiator_name: str) -> discord.Embed:
        embed = discord.Embed(color=discord.Color.blue())
        embed.title = "Vote Skip"
        embed.description = f"**{initiator_name}** wants to skip **{track_title}**"

        # Vote progress
        embed.add_field(
            name="Progress",
            value=f"**{len(self.yes_voters)}/{self.required_votes}** votes needed to skip",
            inline=False,
        )

        # Yes voters
        if self.yes_voters:
            yes_mentions = " ".join(f"<@{user_id}>" for user_id in self.yes_voters)
            embed.add_field(name=f"Skip ({len(self.yes_voters)})", value=yes_mentions, inline=True)

        # No voters
        if self.no_voters:
            no_mentions = " ".join(f"<@{user_id}>" for user_id in self.no_voters)
            embed.add_field(name=f"Keep Playing ({len(self.no_voters)})", value=no_mentions, inline=True)

        return embed

    def create_result_embed(self, track_title: str, initiator_name: str) -> discord.Embed:
        if self.result:
            embed = discord.Embed(color=discord.Color.green())
            embed.title = "Vote Skip"
            embed.description = f"Vote passed! Skipping **{track_title}**"
        else:
            embed = discord.Embed(color=discord.Color.blue())
            embed.title = "Vote Skip"
            embed.description = (
                f"Vote ended. **{len(self.yes_voters)}/{self.required_votes}** votes - not enough to skip."
            )

        if self.yes_voters:
            yes_mentions = " ".join(f"<@{user_id}>" for user_id in self.yes_voters)
            embed.add_field(name=f"Voted Skip ({len(self.yes_voters)})", value=yes_mentions, inline=True)

        if self.no_voters:
            no_mentions = " ".join(f"<@{user_id}>" for user_id in self.no_voters)
            embed.add_field(name=f"Voted Keep ({len(self.no_voters)})", value=no_mentions, inline=True)

        return embed

    async def _update_embed(self, interaction: discord.Interaction[Nameless]) -> None:
        if not self._message or not self.player.current:
            return

        track_title = self.player.current.title
        initiator = interaction.guild.get_member(self.initiator_id) if interaction.guild else None
        initiator_name = initiator.display_name if initiator else "Someone"

        embed = self.create_embed(track_title, initiator_name)

        try:
            await self._message.edit(embed=embed)
        except discord.HTTPException as e:
            logging.warning(f"failed to update vote skip embed: {e}")

    @discord.ui.button(label="Skip", emoji="⏭️", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction[Nameless], _btn: discord.ui.Button[Self]) -> None:
        await interaction.response.defer()

        if interaction.user.id in self.voters:
            await interaction.followup.send("You have already voted!", ephemeral=True)
            return

        self.yes_voters.add(interaction.user.id)
        await self._update_embed(interaction)

        if len(self.yes_voters) >= self.required_votes:
            self._result = True
            await interaction.followup.send("Vote passed! Skipping track...", ephemeral=True)
            await self.player.stop()
            self.stop()
        else:
            await interaction.followup.send(
                f"Vote recorded! **{len(self.yes_voters)}/{self.required_votes}** votes to skip.",
                ephemeral=True,
            )

    @discord.ui.button(label="Keep Playing", emoji="▶️", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction[Nameless], _btn: discord.ui.Button[Self]) -> None:
        await interaction.response.defer()

        if interaction.user.id in self.voters:
            await interaction.followup.send("You have already voted!", ephemeral=True)
            return

        self.no_voters.add(interaction.user.id)

        await self._update_embed(interaction)
        await interaction.followup.send("Vote recorded!", ephemeral=True)

    @override
    async def on_timeout(self) -> None:
        # Disable all buttons when timeout occurs
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
