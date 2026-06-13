import base64
import logging
from pathlib import Path
from typing import Any

import requests
from mutagen.flac import FLAC, Picture

# known issue: https://github.com/quodlibet/mutagen/issues/647
from mutagen.id3 import ID3, TXXX, USLT  # pyright: ignore[reportPrivateImportUsage]
from mutagen.id3._frames import APIC
from mutagen.mp3 import EasyMP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus

logger = logging.getLogger("Tagger")


def tag_flac(file_path: str, metadata: dict[str, Any], cover_bytes: bytes | None = None) -> None:
    audio = FLAC(file_path)
    audio.clear_pictures()

    audio["title"] = metadata.get("title", "")
    audio["artist"] = metadata.get("artists", "")
    audio["album"] = metadata.get("album", "")
    audio["albumartist"] = metadata.get("album_artist", "")
    audio["tracknumber"] = str(metadata.get("track_number") or "")
    if metadata.get("total_tracks"):
        audio["tracktotal"] = str(metadata.get("total_tracks"))
    audio["discnumber"] = str(metadata.get("disc_number") or "")
    if metadata.get("total_discs"):
        audio["disctotal"] = str(metadata.get("total_discs"))
    audio["date"] = metadata.get("release_date", "")
    audio["isrc"] = metadata.get("isrc", "")
    audio["copyright"] = metadata.get("copyright", "")

    lyrics = metadata.get("lyrics") or metadata.get("lyrics_lrc")
    if lyrics:
        audio["lyrics"] = lyrics
        audio["unsyncedlyrics"] = lyrics

    for tag in ["replaygain_track_gain", "replaygain_track_peak", "replaygain_album_gain", "replaygain_album_peak"]:
        val = metadata.get(tag) or metadata.get(tag.upper())
        if val:
            audio[tag] = str(val)

    if cover_bytes:
        pic = Picture()
        pic.type = 3  # front cover
        pic.mime = "image/png" if cover_bytes.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
        pic.data = cover_bytes
        audio.add_picture(pic)

    audio.save()


def tag_mp4(file_path: str, metadata: dict[str, Any], cover_bytes: bytes | None = None) -> None:
    audio = MP4(file_path)

    audio["\xa9nam"] = metadata.get("title", "")
    audio["\xa9ART"] = metadata.get("artists", "")
    audio["\xa9alb"] = metadata.get("album", "")
    audio["aART"] = metadata.get("album_artist", "")
    audio["\xa9day"] = metadata.get("release_date", "")
    audio["cprt"] = metadata.get("copyright", "")

    track_num = int(metadata.get("track_number") or 0)
    total_tracks = int(metadata.get("total_tracks") or 0)
    audio["trkn"] = [(track_num, total_tracks)]

    disc_num = int(metadata.get("disc_number") or 0)
    total_discs = int(metadata.get("total_discs") or 0)
    audio["disk"] = [(disc_num, total_discs)]

    isrc = metadata.get("isrc")
    if isinstance(isrc, str):
        audio["----:com.apple.iTunes:ISRC"] = isrc.encode("utf-8")

    lyrics = metadata.get("lyrics") or metadata.get("lyrics_lrc")
    if lyrics:
        audio["\xa9lyr"] = lyrics

    for tag in ["replaygain_track_gain", "replaygain_track_peak", "replaygain_album_gain", "replaygain_album_peak"]:
        val = metadata.get(tag) or metadata.get(tag.upper())
        if val:
            audio[f"----:com.apple.iTunes:{tag}"] = str(val).encode("utf-8")

    if cover_bytes:
        fmt = MP4Cover.FORMAT_JPEG
        if cover_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            fmt = MP4Cover.FORMAT_PNG
        audio["covr"] = [MP4Cover(cover_bytes, imageformat=fmt)]

    audio.save()


