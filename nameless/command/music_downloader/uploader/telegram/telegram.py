from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

import anyio
from pyrogram.enums import MessagesFilter

from nameless.command.music_downloader.uploader.base import BaseUploader

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Awaitable, Callable

    from pyrogram import Client
    from pyrogram.types import Message


class TelegramUploader(BaseUploader):
    def __init__(self, client: Client, chat_id: int | str) -> None:
        self.client = client
        self.chat_id = chat_id
        self.logger = logging.getLogger("TelegramUploader")

    # endpoint only available for user accounts, not bots. careful when using
    async def check_file_exists(self, filename: str) -> Message | None:
        path = anyio.Path(filename)
        if filename.endswith(".zip"):
            msg: Message | None = None
            async for msg in self.client.search_messages(
                self.chat_id,
                query=path.stem,
                filter=MessagesFilter.DOCUMENT,
            ):  # type: ignore  # upstream has wrong type hint for search_messages
                if (
                    msg
                    and msg.document
                    and (msg.document.file_name in path.name or path.stem in msg.document.file_name)
                ):
                    self.logger.info("file %s already exists in Telegram, skipping upload", filename)
                    return msg
        else:
            async for msg in self.client.search_messages(
                self.chat_id,
                query=path.stem,
                filter=MessagesFilter.AUDIO,
            ):  # type: ignore
                if msg and msg.audio and (msg.audio.file_name in path.name or path.stem in msg.audio.file_name):
                    self.logger.info("file %s already exists in Telegram, skipping upload", filename)
                    return msg

    @override
    async def upload_file(
        self,
        filepath: str | anyio.Path | pathlib.Path,
        *,
        on_ready: Callable[[str], Awaitable[None]],
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> str | None:
        path = anyio.Path(filepath)
        path_str = str(path)

        async def progress_callback(current: int, total: int, *args: object) -> None:
            if on_progress is not None:
                await on_progress(current, total)

        # error occurs properly for when we using a bot account
        if path_str.endswith(".zip"):
            try:
                msg = await self.check_file_exists(path_str)
            except Exception:
                msg = None

            if msg is None:
                msg = await self.client.send_document(
                    chat_id=self.chat_id,
                    document=path_str,
                    progress=progress_callback,
                )
        else:
            try:
                msg = await self.check_file_exists(path_str)
            except Exception:
                msg = None

            if msg is None:
                msg = await self.client.send_audio(
                    chat_id=self.chat_id,
                    audio=path_str,
                    progress=progress_callback,
                )

        if msg is not None and msg.link:
            await on_ready(msg.link)
            return msg.link
        return None

    @override
    def get_service_name(self) -> str:
        return "Telegram"

    @override
    def get_max_file_size(self) -> int | None:
        return 2000
