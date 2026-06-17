from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict, cast

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from pyrogram import Client

from nameless.command.music.ui.track_selector import TrackSelector
from nameless.command.music_downloader.downloader.downloader import MusicDownloader
from nameless.command.music_downloader.enums import StatusState
from nameless.command.music_downloader.helpers import (
    cleanup_download_files,
    package_downloaded_files,
    resolve_collection_flags,
    upload_via_external_provider,
)
from nameless.config import nameless_config

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from nameless.nameless import Nameless


class TrackMetadata(TypedDict):
    id: str
    title: str
    artists: str
    album: str
    album_artist: str
    cover_url: str
    isrc: str
    duration_ms: int
    release_date: NotRequired[str]
    track_number: NotRequired[int]
    disc_number: NotRequired[int]
    copyright: NotRequired[str]
    service: NotRequired[str]
    enriched_title: NotRequired[str]
    enriched_artist: NotRequired[str]
    deezer_id: NotRequired[str]
    spotify_id: NotRequired[str]
    tidal_id: NotRequired[str]
    qobuz_id: NotRequired[str]
    external_links: NotRequired[dict[str, str]]
    _is_normalized: NotRequired[bool]


@dataclass(eq=False, repr=False, slots=True)
class Status:
    _total_tracks: int = 0
    _downloaded_tracks: int = 0
    _failed_tracks: int = 0

    _fetching_metadata_state: StatusState = StatusState.NOT_STARTED
    _resolving_tracks_state: StatusState = StatusState.NOT_STARTED
    _downloading_state: StatusState = StatusState.NOT_STARTED
    _download_progress: float = 0.0

    _uploading_state: StatusState = StatusState.NOT_STARTED
    _upload_progress: float = 0.0
    _download_url: str = ""
    _provider: str = "catbox"

    _current_track_title: str = ""
    _current_track_artists: str = ""
    _current_service: str = ""

    _dirty: bool = False

    def _mark_dirty(self) -> None:
        self._dirty = True

    @property
    def provider(self) -> str:
        return self._provider

    @provider.setter
    def provider(self, value: str) -> None:
        if self._provider != value:
            self._provider = value
            self._mark_dirty()

    @property
    def download_url(self) -> str:
        return self._download_url

    @download_url.setter
    def download_url(self, value: str) -> None:
        if self._download_url != value:
            self._download_url = value
            self._mark_dirty()

    @property
    def current_track_title(self) -> str:
        return self._current_track_title

    @current_track_title.setter
    def current_track_title(self, value: str) -> None:
        if self._current_track_title != value:
            self._current_track_title = value
            self._mark_dirty()

    @property
    def current_track_artists(self) -> str:
        return self._current_track_artists

    @current_track_artists.setter
    def current_track_artists(self, value: str) -> None:
        if self._current_track_artists != value:
            self._current_track_artists = value
            self._mark_dirty()

    @property
    def current_service(self) -> str:
        return self._current_service

    @current_service.setter
    def current_service(self, value: str) -> None:
        if self._current_service != value:
            self._current_service = value
            self._mark_dirty()

    def _update_progress(self, state_attr: str, progress_attr: str, progress: float) -> None:
        state = getattr(self, state_attr)
        new_state = state
        new_progress = progress

        if state != StatusState.STARTED and progress > 0.0:
            new_state = StatusState.STARTED
        if progress >= 100.0:
            if state_attr != "_downloading_state":
                new_state = StatusState.COMPLETED
            new_progress = 100.0

        if state != new_state or getattr(self, progress_attr) != new_progress:
            setattr(self, state_attr, new_state)
            setattr(self, progress_attr, new_progress)
            self._mark_dirty()

    @property
    def total_tracks(self) -> int:
        return self._total_tracks

    @total_tracks.setter
    def total_tracks(self, value: int) -> None:
        if self._total_tracks != value:
            self._total_tracks = value
            self._mark_dirty()

    @property
    def downloaded_tracks(self) -> int:
        return self._downloaded_tracks

    @downloaded_tracks.setter
    def downloaded_tracks(self, value: int) -> None:
        if self._downloaded_tracks != value:
            self._downloaded_tracks = value
            self._mark_dirty()

    @property
    def failed_tracks(self) -> int:
        return self._failed_tracks

    @failed_tracks.setter
    def failed_tracks(self, value: int) -> None:
        if self._failed_tracks != value:
            self._failed_tracks = value
            self._mark_dirty()

    @property
    def fetching_metadata_state(self) -> StatusState:
        return self._fetching_metadata_state

    @fetching_metadata_state.setter
    def fetching_metadata_state(self, value: StatusState) -> None:
        if self._fetching_metadata_state != value:
            self._fetching_metadata_state = value
            self._mark_dirty()

    @property
    def resolving_tracks_state(self) -> StatusState:
        return self._resolving_tracks_state

    @resolving_tracks_state.setter
    def resolving_tracks_state(self, value: StatusState) -> None:
        if self._resolving_tracks_state != value:
            self._resolving_tracks_state = value
            self._mark_dirty()

    @property
    def downloading_state(self) -> StatusState:
        return self._downloading_state

    @downloading_state.setter
    def downloading_state(self, value: StatusState) -> None:
        if self._downloading_state != value:
            self._downloading_state = value
            self._mark_dirty()

    @property
    def download_progress(self) -> float:
        return self._download_progress

    @download_progress.setter
    def download_progress(self, value: float) -> None:
        self._update_progress("_downloading_state", "_download_progress", value)

    @property
    def uploading_state(self) -> StatusState:
        return self._uploading_state

    @uploading_state.setter
    def uploading_state(self, value: StatusState) -> None:
        if self._uploading_state != value:
            self._uploading_state = value
            self._mark_dirty()

    @property
    def upload_progress(self) -> float:
        return self._upload_progress

    @upload_progress.setter
    def upload_progress(self, value: float) -> None:
        self._update_progress("_uploading_state", "_upload_progress", value)

    def build_upload_progress_line(self) -> str:
        provider_names = {
            "catbox": "Catbox",
            "litterbox": "Litterbox",
            "uguu": "Uguu",
            "rokket": "Rokket",
            "telegram": "Telegram",
        }
        name = provider_names.get(self._provider, "Uploader")

        if self._uploading_state == StatusState.STARTED:
            return f"Uploading to {name}: {self._upload_progress:.1f}%"
        elif self._uploading_state == StatusState.COMPLETED:
            if self._download_url:
                urls = self._download_url.split("\n")
                if len(urls) > 1:
                    links = [f"[Link {i}]({url})" for i, url in enumerate(urls, 1)]
                    return f"Download links ({name}): " + ", ".join(links)
                return f"Download link ({name}): [Click here to download]({self._download_url})"
            return "Upload completed."
        else:
            return ""

    def build_lines(self) -> list[str]:
        lines: list[str] = []

        if self._fetching_metadata_state == StatusState.STARTED:
            lines.append("Fetching metadata...")
        elif self._fetching_metadata_state == StatusState.COMPLETED:
            lines.append("Metadata fetched.")

        if self._resolving_tracks_state == StatusState.STARTED:
            lines.append("Resolving tracks...")
        elif self._resolving_tracks_state == StatusState.COMPLETED:
            lines.append("Tracks resolved.")

        if self._downloading_state == StatusState.STARTED:
            service_label = f" via `{self._current_service.upper()}`" if self._current_service else ""
            if self._current_track_title:
                lines.append(
                    f"Downloading: **{self._current_track_title}** - {self._current_track_artists}{service_label}"
                )
            lines.append(f"Progress: {self._downloaded_tracks}/{self._total_tracks} ({self._download_progress:.1f}%)")
        elif self._downloading_state == StatusState.COMPLETED:
            lines.append(f"Download completed: {self._downloaded_tracks} succeeded, {self._failed_tracks} failed.")

        upload_line = self.build_upload_progress_line()
        if upload_line:
            lines.append(upload_line)

        return lines


