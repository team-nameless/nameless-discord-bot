import asyncio
import io
import json
import logging
import random
import threading
from collections import deque
from functools import partial
from typing import IO, Any, AsyncGenerator, Dict, Optional, Union

import aiohttp
import discord
from discord.utils import MISSING
from typing_extensions import Self
from yt_dlp import YoutubeDL

from NamelessConfig import NamelessConfig

from .errors import FFAudioProcessNoCache


__all__ = ["YTDLSource", "YTMusicSource", "FFOpusAudioProcess"]

FFMPEG_OPTS = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", "options": "-vn"}
YTDL_OPTS = {
    "format": "bestaudio[ext=webm]/bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio[ext=m4a]/bestaudio/93/best",  # noqa: E501
    "outtmpl": r"downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "extract_flat": "in_playlist",
    "no_warnings": True,
    "default_search": "ytsearch10",
    "playlist_items": "1-200",
    "source_address": "0.0.0.0",
}
ytdl = YoutubeDL(YTDL_OPTS)
VoiceChannel = Union[discord.VoiceChannel, discord.StageChannel]


class UsefulMethod:
    @staticmethod
    async def requests(http_session: aiohttp.ClientSession, url, *args, **kwargs) -> Optional[dict]:
        """Re-use the same session for multiple requests.

        For example we re-use discord.HTTPSession to avoid create a new session each time.
        This also automatically convert respone to a dict for more convenient usage.
        """
        async with http_session.get(url, *args, **kwargs) as resp:
            if resp.status == 200:
                try:
                    return await resp.json()
                except json.JSONDecodeError:
                    return None

            raise asyncio.InvalidStateError(f"Failed to get {url}: Get {resp.status}")


class FFOpusAudioProcess(discord.FFmpegOpusAudio):
    FRAME_SIZE = 3840  # each frame is about 20ms 16bit 48KHz 2ch PCM
    ONE_SEC_FRAME_SIZE = FRAME_SIZE * 50

    def __init__(
        self,
        source: Union[str, io.BufferedIOBase],
        *,
        bitrate: Optional[int] = None,
        codec: str = "opus",
        executable: str = "ffmpeg",
        pipe: bool = False,
        stderr: Optional[IO[bytes]] = None,
        before_options: Optional[str] = None,
        options: Optional[str] = None,
        can_cache: bool = True,
    ) -> None:
        self.lock = threading.Event()
        self.lock.set()

        self.stream: deque[bytes] = deque()
        self.stream_idx = 0

        self.can_cache = can_cache
        self.is_seek = False
        self.cache_done = False

        super().__init__(
            source=source,
            bitrate=bitrate,
            codec=codec,
            executable=executable,
            pipe=pipe,
            stderr=stderr,
            before_options=before_options,
            options=options,
        )

    def read(self):
        self.lock.wait()
        next_call = partial(next, self._packet_iter, b"")
        if not self.can_cache:
            return next_call()

        if self.cache_done:
            data = self.stream[self.stream_idx]
        else:
            data = next_call()
            self.stream.append(data)
            self.cache_done = not (data)

        # print(self.stream_idx)
        self.stream_idx += 1
        # if not data:
        #     print(f"data is None at {self.stream_idx}")
        return data

    async def seek(self, index_offset: int):
        if self.stream is MISSING or self._process is MISSING:  # return if trying to seek on a clean stream
            return

        self.lock.clear()
        index_offset = max(index_offset * 50 + self.stream_idx, 0)

        if index_offset > self.stream_idx and not self.cache_done:
            for _ in range(index_offset - self.stream_idx):
                data = next(self._packet_iter, b"")
                if not data:
                    break
                if self.can_cache:
                    self.stream.append(data)

        self.stream_idx = max(index_offset, 0)
        self.lock.set()

    @property
    def position(self) -> int:
        return round(self.stream_idx / 50)

    def to_start(self):
        if not self.can_cache:
            raise FFAudioProcessNoCache("Can't use cache and seek on song that have over 10mins of duration")

        self.lock.clear()
        self.stream_idx = 0
        self.lock.set()

    def cleanup(self) -> None:
        self._kill_process()
        self._process = self._stdout = self._stdin = MISSING

    def final_cleanup(self) -> None:
        self.lock = self.stream = MISSING

    def all_cleanup(self) -> None:
        self.cleanup()
        self.final_cleanup()


