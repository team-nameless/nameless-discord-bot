import asyncio
import datetime
import io
import logging
import random
import threading
from collections import deque
from functools import partial
from typing import IO, Any, AsyncGenerator, Dict, List, Optional, Union

import discord
import DiscordUtils
from discord import ClientException, VoiceClient, app_commands
from discord.app_commands import Choice
from discord.ext import commands
from discord.ext.commands import Range
from discord.utils import MISSING, escape_markdown
from yt_dlp import DownloadError, YoutubeDL

from nameless import Nameless
from nameless.cogs.checks import MusicCogCheck
from nameless.commons import Utility
from nameless.database import CRUD
from nameless.ui_kit import TrackSelectDropdown, VoteMenu
from NamelessConfig import NamelessConfig

__all__ = ["MusicV2Cog"]

PROVIDER_MAPPING = {
    "youtube": "ytsearch",
    "ytmusic": "https://music.youtube.com/search?q=",
    "soundcloud": "scsearch",
}
FFMPEG_OPTS = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", "options": "-vn"}
YTDL_OPTS = {
    "format": "bestaudio[ext=webm][abr<=?64]/bestaudio[ext=webm]/bestaudio[ext=m4a][abr<=?64]/bestaudio[ext=m4a]/bestaudio/93/best",  # noqa: E501
    "outtmpl": r"downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "extract_flat": "in_playlist",
    "no_warnings": True,
    "default_search": "ytsearch5",
    "playlist_items": "1-200",
    "source_address": "0.0.0.0",
}
ytdl = YoutubeDL(YTDL_OPTS)


class FFAudioProcessNoCache(BaseException):
    pass


class FFAudioProcessSeekError(BaseException):
    pass


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
        self.lock = threading.Lock()

        self.stream: deque = deque()
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
        if not self.can_cache:
            return next(self._packet_iter, b"")

        data = b""
        if not self.cache_done:
            data = next(self._packet_iter, b"")
            self.stream.append(data)
            if not data:
                self.cache_done = True

        if self.cache_done or self.is_seek:
            data = self.stream[self.stream_idx]

        self.stream_idx += 1
        return data

    def seek(self, index_offset: int):
        if not self.can_cache:
            raise FFAudioProcessSeekError(
                "Can't seek because there is no cache avaliable for song that over 10mins in duration"
            )
        if self.stream is MISSING or self._process is MISSING:  # return if trying to seek on a clean stream
            return

        with self.lock:
            self.is_seek = True
            index_offset = max(index_offset * 50 + self.stream_idx, 0)

            if index_offset > self.stream_idx:
                for _ in range(index_offset - self.stream_idx):
                    data = next(self._packet_iter, b"")
                    if not data:
                        break
                    self.stream.append(data)

            self.stream_idx = max(index_offset, 0)

    def to_start(self):
        if not self.can_cache:
            raise FFAudioProcessNoCache("Can't use cache and seek on song that have over 10mins of duration")

        with self.lock:
            self.stream_idx = 0

    def cleanup(self) -> None:
        self._kill_process()
        self._process = self._stdout = self._stdin = MISSING

    def all_cleanup(self) -> None:
        self.cleanup()
        self.lock = self.stream = MISSING