def tag_mp3(file_path: str, metadata: dict[str, Any], cover_bytes: bytes | None = None) -> None:
    audio = EasyMP3(file_path)

    audio["title"] = metadata.get("title", "")
    audio["artist"] = metadata.get("artists", "")
    audio["album"] = metadata.get("album", "")
    audio["albumartist"] = metadata.get("album_artist", "")

    track_num = str(metadata.get("track_number") or "")
    if metadata.get("total_tracks"):
        track_num += f"/{metadata.get('total_tracks')}"
    audio["tracknumber"] = track_num

    disc_num = str(metadata.get("disc_number") or "")
    if metadata.get("total_discs"):
        disc_num += f"/{metadata.get('total_discs')}"
    audio["discnumber"] = disc_num

    audio["date"] = metadata.get("release_date", "")
    audio["copyright"] = metadata.get("copyright", "")
    audio.save()

    id3 = ID3(file_path)

    lyrics = metadata.get("lyrics") or metadata.get("lyrics_lrc")
    if lyrics:
        id3.add(USLT(encoding=3, lang="eng", desc="", text=lyrics))

    for tag in ["replaygain_track_gain", "replaygain_track_peak", "replaygain_album_gain", "replaygain_album_peak"]:
        val = metadata.get(tag) or metadata.get(tag.upper())
        if val:
            id3.add(TXXX(encoding=3, desc=tag, text=str(val)))

    if cover_bytes:
        mime = "image/png" if cover_bytes.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
        id3.add(
            APIC(
                encoding=3,  # utf-8
                mime=mime,
                type=3,  # front cover
                desc="Front Cover",
                data=cover_bytes,
            )
        )
    id3.save()


def tag_opus(file_path: str, metadata: dict[str, Any], cover_bytes: bytes | None = None) -> None:
    audio = OggOpus(file_path)

    audio["title"] = metadata.get("title", "")
    audio["artist"] = metadata.get("artists", "")
    audio["album"] = metadata.get("album", "")
    audio["albumartist"] = metadata.get("album_artist", "")
    audio["tracknumber"] = str(metadata.get("track_number") or "")
    if metadata.get("total_tracks"):
        audio["tracktotal"] = str(metadata.get("total_tracks"))
    audio["discnumber"] = str(metadata.get("disc_number") or "")
    if metadata.get("total_discs"):
        audio["disctotal"] = str(metadata.get("total_discs"))
    audio["date"] = metadata.get("release_date", "")
    audio["isrc"] = metadata.get("isrc", "")
    audio["copyright"] = metadata.get("copyright", "")

    lyrics = metadata.get("lyrics") or metadata.get("lyrics_lrc")
    if lyrics:
        audio["lyrics"] = lyrics
        audio["unsyncedlyrics"] = lyrics

    for tag in ["replaygain_track_gain", "replaygain_track_peak", "replaygain_album_gain", "replaygain_album_peak"]:
        val = metadata.get(tag) or metadata.get(tag.upper())
        if val:
            audio[tag] = str(val)

    if cover_bytes:
        pic = Picture()
        pic.type = 3  # front cover
        pic.mime = "image/png" if cover_bytes.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
        pic.data = cover_bytes
        picture_data = pic.write()
        picture_b64 = base64.b64encode(picture_data).decode("ascii")
        audio["metadata_block_picture"] = [picture_b64]

    audio.save()


def embed_metadata(file_path: str, metadata: dict[str, Any]) -> None:
    cover_url: str | list[str] | dict[str, str] | None = metadata.get("cover_url")
    if isinstance(cover_url, list) and cover_url:
        first = cover_url[0]
        cover_url = first.get("url") if isinstance(first, dict) else first
    elif isinstance(cover_url, dict):
        cover_url = cover_url.get("url")

    cover_bytes = None
    if isinstance(cover_url, str) and cover_url.strip():
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
                )
            }
            r = requests.get(cover_url, headers=headers, timeout=15)
            if r.status_code == 200:
                cover_bytes = r.content
        except Exception as e:
            logger.warning("failed to fetch cover art from %s: %s", cover_url, e)

    ext = Path(file_path).suffix.lower()
    if ext == ".flac":
        tag_flac(file_path, metadata, cover_bytes)
    elif ext == ".m4a":
        tag_mp4(file_path, metadata, cover_bytes)
    elif ext == ".mp3":
        tag_mp3(file_path, metadata, cover_bytes)
    elif ext in (".opus", ".ogg"):
        tag_opus(file_path, metadata, cover_bytes)
    else:
        logger.warning("unsupported file extension for tagging: %s", ext)
