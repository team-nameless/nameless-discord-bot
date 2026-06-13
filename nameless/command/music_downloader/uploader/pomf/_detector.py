from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

import aiohttp

from nameless.command.music_downloader.uploader.pomf.pomf import ServerConfig, ServerType

if TYPE_CHECKING:
    from collections.abc import Iterable


# A rewrite of https://github.com/FoxeiZ/aliucord-plugins/tree/main/plugins/BoxUpload
class ServerDetector:
    """Detect Pomf/Uguu server metadata from a given URL."""

    TAG = "Pomf.ServerDetector"
    logger = logging.getLogger(TAG)

    title_regex = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
    meta_generator_regex = re.compile(
        r"<meta\s+name=[\"']?generator[\"']?\s+content=[\"'](.*?)[\"']",
        re.IGNORECASE | re.DOTALL,
    )
    max_size_regex = re.compile(r"Max upload size is (\d+)(?:&nbsp;\s?)?([mMiIbBgG]+)")
    expire_time_regex = re.compile(r"files expire after (\d+)\s*(\w+)")

    uguu_indicators = ("grill-wrapper", "upload-clipboard-btn", "js/uguu.js", "pomf.min.js")
    pomf_indicators = ("upload.php", "tools.html", "js/app.js", "ShareX")

    @classmethod
    def _extract_group(cls, pattern: re.Pattern[str], input_text: str, group: int = 1) -> str | None:
        match = pattern.search(input_text)
        if match is None:
            return None
        try:
            return match.group(group)
        except IndexError:
            return None

    @classmethod
    def _extract_title(cls, html: str) -> str | None:
        return cls._extract_group(cls.title_regex, html)

    @classmethod
    def _extract_meta_generator(cls, html: str) -> str | None:
        return cls._extract_group(cls.meta_generator_regex, html)

    @classmethod
    def _parse_max_size(cls, html: str) -> tuple[int, str]:
        match = cls.max_size_regex.search(html)
        if match is None:
            return 0, "MiB"

        max_size_str = match.group(1) or ""
        max_size_unit = match.group(2) or "MiB"
        try:
            max_size = int(max_size_str) if max_size_str.strip() else 0
        except ValueError:
            cls.logger.warning("failed to parse max size number: %s", max_size_str)
            max_size = 0

        return max_size, max_size_unit

    @classmethod
    def _parse_expire_time(cls, html: str) -> tuple[str, str]:
        match = cls.expire_time_regex.search(html)
        if match is None:
            return "", ""
        expire_time = match.group(1) or ""
        expire_unit = match.group(2) or ""
        return expire_time, expire_unit

    @classmethod
    async def detect(
        cls,
        url: str,
        *,
        session: aiohttp.ClientSession | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
    ) -> ServerConfig:
        target_url = url.strip()
        if target_url == "":
            raise ValueError("url must not be blank")

        cls.logger.info("Detecting server type for URL: %s", target_url)
        html = await cls._fetch_html(target_url, session=session, timeout=timeout)
        cls.logger.debug("Fetched HTML content from %s (%s chars)", target_url, len(html))

        server_type = cls._detect_server_type(html)
        cls.logger.debug("Detected server type: %s", server_type)

        if server_type == ServerType.UGUU:
            return cls.parse_uguu_config(target_url, html)
        if server_type == ServerType.POMF:
            return cls.parse_pomf_config(target_url, html)
        return ServerConfig(ServerType.UNKNOWN, target_url)

    @classmethod
    async def _fetch_html(
        cls,
        url: str,
        *,
        session: aiohttp.ClientSession | None,
        timeout: aiohttp.ClientTimeout | None,
    ) -> str:
        if session is None:
            request_timeout = timeout or aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=request_timeout) as new_session:
                return await cls._fetch_html_with_session(new_session, url, timeout=None)
        return await cls._fetch_html_with_session(session, url, timeout=timeout)

    @classmethod
    async def _fetch_html_with_session(
        cls,
        session: aiohttp.ClientSession,
        url: str,
        *,
        timeout: aiohttp.ClientTimeout | None,
    ) -> str:
        try:
            request_kwargs: dict[str, Any] = {"allow_redirects": True}
            if timeout is not None:
                request_kwargs["timeout"] = timeout
            async with session.get(url, **request_kwargs) as response:
                if response.status != 200:
                    reason = response.reason or ""
                    raise RuntimeError(f"http error: {response.status} {reason}")
                return await response.text()
        except TimeoutError as exc:
            cls.logger.error("network timeout while fetching url: %s", url, exc_info=exc)
            raise RuntimeError("network timeout while fetching url") from exc
        except aiohttp.ClientError as exc:
            cls.logger.error("network error while fetching url: %s", url, exc_info=exc)
            raise RuntimeError(f"network error: {exc}") from exc

    @classmethod
    def parse_uguu_config(cls, url: str, html: str) -> ServerConfig:
        """Parse Uguu metadata from HTML."""
        max_size, max_size_unit = cls._parse_max_size(html)
        expire_time, expire_unit = cls._parse_expire_time(html)

        if max_size == 0:
            cls.logger.warning("Could not parse max upload size for Uguu server: %s", url)

        return ServerConfig(
            ServerType.UGUU,
            url,
            max_upload_size=max_size,
            max_size_unit=max_size_unit,
            expire_time=expire_time,
            expire_time_unit=expire_unit,
        )

    @classmethod
    def parse_pomf_config(cls, url: str, html: str) -> ServerConfig:
        max_size, max_size_unit = cls._parse_max_size(html)

        if max_size == 0:
            cls.logger.warning("Could not parse max upload size for Pomf server: %s", url)

        return ServerConfig(
            ServerType.POMF,
            url,
            max_upload_size=max_size,
            max_size_unit=max_size_unit,
        )

    @classmethod
    def _detect_server_type(cls, html: str) -> ServerType:
        generator = cls._extract_meta_generator(html)
        if generator is not None:
            generator_lower = generator.lower()
            if "uguu" in generator_lower:
                cls.logger.info("Detected Uguu server via meta generator")
                return ServerType.UGUU
            if "pomf" in generator_lower:
                cls.logger.info("Detected Pomf server via meta generator")
                return ServerType.POMF

        return cls._detect_by_indicators(html)

    @classmethod
    def _count_indicators(cls, html: str, indicators: Iterable[str]) -> int:
        html_lower = html.lower()
        return sum(1 for indicator in indicators if indicator.lower() in html_lower)

    @classmethod
    def _detect_by_indicators(cls, html: str) -> ServerType:
        uguu_score = cls._count_indicators(html, cls.uguu_indicators)
        pomf_score = cls._count_indicators(html, cls.pomf_indicators)

        cls.logger.info("Detection scores - Uguu: %s, Pomf: %s", uguu_score, pomf_score)

        if uguu_score > pomf_score:
            cls.logger.info("Detected Uguu server via content indicators")
            return ServerType.UGUU
        if pomf_score > uguu_score:
            cls.logger.info("Detected Pomf server via content indicators")
            return ServerType.POMF

        cls.logger.info("Could not determine server type")
        return ServerType.UNKNOWN


__all__ = ["ServerDetector"]