class YTDLSource(discord.AudioSource):
    __slots__ = ("requester", "title", "author", "duration", "extractor", "direct", "uri", "thumbnail", "cleaned")

    def __init__(self, data: dict, requester: discord.Member, *args, **kwargs):
        if source := kwargs.get("source", None):
            self.source: FFOpusAudioProcess = source

        self.requester: discord.Member = requester
        self.cleaned = False
        self.id: int = data.get("id", 0)
        self.duration: int = data.get("duration", 0)
        self.direct: bool = kwargs.get("direct", False)
        self.thumbnail: Optional[str] = data.get("thumbnail", None)
        self.title: str = data.get("title", "Unknown title")
        self.extractor: str = data.get("extractor") or kwargs.get("extractor", "None")
        self.author: str = data.get("uploader") or data.get("channel", "Unknown artits")

        if "search" in self.extractor:
            self.uri = data.get("url")
        else:
            self.uri = data.get("webpage_url")

    @staticmethod
    async def __get_raw_data(search, loop=None, ytdl_cls=ytdl, **kwargs) -> Dict:
        loop = loop or asyncio.get_event_loop()

        to_run = partial(ytdl_cls.extract_info, url=search, download=False, **kwargs)
        data: Dict = await loop.run_in_executor(None, to_run)  # type: ignore

        return data

    @staticmethod
    async def _requests(http_session, url, *args, **kwargs) -> Optional[dict]:
        async with http_session.get(url, *args, **kwargs) as resp:
            if resp.status == 200:
                return await resp.json()
            raise asyncio.InvalidStateError(f"Failed to get {url}: Get {resp.status}")

    @classmethod
    async def get_related_tracks(cls, track, bot: discord.Client):
        http_session = bot.http._HTTPClient__session  # type: ignore

        try:
            match track.extractor:
                case "youtube":
                    data = await cls._requests(
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

                    data = await cls._requests(
                        http_session,
                        f"https://api-v2.soundcloud.com/tracks/{track.id}/related",
                        params={
                            "user_id": NamelessConfig.SOUNDCLOUD["user_id"],
                            "client_id": NamelessConfig.SOUNDCLOUD["client_id"],
                            "limit": "5",
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
        if provider == "youtube" and amount == 5:
            return ytdl

        config = YTDL_OPTS.copy()
        match provider:
            case "ytmusic":
                config.update(
                    {
                        "default_search": PROVIDER_MAPPING[provider],
                        "playlist_items": f"1-{amount}",
                    }
                )
            case "youtube" | "soundcloud":
                config.update(
                    {
                        "default_search": f"{PROVIDER_MAPPING[provider]}{amount}",
                    }
                )
        return YoutubeDL(config)

    @property
    def is_stream(self):
        return self.direct

    @classmethod
    async def get_tracks(
        cls, interaction: discord.Interaction, search, amount=5, provider="youtube", loop=None, process=True
    ) -> AsyncGenerator:
        data = await cls.__get_raw_data(
            search, loop, ytdl_cls=cls.maybe_new_extractor(provider, amount), process=process
        )
        if not data:
            return

        if entries := data.get("entries", None):
            for track in entries:
                yield cls.info_wrapper(track, interaction.user, extra_info=data)
        else:
            yield cls.info_wrapper(data, interaction.user)

    @classmethod
    async def get_track(cls, interaction: discord.Interaction, search, amount=5, provider="youtube", loop=None):
        return await anext(cls.get_tracks(interaction, search, amount, provider, loop))

    @classmethod
    def info_wrapper(cls, track, author, extra_info=None):
        if extra_info:
            return cls(track, author, extractor=extra_info.get("extractor"), direct=extra_info.get("direct"))
        return cls(track, author, extractor=track.get("extractor"), direct=track.get("direct"))

    @classmethod
    async def generate_stream(cls, data, loop=None):
        loop = loop or asyncio.get_event_loop()
        requester = data.requester

        to_run = partial(ytdl.extract_info, url=data.uri, download=False)
        ret: dict = await loop.run_in_executor(None, to_run)  # type: ignore

        return cls(
            source=FFOpusAudioProcess(ret["url"], **FFMPEG_OPTS, can_cache=data.duration < 600, codec=ret["acodec"]),
            data=ret,
            requester=requester,
        )

    def read(self) -> bytes:
        return self.source.read()

    def is_opus(self) -> bool:
        return self.source.is_opus()

    def cleanup(self) -> None:
        source: FFOpusAudioProcess
        if source := getattr(self, "source", None):  # type: ignore
            source.all_cleanup()

        self.cleaned = True


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
    async def indivious_get_track(cls, interaction: discord.Interaction, videoid, loop=None):
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


class MainPlayer:
    __slots__ = (
        "client",
        "_guild",
        "_channel",
        "_cog",
        "queue",
        "signal",
        "track",
        "total_duration",
        "position",
        "repeat",
        "task",
        "loop_play_count",
        "allow_np_msg",
        "play_related_tracks",
        "stopped",
    )

    def __init__(self, interaction: discord.Interaction, cog) -> None:
        self.client = interaction.client
        self._guild = interaction.guild
        self._channel = interaction.channel
        self._cog = cog

        self.queue: asyncio.Queue[YTDLSource] = asyncio.Queue()
        self.signal = asyncio.Event()

        self.track: YTDLSource = MISSING
        self.position = 0
        self.total_duration = 0

        self.repeat = False
        self.stopped = False
        self.allow_np_msg = True
        self.loop_play_count = 0
        self.play_related_tracks = False

        if not self._guild and not isinstance(self._guild, discord.Guild):
            logging.error("Wait what? There is no guild here!")
            raise AttributeError(f"Try to access guild attribute, got {self._guild.__class__.__name__} instead")

        self.task: asyncio.Task = self.client.loop.create_task(self.create())
        setattr(self._guild.voice_client, "is_empty", self.is_empty)

    @staticmethod
    def build_embed(track: YTDLSource, header: str):
        return (
            discord.Embed(timestamp=datetime.datetime.now(), color=discord.Color.orange())
            .set_author(
                name=header,
                icon_url=getattr(track.requester.avatar, "url", None),
            )
            .set_thumbnail(url=track.thumbnail)
            .add_field(
                name="Title",
                value=escape_markdown(track.title),
                inline=False,
            )
            .add_field(
                name="Author",
                value=escape_markdown(track.author),
            )
            .add_field(
                name="Source",
                value=escape_markdown(track.uri) if track.uri else "N/A",
            )
        )

    @property
    def is_empty(self):
        return self.queue.empty()

    def clear_queue(self):
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def create(self):
        await self.client.wait_until_ready()

        while not self.client.is_closed():
            try:
                self.signal.clear()
                if not self.repeat or not self.track:
                    self.track = await self.queue.get()
                    self.stopped = False

                    if self.allow_np_msg:
                        await self._channel.send(embed=self.build_embed(self.track, "Now playing"))  # pyright: ignore

                    self.track = await self.track.generate_stream(self.track)
                    self.total_duration -= self.track.duration
                else:
                    self.loop_play_count += 1
                    try:
                        self.track.source.to_start()
                    except FFAudioProcessNoCache:
                        self.track = await YTDLSource.generate_stream(self.track)

                self._guild.voice_client.play(  # type: ignore
                    self.track, after=lambda _: self.client.loop.call_soon_threadsafe(self.signal.set)
                )

            except AttributeError as err:
                logging.error(
                    "We no longer connect to guild %s, but somehow we still in. Time to destroy!", self._guild.id
                )
                logging.error("AttributeError raised, error was: %s", err)
                return self.destroy(self._guild)

            except Exception as e:
                logging.error(
                    "I'm not sure what went wrong when we tried to process the request in guild %s. Anyway, I'm going to sleep. Here is the error: %s",  # noqa: E501
                    self._guild.id,
                    str(e),
                )
                return await self._channel.send(  # pyright: ignore
                    f"There was an error processing your song.\n" f"```css\n[{e}]\n```"
                )

            finally:
                await self.signal.wait()

            if not self.repeat:
                if self.play_related_tracks and self.queue.empty() and not self.stopped:
                    data = await self.track.get_related_tracks(self.track, self.client)
                    if data:
                        await self.queue.put(data)

                self.loop_play_count = 0
                self.track.cleanup()
                self.track = None

            if not self._guild.voice_client:  # random check
                return self.destroy(self._guild)

    def destroy(self, guild):
        """Disconnect and cleanup the player."""
        return self.client.loop.create_task(self._cog.cleanup(guild))


class MusicV2Cog(commands.Cog):
    def __init__(self, bot: Nameless):
        self.bot = bot
        self.players: Dict[int, MainPlayer] = {}

    def get_player(self, interaction: discord.Interaction):
        """Retrieve the guild player, or generate one."""
        try:
            player = self.players[interaction.guild.id]
        except KeyError:
            player = MainPlayer(interaction, self)
            self.players[interaction.guild.id] = player

        return player

    async def cleanup(self, guild_id: int):
        try:
            player = self.players[guild_id]
            player._guild.voice_client.stop()  # type: ignore
            player.task.cancel()

            if not player.signal.is_set():
                player.signal.set()

            await player._guild.voice_client.disconnect()  # type: ignore
            if player.track:  # edge-case
                player.track.cleanup()

            del self.players[guild_id]

        except asyncio.CancelledError:
            pass
        except KeyError:
            pass

    @staticmethod
    def generate_embeds_from_tracks(
        tracks: List,
    ) -> List[discord.Embed]:
        embeds: List[discord.Embed] = []
        txt = ""

        for idx, track in enumerate(tracks):
            upcoming = (
                f"{idx + 1} - "
                f"[{escape_markdown(track.title)} by {escape_markdown(track.author)}]"
                f"({track.uri})\n"
            )

            if len(txt) + len(upcoming) > 2048:
                eb = discord.Embed(
                    title="Tracks currently in list",
                    color=discord.Color.orange(),
                    description=txt,
                )
                embeds.append(eb)
                txt = upcoming
            else:
                txt += upcoming

        embeds.append(
            discord.Embed(
                title="Tracks currently in list",
                color=discord.Color.orange(),
                description=txt,
            )
        )

        return embeds

    @staticmethod
    def generate_embeds_from_queue(q: asyncio.Queue) -> List[discord.Embed]:
        # Some workaround to get list from asyncio.Queue
        copycat: List = q._queue.copy()  # type: ignore
        idx = 0
        txt = ""
        embeds: List[discord.Embed] = []

        try:
            while track := copycat.pop():
                upcoming = (
                    f"{idx + 1} - "
                    f"[{escape_markdown(track.title)} by {escape_markdown(track.author)}]"
                    f"({track.uri})\n"
                )

                if len(txt) + len(upcoming) > 2048:
                    eb = discord.Embed(
                        title="Tracks currently in queue",
                        color=discord.Color.orange(),
                        description=txt,
                    )
                    embeds.append(eb)
                    txt = upcoming
                else:
                    txt += upcoming

                idx += 1
        except IndexError:
            # Nothing else in queue
            pass
        finally:
            # Add the last bit
            embeds.append(
                discord.Embed(
                    title="Tracks currently in queue",
                    color=discord.Color.orange(),
                    description=txt,
                )
            )

        return embeds

    @staticmethod
    async def show_paginated_tracks(interaction: discord.Interaction, embeds: List[discord.Embed], **kwargs):
        p = DiscordUtils.Pagination.AutoEmbedPaginator(interaction, **kwargs)
        await p.run(embeds[:25])

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Handle voice state updates, auto-disconnect the bot, or maybe add a logging system in here :eyes:"""
        if not self.players.get(member.guild.id):  # We're not in this channel? Let's return the function
            return

        vc = member.guild.voice_client.channel
        if len(vc.members) == 1:  # type: ignore  # There is only one person
            if vc.members[0].id == self.bot.user.id:  # type: ignore  # And that person is us
                logging.debug(
                    "Guild player %s still connected even if it is removed from voice, disconnecting",
                    member.guild.id,
                )
                return await self.cleanup(member.guild.id)

        if member.id == self.bot.user.id:  # type: ignore  # We been kicked out of the voice chat
            if not after.channel:
                return await self.cleanup(member.guild.id)

    music = app_commands.Group(name="music", description="Music related commands")

    @music.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_in_voice)
    async def connect(self, interaction: discord.Interaction):
        """Connect to your current voice channel"""
        await interaction.response.defer()

        await self.bot.wait_until_ready()
        try:
            await interaction.user.voice.channel.connect(self_deaf=True)  # type: ignore
            await interaction.followup.send("Connected to your current voice channel")
            self.get_player(interaction)
        except ClientException:
            await interaction.followup.send("Already connected")

    @music.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.bot_in_voice)
    async def disconnect(self, interaction: discord.Interaction):
        """Disconnect from my current voice channel"""
        await interaction.response.defer()

        try:
            await self.cleanup(interaction.guild.id)
            await interaction.followup.send("Disconnected from my own voice channel")
        except AttributeError:
            await interaction.followup.send("Already disconnected")

    @music.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def loop(self, interaction: discord.Interaction):
        """Toggle loop playback of current track"""
        await interaction.response.defer()

        player = self.get_player(interaction)
        player.repeat = not player.repeat
        await interaction.followup.send(f"Loop set to {'on' if player.repeat else 'off'}")

    @music.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def toggle(self, interaction: discord.Interaction):
        """Toggle for current playback."""
        vc: VoiceClient = interaction.guild.voice_client  # type: ignore

        if vc.is_paused():
            vc.resume()
            action = "Resumed"
        else:
            vc.pause()
            action = "Paused"

        await interaction.followup.send(action)

    @music.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def pause(self, interaction: discord.Interaction):
        """Pause current playback"""
        await interaction.response.defer()

        vc: VoiceClient = interaction.guild.voice_client  # type: ignore

        if vc.is_paused():
            await interaction.followup.send("Already paused")
            return

        vc.pause()
        await interaction.followup.send("Paused")

    @music.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_is_silent)
    async def resume(self, interaction: discord.Interaction):
        """Resume current playback, if paused"""
        await interaction.response.defer()

        vc: VoiceClient = interaction.guild.voice_client  # type: ignore

        if not vc.is_paused():
            await interaction.followup.send("Already resuming")
            return

        vc.resume()
        await interaction.followup.send("Resumed")

    @music.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def stop(self, interaction: discord.Interaction):
        """Stop current playback."""
        await interaction.response.defer()

        vc: VoiceClient = interaction.guild.voice_client  # type: ignore
        player = self.get_player(interaction)

        vc.stop()
        player.stopped = True
        await interaction.followup.send("Stopped")

    @music.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def skip(self, interaction: discord.Interaction):
        """Skip a song."""
        await interaction.response.defer()

        vc: VoiceClient = interaction.guild.voice_client  # type: ignore
        player: MainPlayer = self.get_player(interaction)
        track: YTDLSource = player.track

        if await VoteMenu("skip", track.title, interaction, vc).start():
            vc.stop()

    @music.command()
    @app_commands.guild_only()
    @app_commands.describe(offset="Position to seek to in milliseconds, defaults to run from start")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def seek(self, interaction: discord.Interaction, offset: int = 0):
        """Seek to a position in a track"""
        await interaction.response.defer()

        player: MainPlayer = self.get_player(interaction)
        source: FFOpusAudioProcess = player.track.source

        try:
            source.seek(offset)
            await interaction.response.send_message(content="✅")
        except Exception as err:
            await interaction.response.send_message(content=f"{err.__class__.__name__}: {str(err)}")
            logging.error("%s: %s", err.__class__.__name__, str(err))

    @music.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def toggle_play_now(self, interaction: discord.Interaction):
        """Toggle 'Now playing' message delivery"""
        await interaction.response.defer()
        player: MainPlayer = self.get_player(interaction)

        player.allow_np_msg = not player.allow_np_msg
        await interaction.followup.send(f"'Now playing' delivery is now {'on' if player.allow_np_msg else 'off'}")

    @music.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def now_playing(self, interaction: discord.Interaction):
        """Check now playing song"""
        await interaction.response.defer()

        vc: VoiceClient = interaction.guild.voice_client  # type: ignore
        player: MainPlayer = self.get_player(interaction)
        track: YTDLSource = player.track

        dbg = CRUD.get_or_create_guild_record(interaction.guild)
        if not dbg:
            logging.error("Oh no. The database is gone! What do we do now?!!")
            raise AttributeError(f"Can't find guild id '{interaction.guild.id}'. Or maybe the database is gone?")

        next_tr: Optional[YTDLSource] = None
        if not player.queue.empty():
            next_tr = player.queue._queue[0]  # type: ignore

        await interaction.followup.send(
            embed=player.build_embed(track=track, header="Now playing")
            .add_field(
                name="Looping",
                value="This is a stream"
                if track.is_stream
                else f"Looped {getattr(vc, 'loop_play_count')} time(s)"
                if player.repeat is True
                else False,
            )
            .add_field(name="Paused", value=vc.is_paused())
            .add_field(
                name="Next track",
                value=f"[{escape_markdown(next_tr.title)} "
                f"by {escape_markdown(next_tr.author)}]"
                f"({next_tr.uri[:100]})"
                if next_tr
                else None,
            )
        )

    @music.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def autoplay(self, interaction: discord.Interaction):
        """Automatically play the next song in the queue"""
        await interaction.response.defer()

        player: MainPlayer = self.get_player(interaction)
        player.play_related_tracks = not player.play_related_tracks

        await interaction.followup.send(f"Autoplay is now {'on' if player.play_related_tracks else 'off'}")

    queue = app_commands.Group(name="queue", description="Commands related to queue management.")

    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def view(self, interaction: discord.Interaction):
        """View current queue"""
        await interaction.response.defer()

        player: MainPlayer = self.get_player(interaction)

        embeds = self.generate_embeds_from_queue(player.queue)
        self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds))

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(idx="The index to remove (1-based)")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def delete(self, interaction: discord.Interaction, idx: Range[int, 1]):
        """Remove track from queue"""
        await interaction.response.defer()

        idx -= 1
        player: MainPlayer = self.get_player(interaction)
        queue: List = player.queue._queue  # type: ignore

        if idx > player.queue.qsize() or idx < 0:
            return await interaction.followup.send("The track number you just entered is not available. Check again")

        deleted_track: YTDLSource = queue.pop(idx)
        await interaction.followup.send(
            f"Deleted track at position #{idx}: **{deleted_track.title}** from **{deleted_track.author}**"
        )

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(
        search="Search query", provider="Pick a provider to search from", amount="How much results to show"
    )
    @app_commands.choices(provider=[Choice(name=k, value=k) for k in PROVIDER_MAPPING])
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def add(self, interaction: discord.Interaction, search: str, provider: str = "youtube", amount: int = 5):
        """Add selected track(s) to queue"""
        await interaction.response.defer()

        player: MainPlayer = self.get_player(interaction)

        if provider == "ytmusic":
            search = f"{search}#songs"

        try:
            tracks: List[YTDLSource] = [tr async for tr in YTDLSource.get_tracks(interaction, search, amount, provider)]
        except DownloadError:
            if "youtube" in search:
                tracks = [await YTMusicSource.indivious_get_track(interaction, search)]  # type: ignore
            else:
                tracks = []

        if not tracks:
            await interaction.followup.send(f"No tracks found for '{search}' on '{provider}'.")
            return

        soon_to_add_queue: List[YTDLSource] = []
        if ":search" in tracks[0].extractor:
            soon_to_add_queue = tracks
        else:
            if len(tracks) > 1:
                dropdown: Union[discord.ui.Item[discord.ui.View], TrackSelectDropdown] = TrackSelectDropdown(
                    tracks  # pyright: ignore
                )
                view = discord.ui.View().add_item(dropdown)
                await interaction.response.edit_message(content="Tracks found", view=view)

                if await view.wait():
                    await interaction.response.edit_message(content="Timed out!", view=None, delete_after=30)
                    return

                vals = dropdown.values
                if not vals or "Nope" in vals:
                    await interaction.response.edit_message(content="OK bye", delete_after=5, view=None)
                    return

                for val in vals:
                    idx = int(val)
                    soon_to_add_queue.append(tracks[idx])
                    await player.queue.put(tracks[idx])
            else:
                soon_to_add_queue = tracks
                await player.queue.put(tracks[0])

        player.total_duration += sum(tr.duration for tr in soon_to_add_queue)
        await interaction.response.edit_message(
            content=f"Added {len(soon_to_add_queue)} tracks into the queue", view=None
        )
        if len(soon_to_add_queue) <= 25:
            embeds = [player.build_embed(track, f"Requested by {track.requester}") for track in soon_to_add_queue]
            self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds, timeout=15))

    @music.command()
    @app_commands.guilds(*getattr(NamelessConfig, "GUILD_IDs", []))
    @app_commands.guild_only()
    @app_commands.describe(url="Radio url")
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_is_silent)
    async def radio(self, interaction: discord.Interaction, url: str):
        """Play a radio"""
        await interaction.response.defer()

        if not Utility.is_an_url(url):
            await interaction.followup.send("You need to provide a direct URL")
            return

        await self.add(interaction, url, True)  # type: ignore

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(before="Old position", after="New position")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def move(self, interaction: discord.Interaction, before: Range[int, 1], after: Range[int, 1]):
        """Move track to new position"""
        await interaction.response.defer()

        player: MainPlayer = self.get_player(interaction)
        int_queue = player.queue._queue  # type: ignore
        queue_length = player.queue.qsize()

        if not (before != after and 1 <= before <= queue_length and 1 <= after <= queue_length):
            await interaction.followup.send("Invalid queue position(s)")
            return

        temp = int_queue[before - 1]
        del int_queue[before - 1]
        int_queue.insert(after - 1, temp)

        await interaction.followup.send(f"Moved track #{before} to #{after}")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(pos="Current position", diff="Relative difference")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def move_relative(self, interaction: discord.Interaction, pos: Range[int, 1], diff: Range[int, 0]):
        """Move track to new position using relative difference"""
        await self.move(interaction, pos, pos + diff)  # pyright: ignore

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    @app_commands.describe(
        pos1="First track position (1-indexed)",
        pos2="Second track position (1-indexed)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def swap(self, interaction: discord.Interaction, pos1: Range[int, 1], pos2: Range[int, 1]):
        """Swap two tracks."""
        await interaction.response.defer()

        player: MainPlayer = self.get_player(interaction)

        q = player.queue._queue  # type: ignore
        q_length = len(q)

        if not (1 <= pos1 <= q_length and 1 <= pos2 <= q_length):
            await interaction.followup.send(f"Invalid position(s): ({pos1}, {pos2})")
            return

        q[pos1 - 1], q[pos2 - 1] = q[pos2 - 1], q[pos1 - 1]
        await interaction.followup.send(f"Swapped track #{pos1} and #{pos2}")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shuffle(self, interaction: discord.Interaction):
        """Shuffle the queue"""
        await interaction.response.defer()

        vc: VoiceClient = interaction.guild.voice_client  # type: ignore

        random.shuffle(vc.queue._queue)  # type: ignore
        await interaction.followup.send("Shuffled the queue")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def clear(self, interaction: discord.Interaction):
        """Clear the queue"""
        await interaction.response.defer()

        vc = interaction.guild.voice_client  # type: ignore
        player: MainPlayer = self.get_player(interaction)

        if await VoteMenu("clear", "queue", interaction, vc).start():  # pyright: ignore
            player.clear_queue()
            await interaction.followup.send("Cleared the queue")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def force_clear(self, interaction: discord.Interaction):
        """Clear the queue"""
        await interaction.response.defer()
        player: MainPlayer = self.get_player(interaction)

        try:
            player.clear_queue()
            await interaction.followup.send("Cleared the queue")
        except Exception as e:
            logging.error(
                "User %s try to forcely clear the queue in %s, but we encounter some trouble.",
                interaction.user.id,
                player._guild.id,
            )
            logging.error("MusicCog.force_clear raise an error: [%s] %s", e.__class__.__name__, str(e))


async def setup(bot: Nameless):
    if bot.get_cog("MusicV1Cog"):
        raise commands.ExtensionFailed(__name__, RuntimeError("can't load MusicV1 and MusicV2 at the same time."))

    await bot.add_cog(MusicV2Cog(bot))
    logging.info("Cog of %s added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog("MusicV2Cog")
    logging.warning("Cog of %s removed!", __name__)
