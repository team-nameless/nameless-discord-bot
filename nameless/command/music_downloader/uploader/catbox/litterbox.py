from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, override

import aiohttp
import anyio

from nameless.command.music_downloader.uploader.base import BaseUploader

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator, Awaitable, Callable


class LitterboxUploader(BaseUploader):
    """Litterbox file upload provider."""

    API_URL = "https://litterbox.catbox.moe/resources/internals/api.php"

    def __init__(
        self,
        *,
        duration: int = 1,
        session: aiohttp.ClientSession | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
        chunk_size: int = 64 * 1024,
    ) -> None:
        self.duration = duration
        self._session = session
        self._timeout = timeout
        self._chunk_size = chunk_size
        self.logger = logging.getLogger("LitterboxUploader")

    async def _file_iter(
        self,
        filepath: anyio.Path,
        *,
        total_size: int,
        on_progress: Callable[[int, int], Awaitable[None]] | None,
    ) -> AsyncIterator[bytes]:
        sent = 0
        if on_progress is not None:
            await on_progress(0, total_size)

        async with await anyio.open_file(filepath, "rb") as handle:
            while True:
                chunk = await handle.read(self._chunk_size)
                if not chunk:
                    break
                sent += len(chunk)
                if on_progress is not None:
                    await on_progress(sent, total_size)
                yield chunk

        if on_progress is not None and sent != total_size:
            await on_progress(sent, total_size)

    async def _post_form(self, form: aiohttp.FormData) -> str:
        session = self._session
        if session is None:
            timeout = self._timeout or aiohttp.ClientTimeout(total=300.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                return await self._post_with_session(session, form, timeout=None)

        return await self._post_with_session(session, form, timeout=self._timeout)

    async def _post_with_session(
        self,
        session: aiohttp.ClientSession,
        form: aiohttp.FormData,
        *,
        timeout: aiohttp.ClientTimeout | None,
    ) -> str:
        try:
            request_kwargs: dict[str, Any] = {
                "data": form,
                "headers": {"User-Agent": "CatboxClient/1.0"},
            }
            if timeout is not None:
                request_kwargs["timeout"] = timeout
            async with session.post(self.API_URL, **request_kwargs) as response:
                text = await response.text()
                if response.status != 200:
                    self.logger.error(
                        "litterbox request failed with status %s: %s",
                        response.status,
                        text,
                    )
                    reason = response.reason or ""
                    raise RuntimeError(f"failed to make request: {response.status} {reason}")
                return text
        except aiohttp.ClientError as exc:
            self.logger.error("litterbox request failed.", exc_info=exc)
            raise

    @override
    async def upload_file(
        self,
        filepath: str | anyio.Path | pathlib.Path,
        *,
        on_ready: Callable[[str], Awaitable[None]],
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        path = anyio.Path(filepath)
        if not self.validate_file_name(path.name):
            raise ValueError("name must not be blank")

        total_size = (await path.stat()).st_size

        form = aiohttp.FormData()
        form.add_field("reqtype", "fileupload")
        form.add_field("time", f"{self.duration}h")
        form.add_field(
            "fileToUpload",
            self._file_iter(path, total_size=total_size, on_progress=on_progress),
            filename=path.name,
            content_type="application/octet-stream",
        )

        response = await self._post_form(form)
        url = response.strip()
        await on_ready(url)
        return url

    @override
    async def upload_url(self, url: str) -> str:
        raise NotImplementedError("litterbox does not support url uploads")

    @override
    async def delete_files(self, files: set[str]) -> None:
        raise NotImplementedError("litterbox does not support file deletion")

    @override
    def get_service_name(self) -> str:
        return "Litterbox"

    @override
    def get_max_file_size(self) -> int | None:
        return 1000

    @override
    def is_supported_file_extension(self, extension: str) -> bool:
        unsupported = {"exe", "scr", "cpl", "doc", "docx", "jar"}
        return extension.lstrip(".").lower() not in unsupported