class YTDLSource(discord.AudioSource):
    __slots__ = (
        "source",
        "requester",
        "id",
        "duration",
        "is_stream",
        "thumbnail",
        "title",
        "extractor",
        "author",
        "uri",
    )

    def __init__(
        self, data: dict, requester: discord.Member, source: Optional[FFOpusAudioProcess] = MISSING, *args, **kwargs
    ):
        self.source = source
        for fn in ("read", "is_opus", "seek", "cleanup", "final_cleanup", "all_cleanup", "to_start"):
            setattr(self, fn, getattr(self.source, fn, self.__no_source))

        self.requester: discord.Member = requester

        self.id: int = data.get("id", 0)
        self.duration: int = data.get("duration", 0)
        self.is_stream: bool = kwargs.get("direct", False)
        self.thumbnail: Optional[str] = data.get("thumbnail", None)
        self.title: str = data.get("title", "Unknown title")
        self.extractor: str = data.get("extractor") or kwargs.get("extractor", "None")
        self.author: str = data.get("uploader") or data.get("channel", "Unknown artits")

        if "search" in self.extractor:
            self.uri = data.get("url")
        else:
            self.uri = data.get("webpage_url")

    @staticmethod
    def __no_source():
        logging.warning("No running stream found")

    @staticmethod
    async def __get_raw_data(search, loop=None, ytdl_cls=ytdl, **kwargs) -> Dict:
        loop = loop or asyncio.get_event_loop()

        to_run = partial(ytdl_cls.extract_info, url=search, download=False, **kwargs)
        data: Dict = await loop.run_in_executor(None, to_run)  # type: ignore

        return data

    @classmethod
    async def get_related_tracks(cls, track, bot: discord.Client):
        http_session = bot.http._HTTPClient__session  # type: ignore

        try:
            match track.extractor:
                case "youtube":
                    data = await UsefulMethod.requests(
                        http_session, f"https://yt.funami.tech/api/v1/videos/{track.id}?fields=recommendedVideos"
                    )
                    data = await cls.__get_raw_data(
                        f"https://www.youtube.com/watch?v={random.choice(data['recommendedVideos'])['videoId']}",
                        process=False,
                    )
                    return cls.info_wrapper(data, bot.user)

                case "soundcloud":
                    if (sc := getattr(NamelessConfig, "SOUNDCLOUD", None)) and (sc["user_id"] or sc["client_id"]):
                        data = await cls.__get_raw_data(track.title)
                        return await cls.get_related_tracks(track, bot)

                    data = await UsefulMethod.requests(
                        http_session,
                        f"https://api-v2.soundcloud.com/tracks/{track.id}/related",
                        params={
                            "user_id": NamelessConfig.SOUNDCLOUD["user_id"],
                            "client_id": NamelessConfig.SOUNDCLOUD["client_id"],
                            "limit": "10",
                            "offset": "0",
                        },
                    )
                    data = await cls.__get_raw_data(random.choice(data)["permalink_url"])  # type: ignore
                    return cls.info_wrapper(data, bot.user)

                case _:
                    data = await cls.__get_raw_data(track.title)
                    return await cls.get_related_tracks(track, bot)
        except Exception:
            return None

    @staticmethod
    def maybe_new_extractor(provider, amount) -> YoutubeDL:
        if provider == "youtube" and amount <= 10:
            return ytdl

        config = YTDL_OPTS.copy()
        match provider:
            case "ytmusic":
                config.update(
                    {
                        "default_search": "https://music.youtube.com/search?q=",
                        "playlist_items": f"1-{amount}",
                    }
                )
            case "youtube":
                config["default_search"] = f"ytsearch{amount}"
            case "soundcloud":
                config["default_search"] = f"scsearch{amount}"

        return YoutubeDL(config)

    @classmethod
    async def get_tracks(
        cls, interaction: discord.Interaction, search, amount=10, provider="youtube", loop=None, process=True
    ) -> AsyncGenerator:
        data = await cls.__get_raw_data(
            search, loop, ytdl_cls=cls.maybe_new_extractor(provider, amount), process=process
        )
        if not data:
            return

        if entries := data.get("entries", None):
            for track in entries[:amount]:
                yield cls.info_wrapper(track, interaction.user, extra_info=data)
        else:
            yield cls.info_wrapper(data, interaction.user)

    @classmethod
    async def get_track(
        cls, interaction: discord.Interaction, search, amount=10, provider="youtube", loop=None
    ) -> Optional[Self]:
        return await anext(cls.get_tracks(interaction, search, amount, provider, loop))  # type: ignore

    @classmethod
    def info_wrapper(cls, track, author, extra_info=None) -> Self:
        if extra_info:
            return cls(track, author, extractor=extra_info.get("extractor"), direct=extra_info.get("direct"))
        return cls(track, author, extractor=track.get("extractor"), direct=track.get("direct"))

    @classmethod
    async def generate_stream(cls, data, loop=None) -> Self:
        """We need to regenerate the stream because youtube stream has expired time"""
        loop = loop or asyncio.get_event_loop()
        requester = data.requester

        to_run = partial(ytdl.extract_info, url=data.uri, download=False)
        ret: dict = await loop.run_in_executor(None, to_run)  # type: ignore

        return cls(
            source=FFOpusAudioProcess(ret["url"], **FFMPEG_OPTS, can_cache=data.duration < 600, codec=ret["acodec"]),
            data=ret,
            requester=requester,
        )

    def __del__(self) -> None:
        if self.source:
            return self.source.all_cleanup()


