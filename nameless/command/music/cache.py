from __future__ import annotations

import time
from typing import TYPE_CHECKING, final

if TYPE_CHECKING:
    from pomice import Track


@final
class TrackCache:
    def __init__(self, max_size: int = 1000):
        self.cache: dict[str, list[Track]] = {}
        self.max_size = max_size
        self.access_times: dict[str, float] = {}

    def get(self, query: str, source: str) -> list[Track] | None:
        cache_key = f"{source}:{query.lower()}"
        if cache_key in self.cache:
            self.access_times[cache_key] = time.time()
            return self.cache[cache_key]
        return None

    def set(self, query: str, source: str, tracks: list[Track]) -> None:
        if len(self.cache) >= self.max_size:
            self._evict_oldest()

        cache_key = f"{source}:{query.lower()}"
        self.cache[cache_key] = tracks
        self.access_times[cache_key] = time.time()

    def _evict_oldest(self) -> None:
        if not self.access_times:
            return

        oldest_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
        del self.cache[oldest_key]
        del self.access_times[oldest_key]

    def clear(self) -> None:
        self.cache.clear()
        self.access_times.clear()

    def get_stats(self) -> dict[str, int | float]:
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hit_rate": 0.0,
        }
