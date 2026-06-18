# ruff: noqa: E501
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, TypedDict

from .base import LyricsBase

if TYPE_CHECKING:
    from requests import Session


if TYPE_CHECKING:

    class LrcLibResponse(TypedDict):
        id: str
        name: str
        trackName: str
        artistName: str
        albumName: str
        duration: float
        instrumental: bool
        plainLyrics: str
        syncedLyrics: str


class LrcLibLyrics(LyricsBase):
    BASE_URL = "https://lrclib.net/api"
    HEADERS: ClassVar = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }

    name: str = "LrcLib"

    def __init__(
        self,
        title: str,
        artist: str,
        session: Session | None = None,
    ):
        super().__init__(title, artist, session)
        self._lyrics_data: LrcLibResponse | None = None
        # retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        # self.session.mount("https://", HTTPAdapter(max_retries=retries))
        # self.session.headers.update(self.HEADERS)

    def find_lyrics(
        self,
        *,
        q: str = "",
        track_name: str = "",
        artist_name: str = "",
        album_name: str = "",
    ) -> LrcLibResponse | None:
        params = {
            "q": q,
            "track_name": track_name,
            "artist_name": artist_name,
            "album_name": album_name,
        }
        try:
            response = self.session.get(
                self.BASE_URL + "/search",
                params=params,
                # timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            for item in data:
                if item.get("track_name") == track_name and item.get("artist_name") == artist_name:
                    return item
            return None
        except Exception as e:
            self.logger.error(repr(e))
            return None

    def lyrics_data(self) -> LrcLibResponse | None:
        if self._lyrics_data is None:
            self._lyrics_data = self.find_lyrics(
                track_name=self.title or "",
                artist_name=self.artist or "",
                # album_name=self.album,
            )

        return self._lyrics_data

    def get_unsynced(self) -> str | None:
        data = self.lyrics_data()
        if data:
            return data.get("plainLyrics", None)

    def get_synced(self) -> str | None:
        data = self.lyrics_data()
        if data:
            return data.get("syncedLyrics", None)
