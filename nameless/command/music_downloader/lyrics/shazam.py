# ruff: noqa: E501
from __future__ import annotations

import json
import re
import urllib.parse
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any, ClassVar, NotRequired, TypedDict

from .base import LyricsBase

if TYPE_CHECKING:
    from collections.abc import Iterator

    from requests import Response, Session

if TYPE_CHECKING:
    # albumName: "Splash!!"
    # artistName: "Massive New Krew & RoughSketch"
    # artwork: {bgColor: "85b5bb", hasP3: false, height: 3000, textColor1: "0a122a", textColor2: "132837",…}
    # audioLocale: "ja"
    # audioTraits: ["lossless", "lossy-stereo"]
    # composerName: "Massive New Krew"
    # discNumber: 1
    # durationInMillis: 282280
    # genreNames: ["Dance", "Music"]  # use this later?
    # hasLyrics: true
    # hasTimeSyncedLyrics: true
    # isAppleDigitalMaster: false
    # isMasteredForItunes: false
    # isVocalAttenuationAllowed: true
    # isrc: "JPQ891600122"
    # name: "Extreme Music School (feat. Nanahira)"
    class ShazamSongAttributes(TypedDict):
        hasLyrics: bool
        hasTimeSyncedLyrics: bool
        name: str

    class ShazamSongData(TypedDict):
        attributes: ShazamSongAttributes
        id: str
        type: str

    class ShazamSong(TypedDict):
        data: list[ShazamSongData]

    class ShazamSongResult(TypedDict):
        songs: ShazamSong

    class ShazamErrorResult(TypedDict):
        id: str
        title: str
        detail: str
        status: str
        code: str
        source: dict[str, str]

    class ShazamSearchResult(TypedDict):
        results: NotRequired[ShazamSongResult]
        errors: NotRequired[list[ShazamErrorResult]]

    ShazamPageCreativeWorkLyrics = TypedDict("ShazamPageCreativeWorkLyrics", {"text": str, "@type": str})

    ShazamPagePerson = TypedDict("ShazamPagePerson", {"name": str, "@type": str})
    ShazamPageMusicComposition = TypedDict(
        "ShazamPageMusicComposition",
        {
            "composer": list[ShazamPagePerson],
            "@type": str,
            "lyrics": ShazamPageCreativeWorkLyrics | None,
        },
    )
    ShazamPageMusicRecordingCompact = TypedDict(
        "ShazamPageMusicRecordingCompact",
        {
            "name": str,
            "url": str,
            "byArtist": str,
            "recordingOf": ShazamPageMusicComposition,
            "@context": str,
            "@type": str,
            "@id": str,
            "lyricist": list[ShazamPagePerson],
            "duration": str | None,
            "description": str | None,
            "genre": str | None,
            "isFamilyFriendly": bool | None,
            "datePublished": str | None,
        },
    )


