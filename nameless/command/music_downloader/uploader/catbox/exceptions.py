from __future__ import annotations


class NoSuchCatboxFileError(FileNotFoundError):
    """Raised when a Catbox file operation fails because the file does not exist."""


class NoSuchCatboxAlbumError(Exception):
    """Raised when a Catbox album operation fails because the album is missing or locked."""

    def __init__(self, album_short: str, cause: Exception | None = None) -> None:
        super().__init__(f"album with short '{album_short}' not found or cannot be modified")
        if cause is not None:
            self.__cause__ = cause
