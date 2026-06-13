from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from anyio import Path as AsyncPath

from nameless.command.music_downloader.enums import StatusState
from nameless.command.music_downloader.exceptions import DownloadCommandError
from nameless.command.music_downloader.uploader import UPLOADER_REGISTRY
from nameless.config import nameless_config

if TYPE_CHECKING:
    import aiohttp
    from discord.ext import commands
    from pyrogram import Client

    from nameless.nameless import Nameless

    from . import DownloadEmbedController

logger = logging.getLogger("MusicDownloaderHelpers")


def resolve_collection_flags(info: dict[str, str]) -> tuple[bool, bool]:
    collection_type = info.get("type", "")
    is_album = collection_type == "album"
    is_playlist = collection_type in {"playlist", "artist", "artist_discography"}
    return is_album, is_playlist


async def package_downloaded_files(
    output_dir: Path,
    ctx: commands.Context[Nameless],
    controller: DownloadEmbedController,
) -> tuple[AsyncPath, bool]:
    async_output_dir = AsyncPath(output_dir)
    files = [f async for f in async_output_dir.glob("*")]
    if not files:
        await controller.set_failed("No files found after download.")

        raise DownloadCommandError("No files found after download.")

    if len(files) > 1:
        zip_name = output_dir.name or "album"
        temp_dir = Path(tempfile.gettempdir())
        zip_path_no_ext = temp_dir / f"{zip_name}_{ctx.author.id}"

        def create_zip() -> str:
            return shutil.make_archive(str(zip_path_no_ext), "zip", output_dir)

        full_zip_path = await asyncio.to_thread(create_zip)
        return AsyncPath(full_zip_path), True

    return AsyncPath(files[0]), False


async def upload_via_external_provider(
    session: aiohttp.ClientSession,
    tg_client: Client | None,
    upload_path: AsyncPath,
    file_size: int,
    controller: DownloadEmbedController,
    provider: Literal["catbox", "litterbox", "uguu", "rokket", "telegram"],
) -> str | None:
    factory = UPLOADER_REGISTRY.get(provider)
    if not factory:
        raise ValueError(f"unknown upload provider: {provider}")

    chat_id = nameless_config.telegram.chat_id if tg_client else None
    uploader = factory(session=session, tg_client=tg_client, chat_id=chat_id)

    max_size_mb = uploader.get_max_file_size()
    if max_size_mb is not None:
        file_size_mb = file_size / (1024 * 1024)
        if file_size_mb > max_size_mb:
            raise DownloadCommandError(
                f"File size ({file_size_mb:.1f}MB) exceeds the maximum limit "
                f"for {uploader.get_service_name()} ({max_size_mb}MB)."
            )

    extension = upload_path.suffix
    if not uploader.is_supported_file_extension(extension):
        raise DownloadCommandError(f"File extension '{extension}' is not supported by {uploader.get_service_name()}.")

    async def on_ready(url: str) -> None:
        async with controller.status_context() as status:
            status.download_url = url

    last_update = 0.0

    async def on_progress(sent: int, total: int) -> None:
        nonlocal last_update
        pct = (sent / total) * 100 if total > 0 else 0.0

        now = time.time()
        if now - last_update < 3.0 and sent != total:
            controller.status.upload_progress = pct
            return

        last_update = now
        async with controller.status_context() as status:
            status.upload_progress = pct

    async with controller.status_context(auto_flush=True, interval=2.0) as status:
        status.provider = provider
        status.uploading_state = StatusState.STARTED
        status.upload_progress = 0.0

    url = await uploader.upload_file(
        str(upload_path),
        on_ready=on_ready,
        on_progress=on_progress,
    )
    async with controller.status_context() as status:
        status.uploading_state = StatusState.COMPLETED
    return url


async def cleanup_download_files(
    output_dir: Path,
    upload_path: AsyncPath,
    is_zip: bool,
) -> None:
    try:
        if is_zip and await upload_path.exists():
            await upload_path.unlink()
        async_output_dir = AsyncPath(output_dir)
        if await async_output_dir.exists():
            await asyncio.to_thread(shutil.rmtree, output_dir, ignore_errors=True)
    except Exception as e:
        logger.error("Failed to clean up download files: %s", e)
