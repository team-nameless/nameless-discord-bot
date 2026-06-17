# ruff: noqa: E501
from __future__ import annotations

import json
from typing import Any, ClassVar

from .base import LyricsBase


class MusixMatchLyrics(LyricsBase):
    HEADERS: ClassVar = {
        "authority": "apic-desktop.musixmatch.com",
        "cookie": "mxm_bab=AB",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    }

    token: ClassVar[str | None] = None

    def _get_token(self, force_refresh: bool = False) -> str | None:
        if not force_refresh and self.token:
            return self.token

        return self._refresh_token()

    def _refresh_token(self) -> str | None:
        try:
            response = self.session.get(
                "https://apic-desktop.musixmatch.com/ws/1.1/token.get",
                params={"app_id": "web-desktop-app-v1.0"},
                # timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if data["message"]["header"]["status_code"] == 200:
                self.__class__.token = data["message"]["body"]["user_token"]
                return self.token
        except Exception as e:
            print(f"Error fetching MusixMatch token: {e}")
        return None

    def find_lyrics(
        self,
        *,
        album: str = "",
        artist: str = "",
        title: str = "",
        renew: bool = False,
    ) -> dict[str, Any] | None:
        token = self._get_token(force_refresh=renew)
        if not token:
            self.logger.error("Could not obtain MusixMatch token.")
            return None

        params = {
            "q_album": album,
            "q_artist": artist,
            "q_track": title,
            "usertoken": token,
            "app_id": "web-desktop-app-v1.0",
            "format": "json",
            "namespace": "lyrics_richsynched",
            "subtitle_format": "mxm",
        }

        try:
            response = self.session.get(
                "https://apic-desktop.musixmatch.com/ws/1.1/macro.subtitles.get",
                params=params,
                # timeout=10,
            )
            response.raise_for_status()
        except Exception as e:
            self.logger.error(repr(e))
            return None

        r = response.json()
        status_code = r["message"]["header"]["status_code"]

        if status_code != 200:
            if r["message"]["header"].get("hint") == "renew" or status_code == 401:
                if not renew:
                    self.logger.info("Token expired, renewing...")
                    return self.find_lyrics(album=album, artist=artist, title=title, renew=True)
                else:
                    self.logger.error("Token rejected after renewal.")
                    return None

            self.logger.error(f"API Error: {status_code}")
            return None

        body = r["message"]["body"]["macro_calls"]
        track_status = body["matcher.track.get"]["message"]["header"].get("status_code")

        if track_status != 200:
            if track_status == 404:
                self.logger.info("No lyrics/songs found.")
            elif track_status == 401:
                self.logger.info("Timed out or auth error.")
            else:
                self.logger.error(f"Matcher error: {body['matcher.track.get']['message']['header']}")
            return None

        lyrics_msg = body["track.lyrics.get"]["message"]
        if lyrics_msg.get("header", {}).get("status_code") == 200 and lyrics_msg["body"]["lyrics"]["restricted"]:
            self.logger.info("Restricted lyrics.")
            return None

        return body

    def get_unsynced(self) -> str | None:
        body = self.find_lyrics(artist=self.artist, title=self.title)
        if body is None:
            return None

        lyrics_body = body["track.lyrics.get"]["message"].get("body")
        if lyrics_body is None:
            return None

        lyrics: str = lyrics_body["lyrics"]["lyrics_body"]
        if lyrics:
            return "\n".join(filter(None, lyrics.split("\n")))

        return None

    def get_synced(self) -> str | None:
        body = self.find_lyrics(artist=self.artist, title=self.title)
        if body is None:
            return None

        subtitle_body = body["track.subtitles.get"]["message"].get("body")
        if subtitle_body is None:
            return None

        subtitle_list = subtitle_body.get("subtitle_list", [])
        if not subtitle_list:
            return None

        subtitle = subtitle_list[0].get("subtitle")
        if subtitle:
            return "\n".join(
                [
                    f"[{line['time']['minutes']:02d}:{line['time']['seconds']:02d}.{line['time']['hundredths']:02d}]{line['text'] or '♪'}"
                    for line in json.loads(subtitle["subtitle_body"])
                ]
            )

        return None
