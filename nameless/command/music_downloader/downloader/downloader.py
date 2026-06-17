from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast, overload

from nameless.command.music_downloader.downloader.providers import PROVIDER_CLASSES
from nameless.command.music_downloader.downloader.tagger import embed_metadata
from nameless.command.music_downloader.downloader.utils.health_check import check_service_health
from nameless.command.music_downloader.lyrics import get_lyrics

if TYPE_CHECKING:
    from collections.abc import Mapping

    from nameless.command.music_downloader import TrackMetadata

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

    def normalize_track_metadata(self, track: Mapping[str, Any]) -> TrackMetadata:
        if track.get("_is_normalized"):
            return cast("TrackMetadata", track)

        title = track.get("name") or track.get("title", "")
        artists = track.get("artists", "")
        if title == "Loading..." and "enriched_title" in track:
            title = track["enriched_title"]
        if not artists and "enriched_artist" in track:
            artists = track["enriched_artist"]

        return {
            "id": track.get("id", ""),
            "title": title,
            "artists": artists,
            "album": track.get("album_name") or track.get("album", ""),
            "album_artist": track.get("album_artist", ""),
            "cover_url": track.get("cover_url") or track.get("images", ""),
            "release_date": track.get("release_date", ""),
            "track_number": track.get("track_number", 0),
            "disc_number": track.get("disc_number", 1),
            "isrc": track.get("isrc", ""),
            "duration_ms": track.get("duration_ms", 0),
            "copyright": track.get("copyright", ""),
            "service": track.get("service", ""),
            "enriched_title": track.get("enriched_title", ""),
            "enriched_artist": track.get("enriched_artist", ""),
            "deezer_id": track.get("deezer_id", ""),
            "spotify_id": track.get("spotify_id", ""),
            "tidal_id": track.get("tidal_id", ""),
            "qobuz_id": track.get("qobuz_id", ""),
            "external_links": track.get("external_links", {}),
            "_is_normalized": True,
        }

    def normalize_tracks_metadata(self, tracks: list[dict[str, Any]]) -> list[TrackMetadata]:
        return [self.normalize_track_metadata(t) for t in tracks]

    if TYPE_CHECKING:

        class _ResolveUrlResult(TypedDict):
            type: Literal["track", "album", "playlist", "artist"]
            service: str
            name: str
            cover_url: str | list[str] | dict[str, str] | None
            tracks: list[TrackMetadata]

    def resolve_url(self, url: str) -> _ResolveUrlResult | None:
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
            track_data = res["track"]
            try:
                track_data = self.normalize_track_metadata(provider.enrich_track(track_data))
            except Exception as e:
                logger.warning("failed to enrich track: %s", e)
            tracks = [track_data]
            name = track_data.get("name") or track_data.get("title", "")
            cover_url = track_data.get("cover_url") or track_data.get("thumbnail", "")

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

        return {
            "type": res_type,
            "service": matched_service,
            "name": name,
            "cover_url": cover_url,
            "tracks": self.normalize_tracks_metadata(tracks),  # type: ignore  # might want to add validation here.
        }

    def search_tracks(self, query: str, limit: int = 20) -> list[TrackMetadata]:
        provider = self.get_provider("spoti")
        results = provider.search_tracks(query, limit)

        std_tracks: list[TrackMetadata] = []
        for t in results:
            if t.get("item_type") != "track":
                continue
            std_t: TrackMetadata = self.normalize_track_metadata(t)
            std_tracks.append(std_t)
        return std_tracks

    def download_track(
        self,
        track_meta: TrackMetadata,
        target_service: str,
        output_dir: str,
        quality: str = "LOSSLESS",
        progress_cb: Any = None,
    ) -> dict[str, Any]:
        provider = self.get_provider(target_service)
        source_service: str = track_meta.get("service", "")
        if source_service:
            try:
                source_provider = self.get_provider(source_service)
                track_meta = self.normalize_track_metadata(source_provider.enrich_track(track_meta))
            except Exception as e:
                logger.warning("failed to enrich track: %s", e)

        # resolve track ID on target service
        if str(track_meta["id"]).startswith(f"{target_service}:") or track_meta.get("service") == target_service:
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

        provider.set_progress_callback(progress_cb)
        res = provider.download_track(track_id, quality, str(temp_dest))

        if not res or not res.get("success"):
            err = res.get("error_message") if res else "unknown error"
            raise RuntimeError(f"download failed: {err}")

        actual_path = res["file_path"]

        # remux webm to ogg container if needed
        actual_path_obj = Path(actual_path)
        if actual_path_obj.exists() and actual_path_obj.suffix.lower() == ".opus":
            try:
                with actual_path_obj.open("rb") as f:
                    magic = f.read(4)
                if magic == b"\x1aE\xdf\xa3":
                    temp_ogg = actual_path_obj.with_suffix(".temp.ogg")
                    cmd = ["ffmpeg", "-y", "-i", str(actual_path_obj), "-c:a", "copy", "-vn", str(temp_ogg)]
                    subprocess.run(  # noqa: S603
                        cmd,
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    actual_path_obj.unlink()
                    temp_ogg.rename(actual_path_obj)
            except Exception as e:
                logger.warning("failed to remux webm to ogg container: %s", e)

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

        if "lyrics" not in track_meta:
            lyrics = get_lyrics(track_meta["title"], track_meta["artists"])
            if lyrics:
                track_meta["lyrics"] = lyrics
                track_meta["lyrics_lrc"] = lyrics
        embed_metadata(actual_path, track_meta)

        return {"success": True, "file_path": actual_path}
