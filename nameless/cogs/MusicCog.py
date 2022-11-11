import asyncio
import collections
import datetime
import logging
import math
import random
from functools import partial
from typing import Any, AsyncIterable, Dict, List, Optional, Union

import discord
import DiscordUtils
from discord import ClientException, VoiceClient, app_commands

# from discord.app_commands import Choice
from discord.ext import commands
from discord.ext.commands import Range
from discord.utils import escape_markdown
from yt_dlp import YoutubeDL

from nameless import Nameless, shared_vars
from nameless.cogs.checks import MusicCogCheck
from nameless.commons import Utility


__all__ = ["MusicCog"]

ytdlopts = {
    "format": "bestaudio/93/best",
    "outtmpl": "downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "extract_flat": "in_playlist",
    "no_warnings": True,
    "default_search": "ytsearch5",
    "source_address": "0.0.0.0",
}

ffmpegopts = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", "options": "-vn"}

ytdl = YoutubeDL(ytdlopts)


class VoteMenuView(discord.ui.View):
    __slots__ = ("user", "value")

    def __init__(self):
        super().__init__(timeout=15)
        self.user = None
        self.value = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.user = interaction.user.mention

        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey, emoji="❌")
    async def disapprove(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.user = interaction.user.mention

        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        await interaction.response.defer()
        return True


class VoteMenu:
    __slots__ = (
        "action",
        "content",
        "ctx",
        "max_vote_user",
        "total_vote",
        "approve_member",
        "disapprove_member",
    )

    def __init__(
        self,
        action: str,
        content: str,
        ctx: commands.Context,
        voice_client: VoiceClient,
    ):
        self.ctx = ctx
        self.action = action
        self.content = f"{content[:50]}..."
        
        self.max_vote_user = math.ceil(len(voice_client.channel.members) / 2)
        self.total_vote = 1

        self.approve_member: List[str] = [ctx.author.mention]
        self.disapprove_member: List[str] = []

    async def start(self):
        if self.max_vote_user <= 1:
            return True

        message = await self.ctx.send(embed=self.__eb())

        while len(self.disapprove_member) < self.max_vote_user and len(self.approve_member) < self.max_vote_user:
            menu = VoteMenuView()
            await message.edit(embed=self.__eb(), view=menu)
            await menu.wait()

            if menu.user in self.approve_member or menu.user in self.disapprove_member:
                continue

            self.total_vote += 1

            if menu.value:
                self.approve_member.append(menu.user)  # pyright: ignore
            else:
                self.disapprove_member.append(menu.user)  # pyright: ignore

        pred = len(self.disapprove_member) < len(self.approve_member)
        if pred:
            await message.edit(content=f"{self.action.title()} {self.content}!", embed=None, view=None)
        else:
            await message.edit(content=f"Not enough votes to {self.action}!", embed=None, view=None)

        return pred

    def __eb(self):
        return (
            discord.Embed(
                title=f"Vote {self.action} {self.content}",
                description=f"Total vote: {self.total_vote}/{self.max_vote_user}",
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


class TrackPickDropdown(discord.ui.Select):

    __slots__ = ("options",)

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
            for index, track in enumerate(tracks[:25])
        ]

        super().__init__(
            custom_id="music-pick-select",
            placeholder="Choose your tracks",
            min_values=1,
            max_values=10,
            options=options,
        )

    async def callback(self, _: discord.Interaction) -> Any:
        v: Optional[discord.ui.View] = self.view
        if v:
            v.stop()


class YTDLSource(discord.PCMVolumeTransformer):

    __slots__ = ("requester", "title", "author", "lenght", "extractor", "direct", "webpage_url", "thumbnail")

    def __init__(self, data, requester, source=None):

        if source:
            self.source = source
            super().__init__(source)

        self.requester: discord.Member = requester
        self.title = data.get("title")
        self.author = data.get("uploader")
        self.lenght = data.get("duration", 0)
        self.direct = data.get("direct", False)
        self.thumbnail = data.get("thumbnail", None)
        self.extractor = data.get("extractor", "None")

        if "search" in self.extractor:
            self.webpage_url = data.get("url")
        else:
            self.webpage_url = data.get("webpage_url")

    @staticmethod
    async def _get_raw_data(search, loop=None) -> Dict:
        loop = loop or asyncio.get_event_loop()

        to_run = partial(ytdl.extract_info, url=search, download=False)
        data: Dict = await loop.run_in_executor(None, to_run)  # type: ignore

        return data

    @staticmethod
    def custom_ytdl_search(default_search):
        config = ytdlopts.copy()
        config["default_search"] = default_search
        return YoutubeDL(config)

    def is_stream(self):
        return self.direct

    @classmethod
    async def get_track(cls, ctx: commands.Context, search, loop=None):
        data = await cls._get_raw_data(search, loop)
        if tracks := data.get("entries", None):
            track: Dict = tracks[0]
            del data["entries"]
            data.update(track)
        return cls(data, ctx.author)

    @classmethod
    async def get_tracks(cls, ctx: commands.Context, search, range=5, loop=None) -> AsyncIterable:
        data = await cls._get_raw_data(search, loop)
        for track in data.get("entries", data)[:range]:
            track.update(
                {"extractor": data.get("extractor"), "direct": data.get("direct")},
            )
            yield cls(track, ctx.author)

    @classmethod
    async def generate_stream(cls, data, loop=None):
        loop = loop or asyncio.get_event_loop()
        requester = data.requester

        to_run = partial(ytdl.extract_info, url=data.webpage_url, download=False)
        ret: dict = await loop.run_in_executor(None, to_run)  # type: ignore

        return cls(source=discord.FFmpegPCMAudio(ret["url"], **ffmpegopts), data=ret, requester=requester)

    def cleanup(self) -> None:
        del self


class MainPlayer:

    __slots__ = (
        "client",
        "_guild",
        "_channel",
        "_cog",
        "queue",
        "next",
        "track",
        "volume",
        "duration",
        "position",
        "repeat",
        "task",
    )

    def __init__(self, ctx: commands.Context, cog) -> None:
        self.client = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.track: YTDLSource = None  # pyright: ignore
        self.volume = 0.5
        self.duration = 0
        self.position = 0
        self.repeat = False

        self.task = ctx.bot.loop.create_task(self.create())
        setattr(self._guild.voice_client, "is_queue_empty", self.queue.empty)

    @staticmethod
    def __build_np_embed(track: YTDLSource):
        return (
            discord.Embed(timestamp=datetime.datetime.now(), color=discord.Color.orange())
            .set_author(
                name="Now playing track",
                icon_url=track.requester.avatar.url,  # pyright: ignore
            )
            .add_field(
                name="Title",
                value=escape_markdown(track.title),
                inline=False,
            )
            .add_field(
                name="Author",
                value=escape_markdown(track.author) if track.author else "N/A",
            )
            .add_field(
                name="Source",
                value=escape_markdown(track.webpage_url) if track.webpage_url else "N/A",
            )
        )

    def clear_queue(self):
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                continue

    async def create(self):
        await self.client.wait_until_ready()

        while not self.client.is_closed():
            try:
                self.next.clear()
                if not self.repeat or self.track is None:
                    self.track = await self.queue.get()

                    await self._channel.send(embed=self.__build_np_embed(self.track))

                self.track = await YTDLSource.generate_stream(self.track)
                self.track.volume = self.volume

                self._guild.voice_client.play(  # type: ignore
                    self.track, after=lambda _: self.client.loop.call_soon_threadsafe(self.next.set)
                )

                self.duration -= self.track.lenght

            except AttributeError as e:
                print(self._guild.id, str(e))
                return self.destroy(self._guild)

            except Exception as e:
                return await self._channel.send(f"There was an error processing your song.\n" f"```css\n[{e}]\n```")

            finally:
                await self.next.wait()

                # Make sure the FFmpeg process is cleaned up.
                self.track.cleanup()
                if not self.repeat:
                    self.track = None  # type: ignore

    def destroy(self, guild):
        """Disconnect and cleanup the player."""
        return self.client.loop.create_task(self._cog.cleanup(guild))


class MusicCog(commands.Cog):
    def __init__(self, bot: Nameless):
        self.bot = bot
        self.players = {}

    async def cleanup(self, guild):
        await guild.voice_client.disconnect()

        try:
            player = self.players[guild.id]
            player.task.cancel()
        except asyncio.CancelledError:
            pass

        try:
            del self.players[guild.id]
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
        copycat: List = q._queue.copy()  # pyright: ignore
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
    async def show_paginated_tracks(ctx: commands.Context, embeds: List[discord.Embed]):
        p = DiscordUtils.Pagination.AutoEmbedPaginator(ctx)
        await p.run(embeds)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        try:
            player = self.players[member.guild.id]
        except KeyError:
            return

        # Technically auto disconnect the bot from lavalink
        # Sometimes on manual disconnection
        if member.id == self.bot.user.id:
            try:
                if len(player._guild.voice_client.channel.members) == 1:  # If bot is alone
                    if player._guild.voice_client.channel.members[0].id == self.bot.user.id:
                        logging.debug(
                            "Guild player %s still connected even if it is removed from voice, disconnecting",
                            player._guild.id,
                        )
                        await self.cleanup(player._guild)
            except AttributeError:  # Handle things like bot got kicked or move to another channel, etc.
                await self.cleanup(player._guild)

    # @commands.Cog.listener()
    # async def on_wavelink_track_start(self, player: wavelink.Player, track: wavelink.Track):
    #     chn = player.guild.get_channel(getattr(player, "trigger_channel_id"))

    #     if getattr(player, "play_now_allowed") and (
    #         (chn is not None and not getattr(player, "loop_sent")) or (getattr(player, "should_send_play_now"))
    #     ):
    #         setattr(player, "should_send_play_now", False)

    #         if track.is_stream():
    #             await chn.send(f"Streaming music from {track.uri}")  # pyright: ignore
    #         else:
    #             await chn.send(f"Playing: **{track.title}** from **{track.author}** ({track.uri})")  # pyright: ignore

    # @commands.Cog.listener()
    # async def on_wavelink_track_end(self, player: wavelink.Player, track: wavelink.Track, reason: str):
    #     if getattr(player, "stop_sent"):
    #         setattr(player, "stop_sent", False)
    #         return

    #     chn = player.guild.get_channel(getattr(player, "trigger_channel_id"))

    #     is_loop = getattr(player, "loop_sent")
    #     is_skip = getattr(player, "skip_sent")

    #     try:
    #         if is_loop and not is_skip:
    #             setattr(player, "loop_play_count", getattr(player, "loop_play_count") + 1)
    #         elif is_loop and is_skip:
    #             setattr(player, "loop_play_count", 0)
    #             setattr(player, "skip_sent", False)
    #             track = await player.queue.get_wait()  # pyright: ignore
    #         elif is_skip and not is_loop:
    #             track = await player.queue.get_wait()  # pyright: ignore
    #         elif not is_skip and not is_loop:
    #             track = await player.queue.get_wait()  # pyright: ignore

    #         await self.__internal_play2(player, track.uri)  # pyright: ignore
    #     except wavelink.QueueEmpty:
    #         if chn:
    #             await chn.send("The queue is empty now")  # pyright: ignore

    def get_player(self, ctx: commands.Context):
        """Retrieve the guild player, or generate one."""
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MainPlayer(ctx, self)
            self.players[ctx.guild.id] = player

        return player

    async def __internal_play(self, ctx: commands.Context, url: str, is_radio: bool = False):
        if is_radio:
            dbg, _ = shared_vars.crud_database.get_or_create_guild_record(ctx.guild)
            dbg.radio_start_time = discord.utils.utcnow()
            shared_vars.crud_database.save_changes()

        await self.__internal_play2(ctx, url, is_radio)

    async def __internal_play2(self, ctx: commands.Context, url: str, is_radio: bool = False):
        player = self.get_player(ctx)
        track = await YTDLSource.get_track(ctx, url)

        if track:
            if is_radio and not track.is_stream():
                raise commands.CommandError("Radio track must be a stream")
            player.queue.put(track)
        else:
            raise commands.CommandError(f"No tracks found for {url}")

    @commands.hybrid_group(fallback="radio")
    @app_commands.guilds(*getattr(shared_vars.config_cls, "GUILD_IDs", []))
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
            await ctx.author.voice.channel.connect(self_deaf=True)  # pyright: ignore
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
            await self.cleanup(ctx.guild)
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
        vc: VoiceClient = ctx.voice_client  # pyright: ignore

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

        vc: VoiceClient = ctx.voice_client  # pyright: ignore

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

        vc: VoiceClient = ctx.voice_client  # pyright: ignore

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

        vc: VoiceClient = ctx.voice_client  # pyright: ignore

        vc.stop()
        await ctx.send("Stopped")

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def skip(self, ctx: commands.Context):
        """Skip a song."""
        await ctx.defer()

        vc: VoiceClient = ctx.voice_client  # pyright: ignore
        player: MainPlayer = self.get_player(ctx)
        track: YTDLSource = player.track

        if await VoteMenu("skip", track.title, ctx, vc).start():
            vc.stop()
        else:
            await ctx.send("Not skipping because not enough votes!")

    # TODO: Implement seek (I still don't know how to do this, send help)

    # @music.command()
    # @commands.guild_only()
    # @app_commands.describe(pos="Position to seek to in milliseconds, defaults to run from start")
    # @commands.has_guild_permissions(manage_guild=True)
    # @app_commands.checks.has_permissions(manage_guild=True)
    # @commands.check(MusicCogCheck.user_and_bot_in_voice)
    # @commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    # async def seek(self, ctx: commands.Context, pos: Range[int, 0] = 0):
    #     """Seek to a position in a track"""
    #     await ctx.defer()

    #     vc: VoiceClient = ctx.voice_client  # pyright: ignore
    #     track: wavelink.Track = vc.track  # pyright: ignore

    #     pos = pos if pos else 0

    #     if not 0 <= pos / 1000 <= track.length:
    #         await ctx.send("Invalid position to seek")
    #         return

    #     if await VoteMenu("seek", track.title, ctx, vc).start():
    #         await vc.seek(pos)
    #         delta_pos = datetime.timedelta(milliseconds=pos)
    #         await ctx.send(f"Seek to position {delta_pos}")

    # @music.command()
    # @commands.guild_only()
    # @app_commands.describe(segment="Segment to seek (from 0 to 10, respecting to 0%, 10%, ..., 100%)")
    # @commands.has_guild_permissions(manage_guild=True)
    # @app_commands.checks.has_permissions(manage_guild=True)
    # @commands.check(MusicCogCheck.user_and_bot_in_voice)
    # @commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    # async def seek_segment(self, ctx: commands.Context, segment: Range[int, 0, 10] = 0):
    #     """Seek to a segment in a track"""
    #     await ctx.defer()

    #     vc: VoiceClient = ctx.voice_client  # pyright: ignore
    #     track: wavelink.Track = vc.track  # pyright: ignore

    #     if not 0 <= segment <= 10:
    #         await ctx.send("Invalid segment")
    #         return

    #     if await VoteMenu("seek_segment", track.title, ctx, vc).start():
    #         pos = int(float(track.length * (segment * 10) / 100) * 1000)
    #         await vc.seek(pos)
    #         delta_pos = datetime.timedelta(milliseconds=pos)
    #         await ctx.send(f"Seek to segment #{segment}: {delta_pos}")

    # I don't know if I'm going to remove this function or reimplement it.
    # @music.command()
    # @commands.guild_only()
    # @commands.has_guild_permissions(manage_guild=True)
    # @app_commands.checks.has_permissions(manage_guild=True)
    # @commands.check(MusicCogCheck.user_and_bot_in_voice)
    # @commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    # async def toggle_play_now(self, ctx: commands.Context):
    #     """Toggle 'Now playing' message delivery"""
    #     await ctx.defer()

    #     vc: VoiceClient = ctx.voice_client  # pyright: ignore
    #     setattr(vc, "play_now_allowed", not getattr(vc, "play_now_allowed"))

    #     await ctx.send(f"'Now playing' delivery is now {'on' if getattr(vc, 'play_now_allowed') else 'off'}")

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_something)
    async def now_playing(self, ctx: commands.Context):
        """Check now playing song"""
        await ctx.defer()

        vc: VoiceClient = ctx.voice_client  # pyright: ignore
        player: MainPlayer = self.get_player(ctx)
        track: YTDLSource = player.track

        is_stream = track.is_stream()
        dbg, _ = shared_vars.crud_database.get_or_create_guild_record(ctx.guild)

        try:
            next_tr = player.queue._queue.copy().pop()  # type: ignore
        except IndexError:
            next_tr = None

        await ctx.send(
            embeds=[
                discord.Embed(timestamp=datetime.datetime.now(), color=discord.Color.orange())
                .set_author(
                    name="Now playing track",
                    icon_url=ctx.author.avatar.url,  # pyright: ignore
                )
                .add_field(
                    name="Title",
                    value=escape_markdown(track.title),
                    inline=False,
                )
                .add_field(
                    name="Author",
                    value=escape_markdown(track.author) if track.author else "N/A",
                )
                .add_field(
                    name="Source",
                    value=escape_markdown(track.webpage_url) if track.webpage_url else "N/A",
                )
                .add_field(
                    name="Playtime" if is_stream else "Position",
                    value=str(
                        datetime.datetime.now() - dbg.radio_start_time
                        if is_stream
                        else f"{datetime.timedelta(seconds=player.position)}/{datetime.timedelta(seconds=track.lenght)}"
                    ),
                )
                .add_field(
                    name="Looping",
                    value="This is a stream"
                    if is_stream
                    else f"Looped {getattr(vc, 'loop_play_count')} time(s)"
                    if getattr(vc, "loop_sent") is True
                    else False,
                )
                .add_field(name="Paused", value=vc.is_paused())
                .add_field(
                    name="Next track",
                    value=f"[{escape_markdown(next_tr.title) if next_tr.title else 'Unknown title'} "
                    f"by {escape_markdown(next_tr.author)}]"
                    f"({next_tr.uri})"
                    if next_tr
                    else None,
                )
            ]
        )

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
        queue: List = player.queue._queue  # pyright: ignore

        if idx > player.queue.qsize() or idx < 0:
            return await ctx.send("The track number you just entered is not available. Check again")

        deleted_track: YTDLSource = queue.pop(idx)
        await ctx.send(f"Deleted track at position #{idx}: **{deleted_track.title}** from **{deleted_track.author}**")

    @queue.command()
    @commands.guild_only()
    @app_commands.describe(search="Search query", source="Source to search")
    # @app_commands.choices(source=[Choice(name=k, value=k) for k in music_default_sources])
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def add(self, ctx: commands.Context, search: str, source: str = "youtube"):
        """Add selected track(s) to queue"""
        await ctx.defer()

        player: MainPlayer = self.get_player(ctx)

        track = await YTDLSource.get_track(ctx, search)
        if track.is_stream():
            await ctx.send("This is a stream, cannot add to queue")
            return

        if "search" in track.extractor:
            await player.queue.put(track)
            await ctx.send(content=f"Added `{track.title}` into the queue")
            return

        tracks: List[YTDLSource] = list(t for t in await YTDLSource.get_tracks(ctx, search, range=5))

        if not tracks:
            await ctx.send(f"No tracks found for '{search}' on '{source}'.")
            return

        view = discord.ui.View().add_item(TrackPickDropdown([track for track in tracks if not track.is_stream()]))

        m = await ctx.send("Tracks found", view=view)

        if await view.wait():
            await m.edit(content="Timed out!", view=None, delete_after=30)
            return

        drop: Union[discord.ui.Item[discord.ui.View], TrackPickDropdown] = view.children[0]
        vals = drop.values  # pyright: ignore

        if not vals:
            await m.delete()
            return

        if "Nope" in vals:
            await m.edit(content="All choices cleared", view=None)
            return

        soon_to_add_queue: List[YTDLSource] = []

        for val in vals:
            idx = int(val)
            await player.queue.put(tracks[idx])

        await m.edit(content=f"Added {len(vals)} tracks into the queue", view=None)

        embeds = self.generate_embeds_from_tracks(soon_to_add_queue)
        self.bot.loop.create_task(self.show_paginated_tracks(ctx, embeds))

    # No playlist for now
    # TODO: Add playlist

    # @queue.command()
    # @commands.guild_only()
    # @commands.check(MusicCogCheck.user_and_bot_in_voice)
    # @app_commands.describe(url="Playlist URL", source="Source to get playlist")
    # @app_commands.choices(source=[Choice(name=k, value=k) for k in music_default_sources])
    # async def add_playlist(self, ctx: commands.Context, url: str, source: str = "youtube"):
    #     """Add track(s) from playlist to queue"""
    #     await ctx.defer()

    #     tracks: Optional[
    #         Union[
    #             List[wavelink.YouTubeTrack],
    #             List[wavelink.YouTubeMusicTrack],
    #             List[spotify.SpotifyTrack],
    #             List[wavelink.SoundCloudTrack],
    #             List[Type[wavelink.tracks.Playable]],
    #             List[Type[wavelink.SearchableTrack]],
    #         ]
    #     ] = []

    #     if source == "youtube":
    #         try:
    #             pl = (await wavelink.YouTubePlaylist.search(url)).tracks  # pyright: ignore
    #         except wavelink.LoadTrackError:
    #             pl = await wavelink.YouTubeTrack.search(url)
    #         tracks = pl
    #     elif source == "ytmusic":
    #         tracks = await wavelink.YouTubeMusicTrack.search(url)
    #     elif source == "spotify":
    #         tracks = await spotify.SpotifyTrack.search(url, type=spotify.SpotifySearchType.playlist)
    #     elif source == "soundcloud":
    #         tracks = await wavelink.SoundCloudTrack.search(query=url)

    #     if not tracks:
    #         await ctx.send(f"No tracks found for {url} on {source}, have you checked your URL?")
    #         return

    #     player: wavelink.Player = ctx.voice_client  # pyright: ignore
    #     accepted_tracks = [track for track in tracks if not track.is_stream()]  # pyright: ignore
    #     player.queue.extend(accepted_tracks)  # pyright: ignore
    #     await ctx.send(f"Added {len(tracks)} track(s) from {url} to the queue")

    #     embeds = self.generate_embeds_from_tracks(accepted_tracks)  # pyright: ignore
    #     self.bot.loop.create_task(self.show_paginated_tracks(ctx, embeds))

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
        int_queue = player.queue._queue  # pyright: ignore
        queue_length = len(int_queue)

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

        q = player.queue._queue  # pyright: ignore
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

        vc: VoiceClient = ctx.voice_client  # pyright: ignore

        random.shuffle(vc.queue._queue)  # pyright: ignore
        await ctx.send("Shuffled the queue")

    @queue.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.queue_has_element)
    async def clear(self, ctx: commands.Context):
        """Clear the queue"""
        await ctx.defer()

        vc: VoiceClient = ctx.voice_client  # pyright: ignore
        player: MainPlayer = self.get_player(ctx)

        if await VoteMenu("clear", "queue", ctx, vc).start():
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
            logging.debug("MusicCog.force_clear raise an error: [%s] %s", e.__class__.__name__, str(e))


async def setup(bot: Nameless):
    await bot.add_cog(MusicCog(bot))
    logging.info("Cog of %s added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog("MusicCog")
    logging.warning("Cog of %s removed!", __name__)