embed_controller_var: ContextVar[DownloadEmbedController | None] = ContextVar("embed_controller", default=None)


class DownloadEmbedController:
    def __init__(self, ctx: commands.Context[Nameless], title: str | None = None, provider: str = "catbox"):
        self.ctx = ctx
        self.title = title
        self.message: discord.Message | None = None
        self.status = Status()
        self.status.provider = provider
        self._update_lock = asyncio.Lock()
        self._last_download_update = 0.0
        self._last_update_time = 0.0

    def _build_embed(self) -> discord.Embed:
        lines: list[str] = self.status.build_lines()

        return discord.Embed(
            title=self.title or f"Total Tracks: {self.status.total_tracks}",
            description="\n".join(lines) if lines else "Preparing...",
            color=discord.Color.blue(),
        )

    async def _flush_status(self, force: bool = False) -> None:
        if not force and time.time() - self._last_update_time < 1.0:
            return

        if not self.message or not self.status._dirty:
            return

        async with self._update_lock:
            if not self.message or not self.status._dirty:
                return

            self.status._dirty = False
            await self.message.edit(embed=self._build_embed())
            self._last_update_time = time.time()

    async def _auto_flush(self, interval: float) -> None:
        if interval <= 0:
            return
        try:
            while True:
                await asyncio.sleep(interval)
                await self._flush_status()
        except asyncio.CancelledError:
            return

    async def update_title(self, title: str) -> None:
        self.title = title
        if self.message:
            await self.message.edit(embed=self._build_embed())

    @contextlib.asynccontextmanager
    async def status_context(
        self,
        *,
        auto_flush: bool = False,
        interval: float = 2.0,
    ) -> AsyncIterator[Status]:
        task: asyncio.Task[None] | None = None
        if auto_flush:
            task = asyncio.create_task(self._auto_flush(interval))
        try:
            yield self.status
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await self._flush_status(force=True)

    async def set_download_progress(self, pct: float, force: bool = False) -> None:
        self.status.download_progress = pct
        now = time.time()
        if force or pct >= 100.0 or now - self._last_download_update >= 3.0:
            self._last_download_update = now
            await self._flush_status(force=force or pct >= 100.0)

    async def send_initial(self) -> None:
        self.message = await self.ctx.send(embed=self._build_embed())

    async def set_failed(self, error_message: str) -> None:
        if self.message:
            await self.message.edit(content=error_message, embed=None)
        else:
            await self.ctx.send(content=error_message)