class ShazamLyrics(LyricsBase):
    name: str = "shazam"
    # BASE_URL = "https://www.shazam.com/services/search/v3/en-US/GB/web/search?query={query}&numResults=3&offset=0&types=songs"
    HEADERS: ClassVar = {
        "X-Shazam-Platform": "IPHONE",
        "X-Shazam-AppVersion": "14.1.0",
        "Accept": "*/*",
        "Accept-Language": "en-US",
        "Accept-Encoding": "gzip, deflate",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    }

    def __init__(
        self,
        title: str,
        artist: str,
        session: Session | None = None,
    ):
        super().__init__(title, artist, session)
        self._raw_data: tuple[str, bool, bool] | None = None

    def _make_request(self, url: str) -> Response | None:
        try:
            response = self.session.get(
                url,
                headers=self.HEADERS,
                allow_redirects=True,
                # timeout=10,
            )
            response.raise_for_status()
        except Exception as e:
            self.logger.exception(f"Connection error while making request to {url}: {e}")
            return None

        return response

    def handle_error_responses(
        self,
        data: ShazamErrorResult,
        query: str,
        language: str,
        *,
        short_circuit: bool = False,
    ) -> Any:
        if data.get("title", "").lower() == "invalid parameter":
            source = data.get("source", {})
            if not source:
                return

            param = source.get("parameter", "")
            if not param:
                return

            query = query.replace(param, "").strip()
            self.logger.debug(f"Retrying without invalid parameter: {param!r}")
            if short_circuit:
                raise ValueError(f"Invalid parameter: {param!r}")

            return self._search_for_id(query, language, short_circuit=True)

        details = ", ".join(f"{key}={value!r}" for key, value in data.items())
        raise ValueError(f"Shazam API error: {details}")

    def _search_for_id(
        self, query: str, language: str = "GB", *, short_circuit: bool = False
    ) -> tuple[str, bool, bool]:
        resp = self._make_request(
            f"https://www.shazam.com/services/amapi/v1/catalog/{language}/search?types=songs&term={urllib.parse.quote(query)}&limit=3"
        )
        if resp is None:
            raise ValueError("Failed to fetch data")

        data: ShazamSearchResult = resp.json()
        if not data:
            raise ValueError("No data found")

        for error in data.get("errors", []):
            return self.handle_error_responses(
                error,
                query,
                language,
                short_circuit=short_circuit,
            )

        for song in data.get("results", {}).get("songs", {}).get("data", []):
            sz_name = song["attributes"]["name"]
            sm = SequenceMatcher(
                lambda x: x in ("-", "_"),
                self.title.lower(),
                sz_name.lower(),
            )
            ratio = round(sm.ratio(), 2)
            if ratio >= 0.7:
                return (
                    song["id"],
                    song["attributes"]["hasLyrics"],
                    song["attributes"]["hasTimeSyncedLyrics"],
                )

        raise ValueError("No matching song found")

    def _get_real_page(
        self,
        track_id: str,
    ) -> str | None:
        song_page = self._make_request(f"https://www.shazam.com/song/{track_id}")
        if song_page is None:
            return None

        regex = r"<link\s+rel=\"canonical\"\s+href=\"([^\"]+)"
        match = re.search(regex, song_page.text, re.NOFLAG)
        if match:
            return match.group(1)
        return None

    def _deep_search_all(self, data: dict[str, Any] | list[Any] | Any, target_key: str) -> Iterator[Any]:
        if isinstance(data, dict):
            if target_key in data:
                yield data[target_key]

            for value in data.values():
                if TYPE_CHECKING:
                    value: Any
                yield from self._deep_search_all(value, target_key)

        elif isinstance(data, list):
            for item in data:
                yield from self._deep_search_all(item, target_key)

    def get_unsynced(self) -> str | None:
        if not self.has_lyrics():
            return None

        pattern = r'<script type="application/ld\+json">(.*?)</script>'
        match = re.search(pattern, self.page_content(), re.DOTALL)
        if not match:
            self.logger.warning("Failed to find lyrics data in the song page.")
            return None

        json_data = match.group(1).strip()
        data: ShazamPageMusicRecordingCompact = json.loads(json_data)
        lyrics_data = data["recordingOf"]["lyrics"]
        if not lyrics_data:
            self.logger.warning("No lyrics found for this track.")
            return None

        return lyrics_data["text"]

    def _get_synced_lyrics(self) -> Iterator[str]:
        pattern = r"self\.__next_f\.push\(\[\s*1,\s*\"..?:(.*?)\"\]\)"
        match = re.finditer(pattern, self.page_content(), re.DOTALL)
        if not match:
            self.logger.warning("Failed to find synced lyrics data in the song page.")
            return

        lyrics_block_js_string = None
        for m in match:
            if not m:
                continue
            content = m.group(1)
            if "startTimeInSeconds" in content or "endTimeInSeconds" in content:
                lyrics_block_js_string = content
                break

        if not lyrics_block_js_string:
            self.logger.warning("No synced lyrics found for this track.")
            return

        # annoying double escape sequences in the JS string, need to decode properly
        lyrics_block_js_string = (
            lyrics_block_js_string.encode()
            .decode("unicode_escape")  # for removing double escape sequences
            .encode("latin-1")  # for correct byte representation
            .decode("utf-8")  # final decode to utf-8
        )

        lyrics_data = json.loads(lyrics_block_js_string)
        if not lyrics_data:
            self.logger.warning("No synced lyrics data could be parsed.")
            return

        # lyrics_data[-1]["children"][-1]["children"][-1]["children"][-1][0][-1]["children"][-1][-1]["lyrics"]["lyricLines"]
        lyric_lines_gen = self._deep_search_all(lyrics_data, "lyricLines")
        if TYPE_CHECKING:
            lyric_lines_gen: Iterator[list[dict[str, Any]]]

        for lyric_lines in lyric_lines_gen:
            if len(lyric_lines) > 0:
                for line in lyric_lines:
                    time_raw: str = line.get("startTimeInSeconds", "0")
                    try:
                        time_float = float(time_raw)
                        minutes = int(time_float // 60)
                        seconds = int(time_float % 60)
                        hundredths = int((time_float - int(time_float)) * 100)
                        start_time = f"{minutes:02d}:{seconds:02d}.{hundredths:02d}"
                    except ValueError:
                        parts = time_raw.split(":")
                        if len(parts) == 3:
                            hours = int(parts[0])
                            minutes = int(parts[1])
                            seconds = float(parts[2])
                            if hours > 0:
                                minutes += hours * 60
                            start_time = f"{minutes:02d}:{seconds:05.2f}"
                        elif len(parts) == 2:
                            minutes = int(parts[0])
                            seconds = float(parts[1])
                            start_time = f"{minutes:02d}:{seconds:05.2f}"
                        else:
                            start_time = "00:00.000"

                    text = line.get("content", "♪")
                    yield f"[{start_time}] {text}"

    def get_synced(self) -> str | None:
        if not self.has_synced_lyrics():
            return None
        lines = list(self._get_synced_lyrics())
        if not lines:
            self.logger.warning("No synced lyrics lines could be extracted.")
            return None
        return "\n".join(lines)

    def raw_data(self) -> tuple[str, bool, bool]:
        if not self._raw_data:
            self._raw_data = self._get_data()

        if self._raw_data is None:
            return "", False, False
        return self._raw_data

    def page_content(self) -> str:
        return self.raw_data()[0]

    def has_lyrics(self) -> bool:
        return self.raw_data()[1]

    def has_synced_lyrics(self) -> bool:
        return self.raw_data()[2]

    def _get_data(self) -> tuple[str, bool, bool] | None:
        track_id: str = ""
        has_lyrics: bool = False
        has_synced_lyrics: bool = False

        assert self.title is not None
        query = f"{self.artist} {self.title}" if self.artist else self.title
        for language in ["GB", "JP"]:
            try:
                track_id, has_lyrics, has_synced_lyrics = self._search_for_id(query, language)
            except ValueError as e:
                self.logger.error(repr(e))
                continue

        if not track_id:
            self.logger.warning("No matching track found on Shazam.")
            return None

        song_url = self._get_real_page(track_id)
        if not song_url:
            self.logger.warning("Failed to retrieve the song page.")
            return None

        song_page = self._make_request(song_url)
        if song_page is None:
            self.logger.warning("Failed to retrieve the song page content.")
            return None

        return song_page.text, has_lyrics, has_synced_lyrics