class YTMusicSource(YTDLSource):
    """
    This class is used to represent a YouTube Music stream, taken from Invidious instance.

    This could be useful if you run the bot in an area where Youtube Music has been blocked or is not yet available.
    """

    PARAMS = "fields=videoThumbnails,videoId,title,viewCount,likeCount,author,authorUrl,lengthSeconds"

    def __init__(self, data: dict, requester: discord.Member, *args, **kwargs):
        super().__init__(data, requester, *args, **kwargs)

    def get(self, key: str, _default: Any = None) -> Any:
        if not hasattr(self, key):
            return _default

        return getattr(self, key)

    @staticmethod
    async def _requests(http_session, url, *args, **kwargs) -> Optional[dict]:
        async with http_session.get(url, *args, **kwargs) as resp:
            if resp.status == 200:
                return await resp.json()
            raise asyncio.InvalidStateError(f"Failed to get {url}: Get {resp.status}")

    @classmethod
    async def generate_stream(cls, data, loop=None):
        loop = loop or asyncio.get_event_loop()
        requester = data.requester

        data.url = f"https://vid.puffyan.us/latest_version?id={data.id}&itag=250&local=true"

        return cls(
            source=FFOpusAudioProcess(
                data.url,
                **FFMPEG_OPTS,
                can_cache=data.duration < 600,
                codec="opus",
            ),
            data=data,
            requester=requester,
        )

    @classmethod
    async def indivious_get_track(cls, interaction: discord.Interaction, videoid: str, loop=None):
        # data_search = await cls._requests(
        #     ctx.bot.http._HTTPClient__session,
        #     f"https://yt.funami.tech/api/v1/search/{videoid}?{cls.PARAMS}",
        #     loop=loop,
        # )

        if "youtube" in videoid:
            idx = videoid.find("?v=")
            if idx == -1:
                return

            # dirty way to extract id from url
            videoid = videoid[idx + 3 : idx + 3 + 11]  # noqa: E203

        if len(videoid) != 11:
            return

        req_data = await cls._requests(
            interaction.client.http._HTTPClient__session,  # pyright: ignore
            f"https://yt.funami.tech/api/v1/videos/{videoid}?{cls.PARAMS}",
        )

        if not req_data:
            return

        data = {
            "id": req_data["videoId"],
            "duration": req_data["lengthSeconds"],
            "direct": False,
            "thumbnail": req_data["videoThumbnails"][1]["url"],
            "title": req_data["title"],
            "extractor": "ytmusic",
            "uploader": req_data["author"],
            "author_url": req_data["authorUrl"],
            "webpage_url": f"https://music.youtube.com/watch?v={req_data['videoId']}",
        }

        return cls.info_wrapper(data, interaction.user)
