import asyncio
import datetime
import io
import logging
import math
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
from yt_dlp import YoutubeDL

from nameless import Nameless
from nameless.cogs.checks import MusicCogCheck
from nameless.commons import Utility
from nameless.database import CRUD
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


class VoteMenuView(discord.ui.View):
    __slots__ = ("user", "value")

    def __init__(
        self,
        action: str,
        content: str,
        ctx: commands.Context,
        timeout: Optional[float] = None,
    ):
        super().__init__(timeout=timeout)

        self.ctx = ctx
        self.action = action
        self.content = f"{content[:50]}..."

        self.max_vote = math.ceil(len([m for m in ctx.voice_client.channel.members if not m.bot]) / 2)  # type: ignore
        self.total_vote = 1

        self.approve_member: List[str] = [ctx.author.mention]
        self.disapprove_member: List[str] = []

        self.message: discord.Message = MISSING
        ctx.bot.loop.create_task(self.update())

    def __eb(self):
        return (
            discord.Embed(
                title=f"Vote {self.action} {self.content}",
                description=f"Total vote: {self.total_vote}/{self.max_vote}",
            )
            .add_field(
                name="Approve",
                value="\n".join(self.approve_member),
                inline=True,
            )
            .add_field(
                name="Disapprove",
                value="\n".join(self.disapprove_member) if self.disapprove_member else "None",
                inline=True,
            )
            .set_footer(text=f"Requested by {self.ctx.author.name}")
        )

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.approve_member.append(interaction.user.mention)
        await self.update()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey, emoji="❌")
    async def disapprove(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.disapprove_member.append(interaction.user.mention)
        await self.update()

    async def send_or_edit(self, **kwargs):
        if self.message:
            self.message = await self.message.edit(**kwargs)
            return

        self.message = await self.ctx.send(**kwargs)

    async def update(self):
        if self.max_vote <= 1:
            self.stop()
            return

        self.total_vote += 1
        await self.send_or_edit(embed=self.__eb(), view=self)

        if self.total_vote == self.max_vote:
            self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:  # pylint: disable=arguments-differ
        if interaction.user.mention in self.approve_member or interaction.user.mention in self.disapprove_member:
            return False

        await interaction.response.defer()
        return True


class VoteMenu:
    __slots__ = ("view",)

    def __init__(
        self,
        action: str,
        content: str,
        ctx: commands.Context,
    ):
        self.view = VoteMenuView(action, content, ctx)

    async def start(self):
        await self.view.wait()

        pred = True
        if self.view.max_vote > 1:
            pred = (
                len(self.view.disapprove_member) < len(self.view.approve_member) and len(self.view.approve_member) > 1
            )

        if pred:
            await self.view.send_or_edit(
                content=f"{self.view.action.title()} {self.view.content}!", embed=None, view=None
            )
        else:
            await self.view.send_or_edit(content=f"Not enough votes to {self.view.action}!", embed=None, view=None)

        return pred


class TrackPickDropdown(discord.ui.Select):
    def __init__(self, tracks: List):
        options = [
            discord.SelectOption(
                label="I don't see my results here",
                description="Nothing here!",
                value="Nope",
                emoji="❌",
            )
        ] + [
            discord.SelectOption(
                label=f"{track.author} - {track.title}"[:100],
                description=track.uri[:100] if track.uri else "No URI",
                value=str(index),
            )
            for index, track in enumerate(tracks)
        ]

        super().__init__(
            custom_id="music-pick-select",
            placeholder="Choose your tracks",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, _: discord.Interaction) -> Any:
        v: Optional[discord.ui.View] = self.view
        if v:
            v.stop()


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
            raise FFAudioProcessNoCache("Can't use cache and seek on audio that have over 10mins of duration")

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

    def __init__(self, data, requester, *args, **kwargs):
        if source := kwargs.get("source", None):
            self.source: FFOpusAudioProcess = source

        self.requester: discord.Member = requester
        self.cleaned = False
        self.id = data.get("id", 0)
        self.duration = data.get("duration", 0)
        self.direct = kwargs.get("direct", False)
        self.thumbnail = data.get("thumbnail", None)
        self.title = data.get("title", "Unknown title")
        self.extractor = data.get("extractor") or kwargs.get("extractor", "None")
        self.author = data.get("uploader") or data.get("channel", "Unknown artits")

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

    @classmethod
    async def get_related_tracks(cls, track, bot: Nameless):
        http_session = bot.http._HTTPClient__session  # type: ignore

        async def _requests(url, *args, **kwargs) -> Optional[dict]:
            async with http_session.get(url, *args, **kwargs) as resp:
                if resp.status == 200:
                    return await resp.json()
                raise asyncio.InvalidStateError(f"Failed to get related tracks: Get {resp.status}")

        try:
            match track.extractor:
                case "youtube":
                    data = await _requests(f"https://yt.funami.tech/api/v1/videos/{track.id}?fields=recommendedVideos")
                    data = await cls.__get_raw_data(
                        f"https://www.youtube.com/watch?v={random.choice(data['recommendedVideos'])['videoId']}",
                        process=False,
                    )
                    return cls.info_wrapper(data, bot.user)

                case "soundcloud":
                    if (sc := getattr(NamelessConfig, "SOUNDCLOUD", None)) and (sc["user_id"] or sc["client_id"]):
                        data = await cls.__get_raw_data(track.title)
                        return await cls.get_related_tracks(track, bot)

                    data = await _requests(
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

    def is_stream(self):
        return self.direct

    @classmethod
    async def get_tracks(
        cls, ctx: commands.Context, search, amount, provider, loop=None, process=False
    ) -> AsyncGenerator:
        data = await cls.__get_raw_data(
            search, loop, ytdl_cls=cls.maybe_new_extractor(provider, amount), process=process
        )
        if not data:
            return

        if entries := data.get("entries", None):
            for track in entries:
                yield cls.info_wrapper(track, ctx.author, extra_info=data)
        else:
            yield cls.info_wrapper(data, ctx.author)

    @classmethod
    async def get_track(cls, ctx: commands.Context, search, loop=None):
        return await anext(cls.get_tracks(ctx, search, 5, search, loop))

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


class MainPlayer:
    __slots__ = (
        "client",
        "_guild",
        "_channel",
        "_cog",
        "queue",
        "next",
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

    def __init__(self, ctx: commands.Context, cog) -> None:
        self.client = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = cog

        self.queue: asyncio.Queue[YTDLSource] = asyncio.Queue()
        self.next = asyncio.Event()

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

        self.task: asyncio.Task = ctx.bot.loop.create_task(self.create())
        setattr(self._guild.voice_client, "is_queue_empty", self.is_queue_empty)

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

    def is_queue_empty(self):
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
                self.next.clear()
                if not self.repeat or not self.track:
                    self.track = await self.queue.get()
                    self.stopped = False

                    if self.allow_np_msg:
                        await self._channel.send(embed=self.build_embed(self.track, "Now playing"))
                    self.track = await YTDLSource.generate_stream(self.track)
                    self.total_duration -= self.track.duration
                else:
                    self.loop_play_count += 1
                    try:
                        self.track.source.to_start()
                    except FFAudioProcessNoCache:
                        self.track = await YTDLSource.generate_stream(self.track)

                self._guild.voice_client.play(  # type: ignore
                    self.track, after=lambda _: self.client.loop.call_soon_threadsafe(self.next.set)
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
                return await self._channel.send(f"There was an error processing your song.\n" f"```css\n[{e}]\n```")

            finally:
                await self.next.wait()

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

    def get_player(self, ctx: commands.Context):
        """Retrieve the guild player, or generate one."""
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MainPlayer(ctx, self)
            self.players[ctx.guild.id] = player

        return player

    async def cleanup(self, guild_id: int):
        try:
            player = self.players[guild_id]
            player._guild.voice_client.stop()  # type: ignore
            player.task.cancel()

            if not player.next.is_set():
                player.next.set()

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
    async def show_paginated_tracks(ctx: commands.Context, embeds: List[discord.Embed], **kwargs):
        p = DiscordUtils.Pagination.AutoEmbedPaginator(ctx, **kwargs)
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

    async def __internal_play(self, ctx: commands.Context, url: str, is_radio: bool = False):
        if is_radio:
            dbg = CRUD.get_or_create_guild_record(ctx.guild)
            dbg.radio_start_time = discord.utils.utcnow()
            CRUD.save_changes()

        await self.__internal_play2(ctx, url, is_radio)

    async def __internal_play2(self, ctx: commands.Context, url: str, is_radio: bool = False):
        player = self.get_player(ctx)
        track = await YTDLSource.get_track(ctx, url)

        if track:
            if is_radio and not track.is_stream():
                raise commands.CommandError("Radio track must be a stream")
            await player.queue.put(track)
        else:
            raise commands.CommandError(f"No tracks found for {url}")

    @commands.hybrid_group(fallback="radio")
    @app_commands.guilds(*getattr(NamelessConfig, "GUILD_IDs", []))
    @commands.guild_only()
    @app_commands.describe(url="Radio url")
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_silent)
    async def music(self, ctx: commands.Context, url: str):
        """Play a radio"""
        await ctx.defer()

        if not Utility.is_an_url(url):
            await ctx.send("You need to provide a direct URL")
            return

        await self.__internal_play(ctx, url, True)

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_in_voice)
    async def connect(self, ctx: commands.Context):
        """Connect to your current voice channel"""
        await ctx.defer()

        try:
            await ctx.author.voice.channel.connect(self_deaf=True)  # type: ignore
            await ctx.send("Connected to your current voice channel")
            self.get_player(ctx)
        except ClientException:
            await ctx.send("Already connected")

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.bot_in_voice)
    async def disconnect(self, ctx: commands.Context):
        """Disconnect from my current voice channel"""
        await ctx.defer()

        try:
            await self.cleanup(ctx.guild.id)
            await ctx.send("Disconnected from my own voice channel")
        except AttributeError:
            await ctx.send("Already disconnected")

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def loop(self, ctx: commands.Context):
        """Toggle loop playback of current track"""
        await ctx.defer()

        player = self.get_player(ctx)
        player.repeat = not player.repeat
        await ctx.send(f"Loop set to {'on' if player.repeat else 'off'}")

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_something)
    async def toggle(self, ctx: commands.Context):
        """Toggle for current playback."""
        vc: VoiceClient = ctx.voice_client  # type: ignore

        if vc.is_paused():
            vc.resume()
            action = "Resumed"
        else:
            vc.pause()
            action = "Paused"

        await ctx.send(action)

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_something)
    async def pause(self, ctx: commands.Context):
        """Pause current playback"""
        await ctx.defer()

        vc: VoiceClient = ctx.voice_client  # type: ignore

        if vc.is_paused():
            await ctx.send("Already paused")
            return

        vc.pause()
        await ctx.send("Paused")

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_silent)
    async def resume(self, ctx: commands.Context):
        """Resume current playback, if paused"""
        await ctx.defer()

        vc: VoiceClient = ctx.voice_client  # type: ignore

        if not vc.is_paused():
            await ctx.send("Already resuming")
            return

        vc.resume()
        await ctx.send("Resumed")

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_something)
    async def stop(self, ctx: commands.Context):
        """Stop current playback."""
        await ctx.defer()

        vc: VoiceClient = ctx.voice_client  # type: ignore
        player = self.get_player(ctx)

        vc.stop()
        player.stopped = True
        await ctx.send("Stopped")

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def skip(self, ctx: commands.Context):
        """Skip a song."""
        await ctx.defer()

        vc: VoiceClient = ctx.voice_client  # type: ignore
        player: MainPlayer = self.get_player(ctx)
        track: YTDLSource = player.track

        if await VoteMenu("skip", track.title, ctx).start():
            vc.stop()

    @music.command()
    @commands.guild_only()
    @app_commands.describe(offset="Position to seek to in milliseconds, defaults to run from start")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def seek(self, ctx: commands.Context, offset: int = 0):
        """Seek to a position in a track"""
        await ctx.defer()

        player: MainPlayer = self.get_player(ctx)
        source: FFOpusAudioProcess = player.track.source

        try:
            source.seek(offset)
            if ctx.message:
                await ctx.message.add_reaction("✅")
            else:
                await ctx.send("✅")
        except Exception as err:
            await ctx.send(f"{err.__class__.__name__}: {str(err)}")
            logging.error("%s: %s", err.__class__.__name__, str(err))

    @music.command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def toggle_play_now(self, ctx: commands.Context):
        """Toggle 'Now playing' message delivery"""
        await ctx.defer()
        player: MainPlayer = self.get_player(ctx)

        player.allow_np_msg = not player.allow_np_msg
        await ctx.send(f"'Now playing' delivery is now {'on' if player.allow_np_msg else 'off'}")

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_something)
    async def now_playing(self, ctx: commands.Context):
        """Check now playing song"""
        await ctx.defer()

        vc: VoiceClient = ctx.voice_client  # type: ignore
        player: MainPlayer = self.get_player(ctx)
        track: YTDLSource = player.track

        is_stream = track.is_stream()
        dbg = CRUD.get_or_create_guild_record(ctx.guild)
        if not dbg:
            logging.error("Oh no. The database is gone! What do we do now?!!")
            raise AttributeError(f"Can't find guild id '{ctx.guild.id}'. Or maybe the database is gone?")

        next_tr: Optional[YTDLSource] = None
        if not player.queue.empty():
            next_tr = player.queue._queue[0]  # type: ignore

        await ctx.send(
            embed=player.build_embed(track=track, header="Now playing")
            .add_field(
                name="Looping",
                value="This is a stream"
                if is_stream
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
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def autoplay(self, ctx: commands.Context):
        """Automatically play the next song in the queue"""
        await ctx.defer()

        player: MainPlayer = self.get_player(ctx)
        player.play_related_tracks = not player.play_related_tracks

        await ctx.send(f"Autoplay is now {'on' if player.play_related_tracks else 'off'}")

    @music.group(fallback="view")
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.queue_has_element)
    async def queue(self, ctx: commands.Context):
        """View current queue"""
        await ctx.defer()

        player: MainPlayer = self.get_player(ctx)

        embeds = self.generate_embeds_from_queue(player.queue)
        self.bot.loop.create_task(self.show_paginated_tracks(ctx, embeds))

    @queue.command()
    @commands.guild_only()
    @app_commands.describe(idx="The index to remove (1-based)")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.queue_has_element)
    async def delete(self, ctx: commands.Context, idx: Range[int, 1]):
        """Remove track from queue"""
        await ctx.defer()

        idx -= 1
        player: MainPlayer = self.get_player(ctx)
        queue: List = player.queue._queue  # type: ignore

        if idx > player.queue.qsize() or idx < 0:
            return await ctx.send("The track number you just entered is not available. Check again")

        deleted_track: YTDLSource = queue.pop(idx)
        await ctx.send(f"Deleted track at position #{idx}: **{deleted_track.title}** from **{deleted_track.author}**")

    @queue.command()
    @commands.guild_only()
    @app_commands.describe(
        search="Search query", provider="Pick a provider to search from", amount="How much results to show"
    )
    @app_commands.choices(provider=[Choice(name=k, value=k) for k in PROVIDER_MAPPING])
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def add(self, ctx: commands.Context, search: str, provider: str = "youtube", amount: int = 5):
        """Add selected track(s) to queue"""
        await ctx.defer()
        m = await ctx.send("Searching...")

        player: MainPlayer = self.get_player(ctx)

        if provider == "ytmusic":
            search = f"{search}#songs"

        tracks: List[YTDLSource] = [tr async for tr in YTDLSource.get_tracks(ctx, search, amount, provider)]
        if not tracks:
            await ctx.send(f"No tracks found for '{search}' on '{provider}'.")
            return

        soon_to_add_queue: List[YTDLSource] = []
        if ":search" in tracks[0].extractor:
            soon_to_add_queue = tracks
        else:
            if len(tracks) > 1:
                dropdown: Union[discord.ui.Item[discord.ui.View], TrackPickDropdown] = TrackPickDropdown(tracks)
                view = discord.ui.View().add_item(dropdown)
                await m.edit(content="Tracks found", view=view)

                if await view.wait():
                    await m.edit(content="Timed out!", view=None, delete_after=30)
                    return

                vals = dropdown.values
                if not vals or "Nope" in vals:
                    await m.delete()
                    return

                for val in vals:
                    idx = int(val)
                    soon_to_add_queue.append(tracks[idx])
                    await player.queue.put(tracks[idx])
            else:
                soon_to_add_queue = tracks
                await player.queue.put(tracks[0])

        player.total_duration += sum(tr.duration for tr in soon_to_add_queue)
        await m.edit(content=f"Added {len(soon_to_add_queue)} tracks into the queue", view=None)
        if len(soon_to_add_queue) <= 25:
            embeds = [player.build_embed(track, f"Requested by {track.requester}") for track in soon_to_add_queue]
            self.bot.loop.create_task(self.show_paginated_tracks(ctx, embeds, timeout=15))

    @queue.command()
    @commands.guild_only()
    @app_commands.describe(before="Old position", after="New position")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.queue_has_element)
    async def move(self, ctx: commands.Context, before: Range[int, 1], after: Range[int, 1]):
        """Move track to new position"""
        await ctx.defer()

        player: MainPlayer = self.get_player(ctx)
        int_queue = player.queue._queue  # type: ignore
        queue_length = player.queue.qsize()

        if not (before != after and 1 <= before <= queue_length and 1 <= after <= queue_length):
            await ctx.send("Invalid queue position(s)")
            return

        temp = int_queue[before - 1]
        del int_queue[before - 1]
        int_queue.insert(after - 1, temp)

        await ctx.send(f"Moved track #{before} to #{after}")

    @queue.command()
    @commands.guild_only()
    @app_commands.describe(pos="Current position", diff="Relative difference")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.queue_has_element)
    async def move_relative(self, ctx: commands.Context, pos: Range[int, 1], diff: Range[int, 0]):
        """Move track to new position using relative difference"""
        await self.move(ctx, pos, pos + diff)

    @queue.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.queue_has_element)
    @app_commands.describe(
        pos1="First track position (1-indexed)",
        pos2="Second track position (1-indexed)",
    )
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def swap(self, ctx: commands.Context, pos1: Range[int, 1], pos2: Range[int, 1]):
        """Swap two tracks."""
        await ctx.defer()

        player: MainPlayer = self.get_player(ctx)

        q = player.queue._queue  # type: ignore
        q_length = len(q)

        if not (1 <= pos1 <= q_length and 1 <= pos2 <= q_length):
            await ctx.send(f"Invalid position(s): ({pos1}, {pos2})")
            return

        q[pos1 - 1], q[pos2 - 1] = q[pos2 - 1], q[pos1 - 1]
        await ctx.send(f"Swapped track #{pos1} and #{pos2}")

    @queue.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.queue_has_element)
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shuffle(self, ctx: commands.Context):
        """Shuffle the queue"""
        await ctx.defer()

        vc: VoiceClient = ctx.voice_client  # type: ignore

        random.shuffle(vc.queue._queue)  # type: ignore
        await ctx.send("Shuffled the queue")

    @queue.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.queue_has_element)
    async def clear(self, ctx: commands.Context):
        """Clear the queue"""
        await ctx.defer()

        player: MainPlayer = self.get_player(ctx)

        if await VoteMenu("clear", "queue", ctx).start():
            player.clear_queue()
            await ctx.send("Cleared the queue")

    @queue.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.queue_has_element)
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def force_clear(self, ctx: commands.Context):
        """Clear the queue"""
        await ctx.defer()
        player: MainPlayer = self.get_player(ctx)

        try:
            player.clear_queue()
            await ctx.send("Cleared the queue")
        except Exception as e:
            logging.error(
                "User %s try to forcely clear the queue in %s, but we encounter some trouble.",
                ctx.author.id,
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
