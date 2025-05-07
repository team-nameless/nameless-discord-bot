import logging

import discord
import wavelink

from nameless.custom.player.settings.base import BaseSettingsView
from nameless.custom.ui.modal import NamelessModal

__all__ = ["FilterModal", "FilterView"]


class FilterModal(NamelessModal[int]):
    def __init__(self, title: str, filters: wavelink.Filters) -> None:
        super().__init__(title)

        self.filters: wavelink.Filters = filters
        self.on_create()

    def on_create(self):
        pass


class FilterView(BaseSettingsView):
    def __init__(
        self,
        author: discord.Member | discord.User,
        message: discord.Message,
        filters: wavelink.Filters,
    ):
        super().__init__(author, message)
        self.filters: wavelink.Filters = filters
        self._exit: bool = False
        self._save: bool = False

    def exit(self):
        self._exit = True
        self.stop()

    def save(self):
        self._save = True
        self.stop()

    def is_save(self) -> bool:
        return self._save

    def is_exit(self) -> bool:
        return self._exit

    def set_filter(self, category: str, name: str, value: float):
        try:
            getattr(self.filters, category).set(**{name: value})  # pyright: ignore[reportAny]
            return True
        except AttributeError:
            logging.error(f"Failed to set filter {category} {name} {value}")
            return False
