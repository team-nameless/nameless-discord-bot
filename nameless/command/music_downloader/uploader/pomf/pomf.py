from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, override

import aiohttp
import anyio

from nameless.command.music_downloader.uploader.base import BaseUploader

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator, Awaitable, Callable


class ServerType(StrEnum):
    UNKNOWN = "UNKNOWN"
    UGUU = "UGUU"
    POMF = "POMF"


@dataclass(eq=False, slots=True)
class ServerConfig:
    server_type: ServerType
    url: str
    max_upload_size: int | None = None
    max_size_unit: str | None = None
    expire_time: str | None = None
    expire_time_unit: str | None = None

    @classmethod
    def default(cls) -> ServerConfig:
        return cls.uguu_config()

    @classmethod
    def rokket_config(cls) -> ServerConfig:
        return cls(
            server_type=ServerType.POMF,
            url="https://rokket.space/",
            max_upload_size=5096,
            expire_time="1",
            expire_time_unit="week",
        )

    @classmethod
    def uguu_config(cls) -> ServerConfig:
        return cls(
            server_type=ServerType.UGUU,
            url="https://uguu.se/",
            max_upload_size=128,
            expire_time="3",
            expire_time_unit="hours",
        )


class PomfUploader(BaseUploader):
    def __init__(
        self,
        *,
        config: ServerConfig | None = None,
        session: aiohttp.ClientSession | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
        chunk_size: int = 64 * 1024,
    ) -> None:
        self.config = config or ServerConfig.default()
        self._session = session
        self._timeout = timeout
        self._chunk_size = chunk_size
        self.logger = logging.getLogger("PomfUploader")

    def _build_upload_url(self) -> str:
        if self.config.server_type == ServerType.UGUU:
            return f"{self.config.url}/upload"
        return f"{self.config.url}/upload.php"

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

    async def _post_form(self, form: aiohttp.FormData) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        try:
            request_kwargs: dict[str, Any] = {
                "data": form,
                "headers": {"User-Agent": "PomfClient/1.0"},
            }
            if timeout is not None:
                request_kwargs["timeout"] = timeout
            async with session.post(self._build_upload_url(), **request_kwargs) as response:
                payload = await response.json()
                if response.status != 200:
                    self.logger.error(
                        "pomf request failed with status %s: %s",
                        response.status,
                        payload,
                    )
                    reason = response.reason or ""
                    raise RuntimeError(f"failed to make request: {response.status} {reason}")
                if not isinstance(payload, dict):
                    raise RuntimeError("upload response is not a json object")
                return payload
        except aiohttp.ClientError as exc:
            self.logger.error("pomf request failed.", exc_info=exc)
            raise

    def _extract_url(self, payload: dict[str, Any]) -> str:
        success = payload.get("success")
        if success is not True:
            raise RuntimeError("upload failed")

        files = payload.get("files")
        if not isinstance(files, list) or not files:
            raise RuntimeError("upload response missing files")

        first = files[0]
        if not isinstance(first, dict):
            raise RuntimeError("upload response file entry is invalid")

        url = first.get("url")
        if not isinstance(url, str) or not url:
            raise RuntimeError("upload response missing url")

        return url

    @override
    async def upload_file(
        self,
        filepath: str | anyio.Path | pathlib.Path,
        *,
        on_ready: Callable[[str], Awaitable[None]],
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> str | None:
        path = anyio.Path(filepath)
        if not self.validate_file_name(path.name):
            raise ValueError("name must not be blank")

        total_size = (await path.stat()).st_size
        form = aiohttp.FormData()
        form.add_field(
            "files[]",
            self._file_iter(path, total_size=total_size, on_progress=on_progress),
            filename=path.name,
            content_type="application/octet-stream",
        )

        payload = await self._post_form(form)
        url = self._extract_url(payload)
        await on_ready(url)
        return url

    @override
    async def upload_url(self, url: str) -> str:
        raise NotImplementedError("pomf/uguu does not support url uploads")

    @override
    async def delete_files(self, files: set[str]) -> None:
        raise NotImplementedError("pomf/uguu does not support file deletion")

    @override
    def get_service_name(self) -> str:
        return "Pomf/Uguu"

    @override
    def get_max_file_size(self) -> int | None:
        return self.config.max_upload_size

    @override
    def is_supported_file_extension(self, extension: str) -> bool:
        unsupported = {
            "exe",
            "scr",
            "com",
            "vbs",
            "bat",
            "cmd",
            "htm",
            "html",
            "jar",
            "msi",
            "apk",
            "phtml",
            "svg",
        }
        return extension.lstrip(".").lower() not in unsupported
