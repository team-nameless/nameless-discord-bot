from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, overload

from nameless.command.music_downloader.downloader.providers import PROVIDER_CLASSES
from nameless.command.music_downloader.downloader.tagger import embed_metadata
from nameless.command.music_downloader.downloader.utils.health_check import check_service_health

if TYPE_CHECKING:
    from .providers.apple_music import (
        AppleMusicOptions,
        AppleMusicWebProvider,
    )
    from .providers.base import BaseProvider
    from .providers.deezer import DeezerOptions, DeezerWebProvider
    from .providers.qobuz_web import QobuzWebOptions, QobuzWebProvider
    from .providers.tidal_web import TidalWebOptions, TidalWebProvider
    from .providers.ytmusic import (
        YoutubeMusicWebOptions,
        YoutubeMusicWebProvider,
    )

logger = logging.getLogger("MusicDownloader")


class MusicDownloader:
    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}

    @overload
    def get_provider(
        self,
        service_name: Literal["apple"],
        options: AppleMusicOptions | None = None,
    ) -> AppleMusicWebProvider: ...
    @overload
    def get_provider(
        self,
        service_name: Literal["tidal"],
        options: TidalWebOptions | None = None,
    ) -> TidalWebProvider: ...
    @overload
    def get_provider(
        self,
        service_name: Literal["deezer"],
        options: DeezerOptions | None = None,
    ) -> DeezerWebProvider: ...
    @overload
    def get_provider(
        self,
        service_name: Literal["qobuz"],
        options: QobuzWebOptions | None = None,
    ) -> QobuzWebProvider: ...
    @overload
    def get_provider(
        self,
        service_name: Literal["youtube"],
        options: YoutubeMusicWebOptions | None = None,
    ) -> YoutubeMusicWebProvider: ...
    @overload
    def get_provider(self, service_name: str, options: Any = None) -> BaseProvider: ...

    def get_provider(self, service_name: str, options: Any = None) -> BaseProvider:
        if service_name in self._providers:
            provider = self._providers[service_name]
            if not check_service_health(provider.manifest):
                raise RuntimeError(f"service {service_name} is unhealthy/unavailable")
            return provider

        cls = PROVIDER_CLASSES.get(service_name)
        if not cls:
            raise ValueError(f"unknown service name: {service_name}")

        provider = cls(options) if options else cls()
        if not check_service_health(provider.manifest):
            raise RuntimeError(f"service {service_name} is unhealthy/unavailable")

        self._providers[service_name] = provider
        return provider

    def resolve_url(self, url: str) -> dict[str, Any] | None:
        matched_service = None
        for service in PROVIDER_CLASSES:
            try:
                provider = self.get_provider(service)
                url_handler = provider.manifest.get("urlHandler", {})
                if url_handler.get("enabled", False):
                    patterns = url_handler.get("patterns", [])
                    if any(pat in url for pat in patterns):
                        matched_service = service
                        break
            except Exception as e:
                logger.warning("failed to check url patterns for %s: %s", service, e)

        if not matched_service and ("spotify.com" in url or "spotify:" in url):
            matched_service = "spoti"

        if not matched_service:
            logger.warning("no registered service handler matched URL: %s", url)
            return None

        provider = self.get_provider(matched_service)
        res = provider.resolve_url(url)

        if not res or res.get("success") is False:
            err = res.get("error") if res else "unknown error"
            raise ValueError(f"failed to parse URL with service {matched_service}: {err}")

        res_type = res.get("type")
        if res_type == "track" and "track" in res:
            tracks = [res["track"]]
            name = res["track"].get("name", "")
            cover_url = res["track"].get("cover_url", "")
        elif res_type in ("album", "playlist"):
            tracks = res.get("tracks", [])
            name = res.get("name", "")
            cover_url = res.get("cover_url", "")
        elif res_type == "artist" and "artist" in res:
            tracks = res["artist"].get("albums", [])
            name = res["artist"].get("name", "")
            cover_url = res["artist"].get("image_url", "")
        else:
            raise ValueError(f"unsupported response type from handleUrl: {res_type}")

        # TODO: static typing
        std_tracks = []
        for t in tracks:
            std_t = {
                "id": t.get("id"),
                "title": t.get("name") or t.get("title", ""),
                "artists": t.get("artists", ""),
                "album": t.get("album_name") or t.get("album", ""),
                "album_artist": t.get("album_artist", ""),
                "cover_url": t.get("cover_url") or t.get("images", ""),
                "release_date": t.get("release_date", ""),
                "track_number": t.get("track_number", 0),
                "disc_number": t.get("disc_number", 1),
                "isrc": t.get("isrc", ""),
                "duration_ms": t.get("duration_ms", 0),
                "copyright": t.get("copyright", ""),
                "service": matched_service,
            }
            std_tracks.append(std_t)

        return {
            "type": res_type,
            "service": matched_service,
            "name": name,
            "cover_url": cover_url,
            "tracks": std_tracks,
        }

    def search_tracks(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        provider = self.get_provider("spoti")
        results = provider.search_tracks(query, limit)

        std_tracks = []
        for t in results:
            if t.get("item_type") != "track":
                continue
            std_t = {
                "id": t.get("id"),
                "title": t.get("name") or t.get("title", ""),
                "artists": t.get("artists", ""),
                "album": t.get("album_name") or t.get("album", ""),
                "album_artist": t.get("album_artist", ""),
                "cover_url": t.get("cover_url") or t.get("images", ""),
                "release_date": t.get("release_date", ""),
                "track_number": t.get("track_number", 0),
                "disc_number": t.get("disc_number", 1),
                "isrc": t.get("isrc", ""),
                "duration_ms": t.get("duration_ms", 0),
                "copyright": t.get("copyright", ""),
                "service": "spoti",
            }
            std_tracks.append(std_t)
        return std_tracks

    def download_track(
        self,
        track_meta: dict[str, Any],
        target_service: str,
        output_dir: str,
        quality: str = "LOSSLESS",
        progress_cb: Any = None,
    ) -> dict[str, Any]:
        provider = self.get_provider(target_service)

        # enrich track metadata using the source provider if possible
        source_service: str = track_meta.get("service", "")
        if source_service:
            try:
                source_provider = self.get_provider(source_service)
                enriched_meta = source_provider.enrich_track(track_meta)
                track_meta = {**track_meta, **enriched_meta}
            except Exception as e:
                logger.warning("failed to enrich track: %s", e)

        # resolve track ID on target service
        if str(track_meta["id"]).startswith(f"{target_service}:"):
            track_id = track_meta["id"]
        else:
            options = {
                "duration_ms": track_meta.get("duration_ms") or 0,
            }
            target_id_key = f"{target_service}_id"
            if target_id_key in track_meta:
                options[target_id_key] = track_meta[target_id_key]

            resolved_id = provider.check_availability(
                isrc=track_meta.get("isrc") or "",
                title=track_meta["title"],
                artists=track_meta["artists"],
                options=options,
            )
            if not resolved_id:
                raise RuntimeError(f"track is not available on {target_service}")
            track_id = resolved_id

        # build output path
        clean_title = "".join(c for c in track_meta["title"] if c not in r'<>:"/\|?*').strip()
        clean_artist = "".join(c for c in track_meta["artists"] if c not in r'<>:"/\|?*').strip()
        filename_base = f"{clean_title} - {clean_artist}"
        if len(filename_base) > 180:
            filename_base = filename_base[:180].strip()

        temp_dest = Path(output_dir) / f"{filename_base}.flac"  # placeholder extension
        temp_dest.parent.mkdir(parents=True, exist_ok=True)

        # execute download via JS extension
        provider.set_progress_callback(progress_cb)
        res = provider.download_track(track_id, quality, str(temp_dest))

        if not res or not res.get("success"):
            err = res.get("error_message") if res else "unknown error"
            raise RuntimeError(f"download failed: {err}")

        actual_path = res["file_path"]

        codec = (res.get("audio_codec") or res.get("actual_audio_codec") or "").lower()

        requires_conversion = (
            res.get("requires_container_conversion") is True or res.get("requiresContainerConversion") is True
        )
        if not requires_conversion:
            capabilities = provider.manifest.get("capabilities", {})
            requires_native = capabilities.get("requiresNativeContainerConversion", False)
            if requires_native:
                lossy_codecs = {"aac", "eac3", "ac3", "ac4", "mp3", "opus", "m4a", "mp4a"}
                is_lossy = any(lc in codec for lc in lossy_codecs) if codec else False
                if not is_lossy:
                    requires_conversion = True

        if requires_conversion:
            flac_path = str(Path(actual_path).with_suffix(".flac"))
            # use stream copy if input is already flac, otherwise transcode
            cmd = ["ffmpeg", "-y", "-i", actual_path]
            if codec == "flac":
                cmd.extend(["-c:a", "copy"])
            else:
                cmd.extend(["-c:a", "flac"])
            cmd.extend(["-vn", flac_path])

            try:
                subprocess.run(  # noqa: S603
                    cmd,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                Path(actual_path).unlink(missing_ok=True)
                actual_path = flac_path
            except Exception as e:
                logger.warning("failed to convert container for %s: %s", actual_path, e)

        # embed metadata
        embed_metadata(actual_path, track_meta)

        return {"success": True, "file_path": actual_path}
