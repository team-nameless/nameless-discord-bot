from __future__ import annotations

from typing import TYPE_CHECKING, Self, final, override

import discord

from .base import PlayerOptionModal

if TYPE_CHECKING:
    from nameless.command.music.player import CustomPlayer


@final
class GeneralSettingsModal(PlayerOptionModal):
    def __init__(self, player: CustomPlayer):
        super().__init__(player, title="General Settings")

        self.volume_input = discord.ui.TextInput[Self](
            label="Volume (0-200)",
            placeholder=f"Current: {player.volume}",
            default=str(player.volume),
            min_length=1,
            max_length=3,
            required=False,
        )
        self.add_item(self.volume_input)

        self.speed_input = discord.ui.TextInput[Self](
            label="Speed (0.5-2.0)",
            placeholder=f"Current: {player.speed}",
            default=str(player.speed),
            min_length=3,
            max_length=4,
            required=False,
        )
        self.add_item(self.speed_input)

    @override
    async def validate_inputs(self, interaction: discord.Interaction) -> tuple[bool, str | None]:
        """Validate volume and speed inputs."""
        volume_str = self.volume_input.value.strip()
        if volume_str:
            try:
                volume = int(volume_str)
                if not 0 <= volume <= 200:
                    return False, "Volume must be between 0 and 200"
            except ValueError:
                return False, "Volume must be a valid number"

        speed_str = self.speed_input.value.strip()
        if speed_str:
            try:
                speed = float(speed_str)
                if not 0.5 <= speed <= 2.0:
                    return False, "Speed must be between 0.5 and 2.0"
            except ValueError:
                return False, "Speed must be a valid number"

        return True, None

    @override
    async def apply_changes(self, interaction: discord.Interaction) -> str:
        changes: list[str] = []

        volume_str = self.volume_input.value.strip()
        if volume_str:
            volume = int(volume_str)
            if volume != self.player.volume:
                await self.player.set_volume(volume)
                changes.append(f"Volume: {volume}%")

        speed_str = self.speed_input.value.strip()
        if speed_str:
            speed = float(speed_str)
            if speed != self.player.speed:
                await self.player.set_speed(speed)
                changes.append(f"Speed: {speed}x")

        if changes:
            return "✅ Updated: " + ", ".join(changes)
        return "ℹ️ No changes made"
