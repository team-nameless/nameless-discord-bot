"""Reusable framework for player option menus with dropdown navigation.

This module provides a dropdown-based menu system for controlling CustomPlayer settings.
The framework supports:
- Dropdown select menu for navigating options
- Modals for detailed settings (Volume & Speed)
- Direct toggles for simple settings (Autoplay)
- Automatic embed updates after changes

Example:
    The menu structure:
    - General Settings (opens modal with Volume & Speed)
    - Toggle Autoplay (on/off)
    - EQ Settings (placeholder)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Self, final, override

import discord
from discord.ui import Select, View

if TYPE_CHECKING:
    from .player import CustomPlayer


class PlayerOptionModal(discord.ui.Modal, ABC):
    """Base class for player option modals.

    This framework provides a consistent structure for creating modals
    that control player settings. Subclasses should:
    1. Define their input fields in __init__
    2. Implement validate_inputs() to check user input
    3. Implement apply_changes() to modify the player

    HOW TO CREATE A NEW MODAL:
    1. Create a new class that inherits from PlayerOptionModal
    2. Add @final decorator to prevent further inheritance
    3. Implement the required abstract methods

    Example - Creating a new "EQ Settings" modal:

        @final
        class EQSettingsModal(PlayerOptionModal):
            def __init__(self, player: CustomPlayer):
                super().__init__(player, title="EQ Settings")

                self.bass_input = discord.ui.TextInput[Self](
                    label="Bass (-10 to 10)",
                    placeholder="Current: 0",
                    default="0",
                    required=False,
                )
                self.add_item(self.bass_input)

            async def validate_inputs(self, interaction) -> tuple[bool, str | None]:
                bass_str = self.bass_input.value.strip()
                if bass_str:
                    try:
                        bass = int(bass_str)
                        if not -10 <= bass <= 10:
                            return False, "Bass must be between -10 and 10"
                    except ValueError:
                        return False, "Bass must be a valid number"
                return True, None

            async def apply_changes(self, interaction) -> str:
                changes = []
                bass_str = self.bass_input.value.strip()
                if bass_str:
                    bass = int(bass_str)
                    await self.player.set_bass(bass)
                    changes.append(f"Bass: {bass}")
                return "Updated: " + ", ".join(changes) if changes else "No changes made"

    Then add it to the dropdown in PlayerOptionsSelect callback:
        elif selected == "eq":
            modal = EQSettingsModal(self.player)
            await interaction.response.send_modal(modal)
    """

    def __init__(self, player: CustomPlayer, title: str, timeout: float = 180.0):
        super().__init__(title=title, timeout=timeout)
        self.player = player
        self.parent_view: PlayerOptionsMenuView | None = None

    @abstractmethod
    async def validate_inputs(self, interaction: discord.Interaction) -> tuple[bool, str | None]:
        """Validate user inputs before applying changes.

        Returns:
            (success, error_message): If success is False, error_message will be shown.
        """

    @abstractmethod
    async def apply_changes(self, interaction: discord.Interaction) -> str:
        """Apply validated changes to the player.

        Returns:
            success_message: A message to display after successful application.
        """

    @override
    async def on_submit(self, interaction: discord.Interaction):
        is_valid, error_message = await self.validate_inputs(interaction)
        if not is_valid:
            await interaction.response.send_message(f"❌ {error_message}", ephemeral=True)
            return

        try:
            success_message = await self.apply_changes(interaction)
            await interaction.response.send_message(success_message, ephemeral=True)

            # Update the now playing embed if it exists
            if interaction.message:
                await self.player.update_now_playing_embed(interaction.message, interaction.user)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @override
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logging_message = f"Error in {self.__class__.__name__}: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ {logging_message}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {logging_message}", ephemeral=True)


@final
class PlayerOptionsMenuView(View):
    """Dropdown-based menu for player options.

    Menu structure:
    - General Settings: Opens modal with Volume & Speed settings
    - Toggle Autoplay: Instantly toggles autoplay on/off
    - EQ Settings: Placeholder for future audio filters
    """

    def __init__(self, player: CustomPlayer, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.player = player
        self.add_item(PlayerOptionsSelect(player))

    @override
    async def on_timeout(self):
        """Disable all items when the view times out."""
        for item in self.children:
            if isinstance(item, Select):
                item.disabled = True


@final
class PlayerOptionsSelect(Select[PlayerOptionsMenuView]):
    """Dropdown select menu for player options.

    HOW TO ADD NEW DROPDOWN OPTIONS:
    1. Add a new discord.SelectOption to the options list
    2. Add a handler in the callback() method
    3. Either open a modal or perform an action directly

    Example - Adding a "Loop Mode" option:
        options = [
            ...existing options...,
            discord.SelectOption(
                label="Loop Mode",
                value="loop",  # This is the internal identifier
                description="Change loop mode (Off/Track/Queue)",
                emoji="🔁",
            ),
        ]

        # Then in callback():
        elif selected == "loop":
            modal = LoopModeModal(self.player)
            await interaction.response.send_modal(modal)
    """

    def __init__(self, player: CustomPlayer):
        self.player = player

        # Build options dynamically with current state
        autoplay_status = "ON" if player.is_autoplay_enabled else "OFF"
        autoplay_emoji = "✅" if player.is_autoplay_enabled else "❌"

        # NOTE: Discord dropdowns support up to 25 options
        options = [
            discord.SelectOption(
                label="General Settings",
                value="general",
                description="Adjust Volume and Speed",
                emoji="🎛️",
            ),
            discord.SelectOption(
                label=f"Toggle Autoplay ({autoplay_status})",
                value="autoplay",
                description=f"Currently {autoplay_status} - Click to toggle",
                emoji=autoplay_emoji,
            ),
            discord.SelectOption(
                label="EQ Settings",
                value="eq",
                description="Audio equalizer settings",
                emoji="🎚️",
            ),
            # ADD NEW OPTIONS HERE:
            # discord.SelectOption(
            #     label="Your New Option",
            #     value="your_value",
            #     description="Description shown in dropdown",
            #     emoji="🎵",
            # ),
        ]

        super().__init__(
            placeholder="Choose a setting to configure...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="player_options_select",
        )

    @override
    async def callback(self, interaction: discord.Interaction):
        """Handle dropdown selection."""
        selected = self.values[0]

        if selected == "general":
            # Open general settings modal
            modal = GeneralSettingsModal(self.player)
            await interaction.response.send_modal(modal)

        elif selected == "autoplay":
            await interaction.response.defer(ephemeral=True)

            self.player.toggle_autoplay()

            autoplay_status = "ON" if self.player.is_autoplay_enabled else "OFF"
            autoplay_emoji = "✅" if self.player.is_autoplay_enabled else "❌"

            self.options[1].label = f"Toggle Autoplay ({autoplay_status})"
            self.options[1].description = f"Currently {autoplay_status} - Click to toggle"
            self.options[1].emoji = autoplay_emoji

            status = "enabled" if self.player.is_autoplay_enabled else "disabled"
            await interaction.followup.send(f"🔄 Autoplay {status}", ephemeral=True)

            if interaction.message:
                await interaction.message.edit(view=self.view)
                await self.player.update_now_playing_embed(interaction.message, interaction.user)

        elif selected == "eq":
            await interaction.response.send_message("🎚️ EQ settings coming soon!", ephemeral=True)


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
        """Apply volume and speed changes to the player."""
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
