from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Awaitable, Callable

    import anyio


class BaseUploader(ABC):
    """Base interface for file upload providers."""

    @abstractmethod
    async def upload_file(
        self,
        filepath: str | anyio.Path | pathlib.Path,
        *,
        on_ready: Callable[[str], Awaitable[None]],
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> str | None:
        """Upload a file and return the resulting URL."""

    async def upload_url(self, url: str) -> str:
        """Upload content from a URL and return the resulting URL."""
        raise NotImplementedError("url uploads are not supported by this uploader")

    async def delete_files(self, files: set[str]) -> None:
        """Delete files from the hosting service."""
        raise NotImplementedError("file deletion is not supported by this uploader")

    def get_max_file_size(self) -> int | None:
        """Return the service maximum file size in megabytes when known."""
        return None

    def get_service_name(self) -> str:
        """Return the hosting service name."""
        return self.__class__.__name__

    def validate_file_name(self, name: str) -> bool:
        """Return true if the file name is valid for this service."""
        return name.strip() != ""

    def get_supported_extensions(self) -> set[str] | None:
        """Return a set of supported extensions or None for all extensions."""
        return None

    def is_supported_file_extension(self, extension: str) -> bool:
        """Return true if the given extension is supported by this service."""
        normalized = extension.lstrip(".").lower()
        supported = self.get_supported_extensions()
        return supported is None or normalized in supported
