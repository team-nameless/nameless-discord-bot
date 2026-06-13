from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from nameless.command.music_downloader.uploader.catbox.catbox import CatboxUploader
from nameless.command.music_downloader.uploader.catbox.litterbox import LitterboxUploader
from nameless.command.music_downloader.uploader.pomf.pomf import PomfUploader, ServerConfig
from nameless.command.music_downloader.uploader.telegram.telegram import TelegramUploader

if TYPE_CHECKING:
    import aiohttp
    from pyrogram import Client

    from .base import BaseUploader

UploaderFactory = Callable[..., "BaseUploader"]


def create_catbox(session: aiohttp.ClientSession, **kwargs: Any) -> CatboxUploader:
    return CatboxUploader(session=session)


def create_litterbox(session: aiohttp.ClientSession, **kwargs: Any) -> LitterboxUploader:
    return LitterboxUploader(session=session)


def create_uguu(session: aiohttp.ClientSession, **kwargs: Any) -> PomfUploader:
    return PomfUploader(config=ServerConfig.uguu_config(), session=session)


def create_rokket(session: aiohttp.ClientSession, **kwargs: Any) -> PomfUploader:
    return PomfUploader(config=ServerConfig.rokket_config(), session=session)


def create_telegram(tg_client: Client | None, chat_id: int | str, **kwargs: Any) -> TelegramUploader:
    if not tg_client:
        raise RuntimeError("Telegram client is not configured.")
    return TelegramUploader(tg_client, chat_id)


UPLOADER_REGISTRY: dict[str, UploaderFactory] = {
    "catbox": create_catbox,
    "litterbox": create_litterbox,
    "uguu": create_uguu,
    "rokket": create_rokket,
    "telegram": create_telegram,
}
