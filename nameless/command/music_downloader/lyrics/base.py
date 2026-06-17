# ruff: noqa: E501
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from requests import Session

if TYPE_CHECKING:
    from typing import ClassVar


class InnerTubeBase:
    if TYPE_CHECKING:
        session: Session

    API_KEY = "AIzaSyDkZV5Q2b1e0Qf4Zc0wRjM3vW3rmpZ_mD0"
    INNER_TUBE_BASE = "https://music.youtube.com/youtubei/v1"
    HEADERS: ClassVar[dict[str, str]] = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://music.youtube.com",
        "Referer": "https://music.youtube.com/",
    }
    CLIENT_CONTEXT: ClassVar[dict[str, Any]] = {
        "client": {
            "clientName": "WEB_REMIX",
            "clientVersion": "1.20210912.07.00",
        },
    }

    def __init__(self, session: Session | None = None):
        self.session = session or Session(headers=self.HEADERS)

    def fetch(self, endpoint: Literal["next", "browse"], payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.INNER_TUBE_BASE}/{endpoint}?key={self.API_KEY}"
        if payload.get("context") is None:
            payload["context"] = self.CLIENT_CONTEXT

        response = self.session.post(url, json={**payload, "context": self.CLIENT_CONTEXT})
        response.raise_for_status()
        return response.json()

    def fetch_next(self, video_id: str) -> dict[str, Any]:
        return self.fetch("next", {"videoId": video_id})

    def fetch_browse(self, browse_id: str) -> dict[str, Any]:
        return self.fetch("browse", {"browseId": browse_id})


class LyricsBase:
    if TYPE_CHECKING:
        title: str
        artist: str

    name = "base_lyrics"

    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    }

    def __init__(
        self,
        title: str,
        artist: str,
        session: Session | None = None,
    ):
        self.title = title
        self.artist = artist
        self.logger = logging.getLogger(f"lyrics:{self.name}")
        self.session = session or Session(headers=self.HEADERS)

    def get_synced(self) -> str | None:
        raise NotImplementedError("Subclasses must implement this method")

    def get_unsynced(self) -> str | None:
        raise NotImplementedError("Subclasses must implement this method")
