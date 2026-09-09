from __future__ import annotations

import logging
from io import BytesIO
from typing import TYPE_CHECKING, Any, override

import anyio
from pyrogram.enums import MessagesFilter

from nameless.command.music_downloader.uploader.base import BaseUploader

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Awaitable, Callable

    import aiohttp
    from pyrogram import Client
    from pyrogram.types import Message


class TelegramUploader(BaseUploader):
    def __init__(self, session: aiohttp.ClientSession, client: Client, chat_id: int | str) -> None:
        self.session = session
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
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        path = anyio.Path(filepath)
        path_str = str(path)

        async def progress_callback(current: int, total: int, *args: object) -> None:
            if on_progress is not None:
                await on_progress(current, total)

        if path_str.endswith(".zip"):
            # error occurs properly for when we using a bot account
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
                send_kwargs = {
                    "chat_id": self.chat_id,
                    "audio": path_str,
                    "progress": progress_callback,
                }
                if metadata:
                    if metadata.get("title"):
                        send_kwargs["title"] = metadata["title"]
                    if metadata.get("artists"):
                        send_kwargs["performer"] = metadata["artists"]
                    if metadata.get("duration_ms"):
                        send_kwargs["duration"] = int(metadata["duration_ms"] / 1000)
                    cover_url = metadata.get("cover_url")
                    if cover_url:
                        headers = {
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
                            )
                        }
                        r = await self.session.get(cover_url, headers=headers)
                        if r.status == 200:
                            cover_bytes = BytesIO(await r.read())
                            send_kwargs["thumb"] = cover_bytes  # type: ignore

                msg = await self.client.send_audio(**send_kwargs)  # type: ignore

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
