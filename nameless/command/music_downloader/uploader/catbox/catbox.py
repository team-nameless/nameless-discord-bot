from __future__ import annotations

import logging
from enum import StrEnum
from typing import TYPE_CHECKING, Any, override

import aiohttp
import anyio

from nameless.command.music_downloader.uploader.base import BaseUploader
from nameless.command.music_downloader.uploader.catbox.exceptions import (
    NoSuchCatboxAlbumError,
    NoSuchCatboxFileError,
)

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator, Awaitable, Callable


class RequestType(StrEnum):
    FILE_UPLOAD = "fileupload"
    URL_UPLOAD = "urlupload"
    DELETE_FILES = "deletefiles"
    CREATE_ALBUM = "createalbum"
    EDIT_ALBUM = "editalbum"
    ADD_TO_ALBUM = "addtoalbum"
    REMOVE_FROM_ALBUM = "removefromalbum"
    DELETE_ALBUM = "deletealbum"


class CatboxUploader(BaseUploader):
    API_URL = "https://catbox.moe/user/api.php"
    MAX_ALBUM_FILES = 500
    NO_SUCH_FILE_ERROR = "No such file."
    NO_SUCH_ALBUM_ERROR = "Album not found."

    def __init__(
        self,
        *,
        user_hash: str | None = None,
        session: aiohttp.ClientSession | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
        chunk_size: int = 64 * 1024,
    ) -> None:
        self.user_hash = user_hash
        self._session = session
        self._timeout = timeout
        self._chunk_size = chunk_size
        self.logger = logging.getLogger("CatboxUploader")

    def _format_files(self, files: set[str]) -> str:
        return " ".join(sorted(files))

    def _is_catbox_error(self, response: str, error_message: str) -> bool:
        return response.strip() == error_message

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
                        "catbox request failed with status %s: %s",
                        response.status,
                        text,
                    )
                    reason = response.reason or ""
                    raise RuntimeError(f"failed to make request: {response.status} {reason}")
                return text
        except aiohttp.ClientError as exc:
            self.logger.error("catbox request failed.", exc_info=exc)
            raise

    async def _make_post_request(
        self,
        req_type: RequestType,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        form = aiohttp.FormData()
        form.add_field("reqtype", req_type.value)
        if self.user_hash is not None:
            form.add_field("userhash", self.user_hash)
        if parameters:
            for key, value in parameters.items():
                form.add_field(key, value)
        return await self._post_form(form)

    async def _make_album_request(
        self,
        short: str,
        req_type: RequestType,
        additional_params: dict[str, str] | None = None,
    ) -> str:
        params = {"short": short}
        if additional_params:
            params.update(additional_params)

        response = await self._make_post_request(req_type, params)
        if self._is_catbox_error(response, self.NO_SUCH_ALBUM_ERROR):
            raise NoSuchCatboxAlbumError(short)
        if self._is_catbox_error(response, self.NO_SUCH_FILE_ERROR):
            raise NoSuchCatboxFileError()
        return response

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
        form.add_field("reqtype", RequestType.FILE_UPLOAD.value)
        if self.user_hash is not None:
            form.add_field("userhash", self.user_hash)
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
        response = await self._make_post_request(RequestType.URL_UPLOAD, {"url": url})
        return response.strip()

    @override
    async def delete_files(self, files: set[str]) -> None:
        response = await self._make_post_request(
            RequestType.DELETE_FILES,
            {"files": self._format_files(files)},
        )
        if self._is_catbox_error(response, self.NO_SUCH_FILE_ERROR):
            raise NoSuchCatboxFileError()

    async def create_album(self, title: str, description: str, files: set[str]) -> str:
        if len(files) > self.MAX_ALBUM_FILES:
            raise ValueError(f"albums can only contain {self.MAX_ALBUM_FILES} files, was given {len(files)}")
        params = {
            "title": title,
            "desc": description,
            "files": self._format_files(files),
        }
        return await self._make_post_request(RequestType.CREATE_ALBUM, params)

    async def edit_album(self, short: str, title: str, description: str, files: set[str]) -> None:
        if len(files) > self.MAX_ALBUM_FILES:
            raise ValueError(f"albums can only contain {self.MAX_ALBUM_FILES} files, was given {len(files)}")
        params = {
            "title": title,
            "desc": description,
            "files": self._format_files(files),
        }
        await self._make_album_request(short, RequestType.EDIT_ALBUM, params)

    async def add_to_album(self, short: str, files: set[str]) -> None:
        await self._make_album_request(
            short,
            RequestType.ADD_TO_ALBUM,
            {"files": self._format_files(files)},
        )

    async def remove_from_album(self, short: str, files: set[str]) -> None:
        await self._make_album_request(
            short,
            RequestType.REMOVE_FROM_ALBUM,
            {"files": self._format_files(files)},
        )

    async def delete_album(self, short: str) -> None:
        await self._make_album_request(short, RequestType.DELETE_ALBUM)

    @override
    def get_service_name(self) -> str:
        return "Catbox"

    @override
    def get_max_file_size(self) -> int | None:
        return 200

    @override
    def is_supported_file_extension(self, extension: str) -> bool:
        unsupported = {"exe", "scr", "cpl", "doc", "docx", "jar"}
        return extension.lstrip(".").lower() not in unsupported
