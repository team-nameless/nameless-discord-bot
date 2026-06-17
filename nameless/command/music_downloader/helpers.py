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

    from . import DownloadEmbedController, TrackMetadata

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
    zip_if_multiple: bool = True,
) -> tuple[list[AsyncPath], bool]:
    async_output_dir = AsyncPath(output_dir)
    files = [f async for f in async_output_dir.glob("*")]
    if not files:
        await controller.set_failed("No files found after download.")
        raise DownloadCommandError("No files found after download.")

    if len(files) > 1 and zip_if_multiple:
        zip_name = output_dir.name or "album"
        temp_dir = Path(tempfile.gettempdir())
        zip_path_no_ext = temp_dir / f"{zip_name}_{ctx.author.id}"

        def create_zip() -> str:
            return shutil.make_archive(str(zip_path_no_ext), "zip", output_dir)

        full_zip_path = await asyncio.to_thread(create_zip)
        return [AsyncPath(full_zip_path)], True

    sorted_files = sorted(files, key=lambda p: p.name)
    return sorted_files, False


async def upload_via_external_provider(
    session: aiohttp.ClientSession,
    tg_client: Client | None,
    upload_paths: list[AsyncPath],
    controller: DownloadEmbedController,
    provider: Literal["catbox", "litterbox", "uguu", "rokket", "telegram"],
    tracks: list[TrackMetadata] | None = None,
) -> str | None:
    factory = UPLOADER_REGISTRY.get(provider)
    if not factory:
        raise ValueError(f"unknown upload provider: {provider}")

    chat_id = nameless_config.telegram.chat_id if tg_client else None
    uploader = factory(session=session, tg_client=tg_client, chat_id=chat_id)

    # validate all files in list
    total_size = 0
    max_size_mb = uploader.get_max_file_size()

    for path in upload_paths:
        file_size = (await path.stat()).st_size
        total_size += file_size

        if max_size_mb is not None:
            file_size_mb = file_size / (1024 * 1024)
            if file_size_mb > max_size_mb:
                raise DownloadCommandError(
                    f"File size ({file_size_mb:.1f}MB) exceeds the maximum limit "
                    f"for {uploader.get_service_name()} ({max_size_mb}MB)."
                )

        extension = path.suffix
        if not uploader.is_supported_file_extension(extension):
            raise DownloadCommandError(
                f"File extension '{extension}' is not supported by {uploader.get_service_name()}."
            )

    urls: list[str] = []

    async with controller.status_context(auto_flush=True, interval=2.0) as status:
        status.provider = provider
        status.uploading_state = StatusState.STARTED
        status.upload_progress = 0.0

    total_uploaded = 0
    last_update = 0.0

    for i, path in enumerate(upload_paths, 1):
        if len(upload_paths) > 1:
            title = f"Uploading tracks ({i}/{len(upload_paths)})..."
            await controller.update_title(title)

        file_size = (await path.stat()).st_size
        file_uploaded = 0

        async def on_ready(url: str) -> None:
            urls.append(url)
            async with controller.status_context() as status:
                status.download_url = "\n".join(urls)

        async def on_progress(sent: int, total: int) -> None:
            nonlocal last_update, file_uploaded, total_uploaded
            diff = sent - file_uploaded
            file_uploaded = sent
            total_uploaded += diff

            pct = (total_uploaded / total_size) * 100 if total_size > 0 else 0.0

            now = time.time()
            if now - last_update < 3.0 and total_uploaded != total_size:
                controller.status.upload_progress = pct
                return

            last_update = now
            async with controller.status_context() as status:
                status.upload_progress = pct

        metadata_dict = None
        if tracks:
            matched = None
            stem = Path(path).stem
            for track in tracks:
                clean_title = "".join(c for c in track["title"] if c not in r'<>:"/\|?*').strip()
                clean_artist = "".join(c for c in track["artists"] if c not in r'<>:"/\|?*').strip()
                filename_base = f"{clean_title} - {clean_artist}"
                if len(filename_base) > 180:
                    filename_base = filename_base[:180].strip()
                if filename_base == stem:
                    matched = track
                    break

            if matched:
                metadata_dict = {
                    "title": matched["title"],
                    "artists": matched["artists"],
                    "duration_ms": matched["duration_ms"],
                    "cover_url": matched["cover_url"],
                }

        await uploader.upload_file(
            str(path),
            on_ready=on_ready,
            on_progress=on_progress,
            metadata=metadata_dict,
        )

    async with controller.status_context() as status:
        status.uploading_state = StatusState.COMPLETED
        status.upload_progress = 100.0
        status.download_url = "\n".join(urls)

    return "\n".join(urls)


async def cleanup_download_files(
    output_dir: Path,
    upload_paths: list[AsyncPath],
    is_zip: bool,
) -> None:
    try:
        if is_zip:
            for path in upload_paths:
                if await path.exists():
                    await path.unlink()
        async_output_dir = AsyncPath(output_dir)
        if await async_output_dir.exists():
            await asyncio.to_thread(shutil.rmtree, output_dir, ignore_errors=True)
    except Exception as e:
        logger.error("Failed to clean up download files: %s", e)