@dataclass(eq=False, repr=False, slots=True)
class DownloadTrackOption:
    metadata: TrackMetadata
    title: str
    author: str
    length: int | None

    @classmethod
    def from_metadata(cls, metadata: TrackMetadata) -> DownloadTrackOption:
        return cls(
            metadata=metadata,
            title=metadata["title"],
            author=metadata["artists"],
            length=metadata["duration_ms"] or None,
        )


class DownloadCommandError(commands.CommandError):
    pass


class MusicDownloaderCommand(commands.Cog):
    def __init__(self, bot: Nameless):
        self.bot = bot
        self.logger = logging.getLogger("MusicDownloaderCommand")
        self._download_root = Path("Downloads")
        self._session: aiohttp.ClientSession | None = None

        tg_config = nameless_config.telegram
        self._tg_client = None
        if tg_config and tg_config.enabled and tg_config.api_id and tg_config.api_hash and tg_config.bot_token:
            self._tg_client = Client(
                name="namelessMusic",
                api_id=tg_config.api_id,
                api_hash=tg_config.api_hash,
                bot_token=tg_config.bot_token,
                plugins=None,
                workdir="Downloads",
                in_memory=True,
                no_updates=True,
            )

    async def cog_load(self) -> None:
        if self._tg_client is not None:
            await self._tg_client.start()
            self.logger.info("Telegram uploader client started.")

    async def cog_unload(self) -> None:
        if self._tg_client is not None:
            await self._tg_client.stop()
            self.logger.info("Telegram uploader client stopped.")

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _get_output_dir(self, ctx: commands.Context[Nameless]) -> Path:
        return self._download_root / str(ctx.author.id)

    async def _resolve_metadata(
        self,
        downloader: MusicDownloader,
        query: str,
        controller: DownloadEmbedController,
    ) -> tuple[str, list[TrackMetadata], dict[str, str]]:
        try:
            async with controller.status_context(auto_flush=True, interval=2.0) as status:
                status.fetching_metadata_state = StatusState.STARTED
                if query.startswith(("http://", "https://")) or "spotify:" in query or "tidal:" in query:
                    res = await asyncio.to_thread(downloader.resolve_url, query)
                    if not res:
                        raise ValueError("unsupported URL")
                    collection_name = res["name"]
                    tracks_data = cast(
                        "list[TrackMetadata]", res["tracks"]
                    )  # upstream already normalized, might add stronger type hint in upper level
                    info = {"type": res["type"], "service": res["service"]}
                else:
                    tracks_data = await asyncio.to_thread(downloader.search_tracks, query)
                    collection_name = f"Search: {query}"
                    info = {"type": "playlist", "service": "spoti"}

                tracks = [TrackMetadata(**td) for td in tracks_data]

                status.total_tracks = len(tracks)
                status.fetching_metadata_state = StatusState.COMPLETED
            return collection_name, tracks, info
        except Exception as exc:
            self.logger.error("Metadata fetch failed.", exc_info=exc)
            await controller.set_failed("Failed to resolve the provided URL.")
            raise DownloadCommandError("Failed to resolve the provided URL.") from exc

    async def _resolve_tracks(
        self,
        downloader: MusicDownloader,
        tracks: list[TrackMetadata],
        query: str,
        controller: DownloadEmbedController,
    ) -> list[TrackMetadata]:
        async with controller.status_context() as status:
            status.resolving_tracks_state = StatusState.STARTED
            status.resolving_tracks_state = StatusState.COMPLETED
        return tracks

    async def _select_tracks(
        self,
        ctx: commands.Context[Nameless],
        tracks: list[TrackMetadata],
    ) -> list[TrackMetadata]:
        selection_items = [DownloadTrackOption.from_metadata(track) for track in tracks]
        selected_items = await TrackSelector.select_tracks(
            ctx,
            selection_items,
            title="Only the first 25 tracks are available for selection." if len(selection_items) > 25 else None,
        )
        return [item.metadata for item in selected_items] if selected_items else []

    async def _run_download(
        self,
        downloader: MusicDownloader,
        selected_tracks: list[TrackMetadata],
        collection_name: str,
        info: dict[str, str],
        is_album: bool,
        is_playlist: bool,
        controller: DownloadEmbedController,
    ) -> list[TrackMetadata]:
        await controller.update_title("Downloading tracks...")
        async with controller.status_context() as status:
            status.downloading_state = StatusState.STARTED
            status.download_progress = 0.0
            status.total_tracks = len(selected_tracks)

        loop = asyncio.get_running_loop()
        failed_tracks: list[TrackMetadata] = []
        downloaded = 0
        failed = 0

        primary_service = info.get("service") or "tidal"
        if primary_service == "spoti":
            primary_service = "tidal"

        services_cascade = [primary_service] + [
            service for service in ("tidal", "qobuz", "deezer", "youtube") if service != primary_service
        ]

        for track in selected_tracks:
            async with controller.status_context() as status:
                status.downloaded_tracks = downloaded
                status.failed_tracks = failed
                status.downloading_state = StatusState.STARTED
                status.download_progress = 0.0
                status.current_track_title = track["title"]
                status.current_track_artists = track["artists"]
                status.current_service = ""

            def progress(current: int, total_bytes: int) -> None:
                pct = (current / total_bytes) * 100 if total_bytes > 0 else 0.0
                asyncio.run_coroutine_threadsafe(controller.set_download_progress(pct), loop)

            output_dir = self._get_output_dir(controller.ctx)

            success = False
            last_error = None
            for service in services_cascade:
                try:
                    self.logger.info("Attempting download of track '%s' on service: %s", track["title"], service)
                    async with controller.status_context() as status:
                        status.current_service = service

                    await asyncio.to_thread(
                        downloader.download_track,
                        track_meta=track,
                        target_service=service,
                        output_dir=str(output_dir),
                        quality="LOSSLESS",
                        progress_cb=progress,
                    )
                    success = True
                    await controller.set_download_progress(100.0, force=True)
                    break
                except Exception as e:
                    last_error = e
                    self.logger.warning("Download failed for track '%s' on %s: %s", track["title"], service, e)

            if success:
                downloaded += 1
            else:
                self.logger.error(
                    "Download failed for track '%s' on all attempted services. Last error: %s",
                    track["title"],
                    last_error,
                )
                failed_tracks.append(track)
                failed += 1

        async with controller.status_context() as status:
            status.downloaded_tracks = downloaded
            status.failed_tracks = failed
            status.downloading_state = StatusState.COMPLETED
            status.download_progress = 100.0

        return failed_tracks

    @commands.hybrid_command(name="download", aliases=["dl"])
    @app_commands.describe(
        query="The music URL or search query",
        provider="The upload provider to use (catbox, litterbox, uguu, rokket, telegram)",
    )
    async def download(
        self,
        ctx: commands.Context[Nameless],
        *,
        query: str,
        provider: Literal["catbox", "litterbox", "uguu", "rokket", "telegram"] = "catbox",
    ) -> None:
        if not query:
            raise DownloadCommandError("URL is required.")

        output_dir = self._get_output_dir(ctx)

        downloader = MusicDownloader()

        controller = DownloadEmbedController(ctx, title="Checking tracks...", provider=provider)
        await controller.send_initial()

        collection_name, tracks, info = await self._resolve_metadata(downloader, query, controller)

        if not tracks:
            await controller.set_failed("No tracks found for the provided URL.")
            return

        tracks = await self._resolve_tracks(downloader, tracks, query, controller)
        selected_tracks = await self._select_tracks(ctx, tracks)

        if not selected_tracks:
            await controller.set_failed("No tracks selected.")
            return

        is_album, is_playlist = resolve_collection_flags(info)
        failed_tracks = await self._run_download(
            downloader,
            selected_tracks,
            collection_name,
            info,
            is_album,
            is_playlist,
            controller,
        )

        failed_count = len(failed_tracks)
        success_count = len(selected_tracks) - failed_count
        async with controller.status_context() as status:
            status.downloaded_tracks = success_count
            status.failed_tracks = failed_count
            status.download_progress = 100.0

        zip_if_multiple = provider != "telegram"
        upload_paths, is_zip = await package_downloaded_files(output_dir, ctx, controller, zip_if_multiple)

        title = ("Uploading album..." if is_album else "Uploading playlist...") if is_zip else "Uploading track..."
        await controller.update_title(title)

        try:
            await upload_via_external_provider(
                self.session,
                self._tg_client,
                upload_paths,
                controller,
                provider,
                tracks=selected_tracks,
            )
            await controller.update_title("Completed")

        except Exception as exc:
            self.logger.exception("Failed to prepare upload.")
            await controller.set_failed(f"Upload failed: {exc}")
            return
        finally:
            await cleanup_download_files(output_dir, upload_paths, is_zip)


async def setup(bot: Nameless) -> None:
    await bot.add_cog(MusicDownloaderCommand(bot))
    logging.info("%s added!", __name__)


async def teardown(bot: Nameless) -> None:
    cog = bot.get_cog("MusicDownloaderCommand")
    if cog and hasattr(cog, "_session") and cog._session:  # type: ignore
        await cog._session.close()  # type: ignore
    await bot.remove_cog(MusicDownloaderCommand.__cog_name__)
    logging.warning("%s removed!", __name__)
