from .base import LyricsBase
from .lrclib import LrcLibLyrics
from .musixmatch import MusixMatchLyrics
from .shazam import ShazamLyrics

__all__ = [
    "LrcLibLyrics",
    "LyricsBase",
    "MusixMatchLyrics",
    "ShazamLyrics",
    "get_lyrics",
]

PROVIDER_CLASSES = {
    "shazam": ShazamLyrics,
    "musixmatch": MusixMatchLyrics,
    "lrclib": LrcLibLyrics,
}


def get_lyrics(spotify_id: str, title: str, artist: str) -> str | None:
    _providers = [v(spotify_id, title, artist) for v in PROVIDER_CLASSES.values()]
    for provider in _providers:
        try:
            lyrics = provider.get_synced()
            if lyrics:
                return lyrics
        except Exception as e:
            print(f"Error fetching lyrics from {provider.name}: {e}")

    for provider in _providers:
        try:
            lyrics = provider.get_unsynced()
            if lyrics:
                return lyrics
        except Exception as e:
            print(f"Error fetching unsynced lyrics from {provider.name}: {e}")
