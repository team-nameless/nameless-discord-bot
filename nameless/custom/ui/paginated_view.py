from collections.abc import Iterable
from typing import Self, override

import discord
from discord.ext.commands import Bot, Context
from discord.ui import Button, Modal, TextInput

__all__ = ["NamelessPaginatedView"]


class JumpToPageModal(Modal):
    """Modal to ask for specific page."""

    page: TextInput[Self] = TextInput(
        label="Page number",
        default="0",
        placeholder="Any page number, will failsafe to '0' (zero).",
    )

    @override
    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.stop()

    def get_value(self) -> int:
        """Get parsed page value. Will failsafe to 0."""
        try:
            return int(self.page.value)
        except ValueError:
            return 0


class NamelessPaginatedView(discord.ui.View):
    """nameless* custom paginated view."""

    def __init__(self, ctx: Context[Bot], timeout: int = 60):
        super().__init__(timeout=timeout)
        self.ctx: Context[Bot] = ctx
        self.pages: list[discord.Embed] = []
        self.current_page: int = 0
        self._current_message: discord.Message | None = None

    @property
    def message(self):
        if not self._current_message:
            return self.ctx.message

        return self._current_message

    @message.setter
    def message(self, value: discord.Message):
        self._current_message = value

    def add_pages(self, pages: Iterable[discord.Embed]) -> None:
        self.pages.extend(pages)

    def add_button(self, button: Button[Self]):
        self.add_item(button)

    async def next_page(self):
        if self.current_page + 1 >= len(self.pages):
            self.current_page = 0
        else:
            self.current_page += 1
        await self.message.edit(embed=self.pages[self.current_page], view=self)

    async def previous_page(self):
        if self.current_page - 1 < 0:
            self.current_page = len(self.pages) - 1
        else:
            self.current_page -= 1
        await self.message.edit(embed=self.pages[self.current_page], view=self)

    async def go_to_first_page(self):
        await self.message.edit(embed=self.pages[0], view=self)

    async def go_to_last_page(self):
        await self.message.edit(embed=self.pages[-1], view=self)

    async def go_to_page(self, page: int):
        self.current_page = page
        await self.ctx.send(embed=self.pages[self.current_page], view=self)

    async def start(self):
        self.message = await self.ctx.send(embed=self.pages[0], view=self)
        return await self.wait()

    async def end(self):
        self.stop()
        # await self.__current_message.delete()
        await self.message.edit(view=None)


class NavigationButton(Button[NamelessPaginatedView]):
    NEXT_PAGE_ID: str = "0"
    PREVIOUS_PAGE_ID: str = "1"
    GO_TO_FIRST_PAGE_ID: str = "2"
    GO_TO_LAST_PAGE_ID: str = "3"
    GO_TO_PAGE_ID: str = "4"
    END_ID: str = "5"

    def __init__(self, *args: object, **kwargs: object):
        super().__init__(*args, **kwargs)
        self._view: NamelessPaginatedView | None = None

    @override
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not self.view:
            raise ValueError("View not set for button")

        match self.custom_id:
            case self.NEXT_PAGE_ID:
                await self.view.next_page()
            case self.PREVIOUS_PAGE_ID:
                await self.view.previous_page()
            case self.GO_TO_FIRST_PAGE_ID:
                await self.view.go_to_first_page()
            case self.GO_TO_LAST_PAGE_ID:
                await self.view.go_to_last_page()
            case self.GO_TO_PAGE_ID:
                modal = JumpToPageModal()
                await interaction.response.send_modal(modal)
                if await modal.wait():
                    return

                if modal.page.value:
                    await self.view.go_to_page(int(modal.page.value) - 1)

            case self.END_ID:
                await self.view.end()
            case _:
                raise ValueError("Invalid button")

    @classmethod
    def create_button(
        cls,
        label: str | None,
        custom_id: str | None,
        emoji: discord.Emoji | discord.PartialEmoji | str | None,
        with_label: bool,
        with_emote: bool,
        with_disabled: bool,
        **kwargs: object,
    ):
        return cls(
            style=discord.ButtonStyle.gray,
            label=label if with_label else None,
            custom_id=custom_id,
            emoji=emoji if with_emote else None,
            disabled=with_disabled,
            **kwargs,
        )

    @classmethod
    def back(
        cls,
        with_label: bool = False,
        with_emote: bool = True,
        with_disabled: bool = False,
        **kwargs: object,
    ):
        return cls.create_button(
            "Back",
            cls.PREVIOUS_PAGE_ID,
            "⬅️",
            with_label,
            with_emote,
            with_disabled,
            **kwargs,
        )

    @classmethod
    def next(
        cls,
        with_label: bool = False,
        with_emote: bool = True,
        with_disabled: bool = False,
        **kwargs: object,
    ):
        return cls.create_button(
            "Next",
            cls.NEXT_PAGE_ID,
            "➡️",
            with_label,
            with_emote,
            with_disabled,
            **kwargs,
        )

    @classmethod
    def go_to_first_page(
        cls,
        with_label: bool = False,
        with_emote: bool = True,
        with_disabled: bool = False,
        **kwargs: object,
    ):
        return cls.create_button(
            "First Page",
            cls.GO_TO_FIRST_PAGE_ID,
            "⏮️",
            with_label,
            with_emote,
            with_disabled,
            **kwargs,
        )

    @classmethod
    def go_to_last_page(
        cls,
        with_label: bool = False,
        with_emote: bool = True,
        with_disabled: bool = False,
        **kwargs: object,
    ):
        return cls.create_button(
            "Last Page",
            cls.GO_TO_LAST_PAGE_ID,
            "⏭️",
            with_label,
            with_emote,
            with_disabled,
            **kwargs,
        )

    @classmethod
    def go_to_page(
        cls,
        with_label: bool = False,
        with_emote: bool = True,
        with_disabled: bool = False,
        **kwargs: object,
    ):
        return cls.create_button(
            "Page Selection",
            cls.GO_TO_PAGE_ID,
            "🔢",
            with_label,
            with_emote,
            with_disabled,
            **kwargs,
        )

    @classmethod
    def end(
        cls,
        with_label: bool = False,
        with_emote: bool = True,
        with_disabled: bool = False,
        **kwargs: object,
    ):
        return cls.create_button(
            "End", cls.END_ID, "⏹️", with_label, with_emote, with_disabled, **kwargs
        )
