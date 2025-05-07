import logging
from pathlib import Path

__all__ = ["nameless_cache"]


class NamelessKeyCache:
    """A simple key-only cache, with internal logging and persitence support."""

    def __init__(self):
        self.cache: dict[str, bool] = {}
        self.cache_path: Path = Path(__file__).parent.parent.parent / "nameless.cache"

    def populate_from_persistence(self) -> None:
        """Read from cache persistence."""
        logging.info("Reading cache file.")

        # Create cold cache if needed.
        if not self.cache_path.exists():
            logging.warning("Cache does not exist, creating cold cache file.")
            self.cache_path.touch(exist_ok=False)

        with open(self.cache_path, encoding="utf-8") as f:
            lines = f.read().splitlines()
            for line in lines:
                self.cache[line] = True

    def yank_to_persitence(self) -> None:
        """Write to cache persistence."""
        logging.info("Writing to cache file.")

        with open(self.cache_path, mode="w", encoding="utf-8") as f:
            for key in self.cache:
                f.write(f"{key}\n")

    def set_key(self, key: str) -> None:
        """Flag a key to be exist."""
        logging.debug("Cache key [%s] has been validated.", key)
        self.cache[key] = True

    def get_key(self, key: str) -> bool:
        """Check if `key` exists in cache."""
        logging.debug("Cache key [%s] has been looked up.", key)
        return key in self.cache

    def invalidate_key(self, key: str) -> None:
        """Invalidate a key."""
        logging.debug("Cache key [%s] has been invalidated.", key)
        del self.cache[key]


nameless_cache = NamelessKeyCache()
