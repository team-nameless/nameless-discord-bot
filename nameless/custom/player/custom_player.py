from __future__ import annotations

from typing import TYPE_CHECKING

from wavelink import Player

from .settings.sponsorblock_settings import SponsorBlockSettings

if TYPE_CHECKING:
    from discord.abc import MessageableChannel


__all__ = ["CustomPlayer"]


class CustomPlayer(Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trigger_channel: MessageableChannel = self.channel
        self.play_now_allowed: bool = True
        self.sponsorblock_settings: SponsorBlockSettings = SponsorBlockSettings(0)
