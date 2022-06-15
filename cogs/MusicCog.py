import collections
import datetime
import logging
import math
import random
from typing import List, Any, Union, Optional, Dict, Type
from urllib import parse

import DiscordUtils
import discord
import wavelink
from discord import ClientException, app_commands
from discord.app_commands import Choice
from discord.ext import commands
from discord.utils import escape_markdown
from wavelink.ext import spotify
from customs.Utility import Utility

import global_deps
from config import Config
from cogs.checks import MusicCogChecks

__all__ = ["MusicCog"]

music_default_sources: List[str] = ["youtube", "soundcloud", "ytmusic"]


class VoteMenuView(discord.ui.View):
    __slots__ = ("user", "value")

    def __init__(self):
        super().__init__(timeout=15)
        self.user = None
        self.value = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.value = True
        self.user = interaction.user.mention

        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey, emoji="❌")
    async def disapprove(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
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
        voice_client: wavelink.Player,
    ):
        self.action = action
        self.content = f"{content[:50]}..."
        self.ctx = ctx
        self.max_vote_user = math.ceil(len(voice_client.channel.members) / 2)
        self.total_vote = 1

        self.approve_member: List[str] = [ctx.author.mention]
        self.disapprove_member: List[str] = []

    async def start(self):
        if self.max_vote_user <= 1:
            return True

        message = await self.ctx.send(embed=self.__eb())

        while (
            len(self.disapprove_member) < self.max_vote_user
            and len(self.approve_member) < self.max_vote_user
        ):
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
            await message.edit(
                content=f"{self.action.title()} {self.content}!", embed=None, view=None
            )
        else:
            await message.edit(
                content=f"Not enough votes to {self.action}!", embed=None, view=None
            )

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
                value="\n".join(self.disapprove_member)
                if self.disapprove_member
                else "None",
                inline=True,
            )
            .set_footer(text=f"Requested by {self.ctx.author.name}")
        )


class TrackPickDropdown(discord.ui.Select):
    def __init__(self, tracks: List[wavelink.SearchableTrack]):
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


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot
        self.can_use_spotify = bool(
            Config.LAVALINK.get("spotify")
            and Config.LAVALINK["spotify"]
            and Config.LAVALINK["spotify"]["client_id"]
            and Config.LAVALINK["spotify"]["client_secret"]
        )

        if not self.can_use_spotify:
            logging.warning(
                "Spotify command option will be removed since you did not provide enough credentials."
            )
        else:
            # I know, bad design
            global music_default_sources
            music_default_sources += ["spotify"]

        bot.loop.create_task(self.connect_nodes())

    @staticmethod
    def generate_embeds_from_tracks(
        tracks: List[wavelink.SearchableTrack],
    ) -> List[discord.Embed]:
        embeds: List[discord.Embed] = []
        txt = ""

        for idx, track in enumerate(tracks):
            upcoming = (
                f"{idx} - "
                f"[{escape_markdown(track.title)} by {escape_markdown(track.author)}]"  # pyright: ignore
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
    def generate_embeds_from_queue(q: wavelink.Queue) -> List[discord.Embed]:
        # Just in case the user passes the original queue
        copycat = q.copy()
        idx = 0
        txt = ""
        embeds: List[discord.Embed] = []

        try:
            while track := copycat.get():
                upcoming = (
                    f"{idx} - "
                    f"[{escape_markdown(track.title)} by {escape_markdown(track.author)}]"  # pyright: ignore
                    f"({track.uri})\n"  # pyright: ignore
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
        except wavelink.QueueEmpty:
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

    @staticmethod
    def resolve_direct_url(search: str) -> Optional[Type[wavelink.SearchableTrack]]:
        locations: Dict[str, Type[wavelink.SearchableTrack]] = {
            "soundcloud.com": wavelink.SoundCloudTrack,
            "open.spotify.com": spotify.SpotifyTrack,
            "music.youtube.com": wavelink.YouTubeMusicTrack,
            "youtube.com": wavelink.YouTubeTrack,
            "youtu.be": wavelink.YouTubeTrack,
        }

        if domain := parse.urlparse(search).netloc:
            return locations.get(domain, wavelink.SearchableTrack)

        return None

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        for node in Config.LAVALINK["nodes"]:
            await wavelink.NodePool.create_node(
                bot=self.bot,
                host=node["host"],
                port=node["port"],
                password=node["password"],
                https=node["is_secure"],
                spotify_client=spotify.SpotifyClient(
                    client_id=Config.LAVALINK["spotify"]["client_id"],
                    client_secret=Config.LAVALINK["spotify"]["client_secret"],
                )
                if self.can_use_spotify
                else None,
            )

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        logging.info("Node {%s} (%s) is ready!", node.identifier, node.host)

    @commands.Cog.listener()
    async def on_wavelink_track_start(
        self, player: wavelink.Player, track: wavelink.Track
    ):
        chn = player.guild.get_channel(getattr(player, "trigger_channel_id"))

        if (
            chn
            and not getattr(player, "loop_sent")
            and getattr(player, "play_now_allowed")
        ):
            await chn.send(  # type: ignore
                f"Playing: **{track.title}** from **{track.author}** ({track.uri})"
            )

    @commands.Cog.listener()
    async def on_wavelink_track_end(
        self, player: wavelink.Player, track: wavelink.Track, reason: str
    ):
        if getattr(player, "stop_sent"):
            return

        chn = player.guild.get_channel(getattr(player, "trigger_channel_id"))

        try:
            if getattr(player, "loop_sent") and not getattr(player, "skip_sent"):
                setattr(
                    player, "loop_play_count", getattr(player, "loop_play_count") + 1
                )
            else:
                setattr(player, "loop_play_count", 0)
                setattr(player, "loop_sent", False)
                setattr(player, "skip_sent", False)
                track = await player.queue.get_wait()  # pyright: ignore

            await self.__internal_play2(player, track.uri)  # pyright: ignore
        except wavelink.QueueEmpty:
            if chn:
                await chn.send("The queue is empty now")  # pyright: ignore

    async def __internal_play(
        self, ctx: commands.Context, url: str, is_radio: bool = False
    ):
        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        setattr(vc, "skip_sent", False)
        setattr(vc, "stop_sent", False)
        setattr(vc, "loop_sent", False)
        setattr(vc, "play_now_allowed", True)
        setattr(vc, "trigger_channel_id", ctx.channel.id)
        setattr(vc, "loop_play_count", 0)

        if is_radio:
            dbg, _ = global_deps.crud_database.get_or_create_guild_record(ctx.guild)
            dbg.radio_start_time = discord.utils.utcnow()
            global_deps.crud_database.save_changes()

        await self.__internal_play2(vc, url, is_radio)

    async def __internal_play2(
        self, vc: wavelink.Player, url: str, is_radio: bool = False
    ):
        tracks = await vc.node.get_tracks(wavelink.SearchableTrack, url)

        if tracks:
            track = tracks[0]
            if is_radio and not track.is_stream():
                raise commands.CommandError("Radio track must be a stream")
            await vc.play(track)
        else:
            raise commands.CommandError(f"No tracks found for {url}")

    @commands.hybrid_group(fallback="radio")
    @commands.guild_only()
    @app_commands.describe(url="Radio url")
    @app_commands.guilds(*Config.GUILD_IDs)
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.bot_must_silent()
    async def music(self, ctx: commands.Context, url: str):
        """Play a radio"""
        await ctx.defer()

        if not Utility.is_an_url(url):
            await ctx.send("You need to provide a direct URL")
            return

        await self.__internal_play(ctx, url, True)

    @music.command()
    @commands.guild_only()
    @MusicCogChecks.user_in_voice()
    async def connect(self, ctx: commands.Context):
        """Connect to your current voice channel"""
        await ctx.defer()

        try:
            await ctx.author.voice.channel.connect(  # pyright: ignore
                cls=wavelink.Player, self_deaf=True
            )
            await ctx.send("Connected to your current voice channel")
        except ClientException:
            await ctx.send("Already connected")

    @music.command()
    @commands.guild_only()
    @MusicCogChecks.bot_in_voice()
    async def disconnect(self, ctx: commands.Context):
        """Disconnect from my current voice channel"""
        await ctx.defer()

        try:
            await ctx.voice_client.disconnect(force=True)  # pyright: ignore
            await ctx.send("Disconnected from my own voice channel")
        except AttributeError:
            await ctx.send("Already disconnected")

    @music.command()
    @commands.guild_only()
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.bot_must_play_something()
    @MusicCogChecks.must_not_be_a_stream()
    async def loop(self, ctx: commands.Context):
        """Toggle loop playback of current track"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        setattr(vc, "loop_sent", not getattr(vc, "loop_sent"))
        await ctx.send(f"Loop set to {'on' if getattr(vc, 'loop_sent') else 'off'}")

    @music.command()
    @commands.guild_only()
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.bot_must_play_something()
    async def pause(self, ctx: commands.Context):
        """Pause current playback"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        if vc.is_paused():
            await ctx.send("Already paused")
            return

        await vc.pause()
        await ctx.send("Paused")

    @music.command()
    @commands.guild_only()
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.bot_must_silent()
    async def resume(self, ctx: commands.Context):
        """Resume current playback, if paused"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        if not vc.is_paused():
            await ctx.send("Already resuming")
            return

        await vc.resume()
        await ctx.send("Resuming")

    @music.command()
    @commands.guild_only()
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.bot_must_play_something()
    async def stop(self, ctx: commands.Context):
        """Stop current playback."""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        setattr(vc, "stop_sent", True)

        await vc.stop()
        await ctx.send("Stopping")

    @music.command()
    @commands.guild_only()
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.bot_must_silent()
    @MusicCogChecks.queue_has_element()
    async def play_queue(self, ctx: commands.Context):
        """Play entire queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        if vc.queue.is_empty:
            await ctx.send("Queue is empty")
            return

        track = vc.queue.get()
        await self.__internal_play(ctx, track.uri)  # pyright: ignore

    @music.command()
    @commands.guild_only()
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.bot_must_play_something()
    @MusicCogChecks.queue_has_element()
    @MusicCogChecks.must_not_be_a_stream()
    async def skip(self, ctx: commands.Context):
        """Skip a song. Remind you that the loop effect DOES NOT apply"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        track: wavelink.Track = vc.track  # pyright: ignore

        if await VoteMenu("skip", track.title, ctx, vc).start():
            setattr(vc, "skip_sent", True)
            await vc.stop()

    @music.command()
    @commands.guild_only()
    @app_commands.describe(
        pos="Position to seek to in milliseconds, defaults to run from start"
    )
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.bot_must_play_something()
    @MusicCogChecks.must_not_be_a_stream()
    async def seek(self, ctx: commands.Context, pos: int = 0):
        """Seek to a position in a track"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        track: wavelink.Track = vc.track  # pyright: ignore

        pos = pos if pos else 0

        if not 0 <= pos / 1000 <= track.length:
            await ctx.send("Invalid position to seek")
            return

        if await VoteMenu("seek", track.title, ctx, vc).start():
            await vc.seek(pos)
            delta_pos = datetime.timedelta(milliseconds=pos)
            await ctx.send(f"Seek to position {delta_pos}")

    @music.command()
    @commands.guild_only()
    @app_commands.describe(
        segment="Segment to seek (from 0 to 10, respecting to 0%, 10%, ..., 100%)"
    )
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.bot_must_play_something()
    @MusicCogChecks.must_not_be_a_stream()
    async def seek_segment(self, ctx: commands.Context, segment: int = 0):
        """Seek to a segment in a track"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        track: wavelink.Track = vc.track  # pyright: ignore

        if not 0 <= segment <= 10:
            await ctx.send("Invalid segment")
            return

        if await VoteMenu("seek_segment", track.title, ctx, vc).start():
            pos = int(float(track.length * (segment * 10) / 100) * 1000)
            await vc.seek(pos)
            delta_pos = datetime.timedelta(milliseconds=pos)
            await ctx.send(f"Seek to segment #{segment}: {delta_pos}")

    @music.command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.bot_must_play_something()
    @MusicCogChecks.must_not_be_a_stream()
    async def toggle_play_now(self, ctx: commands.Context):
        """Toggle 'Now playing' message delivery"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        setattr(vc, "play_now_allowed", not getattr(vc, "play_now_allowed"))

        await ctx.send(
            f"'Now playing' delivery is now {'on' if getattr(vc, 'play_now_allowed') else 'off'}"
        )

    @music.command()
    @commands.guild_only()
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.bot_must_play_something()
    async def now_playing(self, ctx: commands.Context):
        """Check now playing song"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        track: wavelink.Track = vc.track  # pyright: ignore

        is_stream = track.is_stream()
        dbg, _ = global_deps.crud_database.get_or_create_guild_record(ctx.guild)

        try:
            next_tr = vc.queue.copy().get()
        except wavelink.QueueEmpty:
            next_tr = None

        await ctx.send(
            embeds=[
                discord.Embed(
                    timestamp=datetime.datetime.now(), color=discord.Color.orange()
                )
                .set_author(
                    name="Now playing track",
                    icon_url=ctx.author.avatar.url,  # pyright: ignore
                )
                .add_field(
                    name="Title",
                    value=escape_markdown(track.title),
                    inline=False,
                )
                .add_field(name="Author", value=escape_markdown(track.author))
                .add_field(name="Source", value=escape_markdown(track.uri))
                .add_field(
                    name="Playtime" if is_stream else "Position",
                    value=str(
                        datetime.datetime.now() - dbg.radio_start_time
                        if is_stream
                        else f"{datetime.timedelta(seconds=vc.position)}/{datetime.timedelta(seconds=track.length)}"
                    ),
                )
                .add_field(
                    name="Looping",
                    value="This is a stream"
                    if is_stream
                    else f"{vc.loop_sent}, looped ||{getattr(vc, 'loop_play_count')}|| time(s)",  # pyright: ignore
                )
                .add_field(name="Paused", value=vc.is_paused())
                .add_field(
                    name="Next track",
                    value=f"[{escape_markdown(next_tr.title)} by {escape_markdown(next_tr.author)}]({next_tr.uri})"
                    if next_tr
                    else None,
                )
            ]
        )

    @music.group(fallback="view")
    @commands.guild_only()
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.queue_has_element()
    async def queue(self, ctx: commands.Context):
        """View current queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        embeds = self.generate_embeds_from_queue(vc.queue)
        await self.show_paginated_tracks(ctx, embeds)

    @queue.command()
    @commands.guild_only()
    @app_commands.describe(
        indexes="The indexes to remove (1-based), separated by comma"
    )
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.queue_has_element()
    async def delete(self, ctx: commands.Context, indexes: str):
        """Remove tracks from queue atomically"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        positions = indexes.replace(" ", "").split(",")
        result = ""
        success_cnt = 0
        q = vc.queue._queue

        for position in positions:
            try:
                pos = int(position)
                if pos < 0:
                    result += f"Invalid position: {pos}\n"
                    continue

                if not q[pos]:
                    result += f"Already marked track #{pos} as deleted\n"
                    continue

                result += f"Marked track #{pos} as deleted\n"
                success_cnt += 1
                q[pos - 1] = None
            except ValueError:
                result += f"Invalid value: {position}\n"

        vc.queue._queue = collections.deque([t for t in q if t])
        await ctx.send(f"{result}\n{success_cnt} tracks deleted")

    @queue.command()
    @commands.guild_only()
    @app_commands.describe(search="Search query", source="Source to search")
    @app_commands.choices(
        source=[Choice(name=k, value=k) for k in music_default_sources]
    )
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    async def add(self, ctx: commands.Context, search: str, source: str = "youtube"):
        """Add selected track(s) to queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        if search_cls := self.resolve_direct_url(search):
            track = (await vc.node.get_tracks(search_cls, search))[0]

            if track.is_stream():
                await ctx.send("This is a stream, cannot add to queue")
                return

            vc.queue.put(track)  # pyright: ignore
            await ctx.send(content=f"Added `{track.title}` into the queue")
            return

        sources: Dict[str, Any] = {
            "youtube": wavelink.YouTubeTrack,
            "ytmusic": wavelink.YouTubeMusicTrack,
            "spotify": spotify.SpotifyTrack,
            "soundcloud": wavelink.SoundCloudTrack,
        }

        search_cls = sources[source]
        tracks = await search_cls.search(search)

        if not tracks:
            await ctx.send(f"No tracks found for '{search}' on '{source}'.")
            return

        view = discord.ui.View().add_item(
            TrackPickDropdown([track for track in tracks if not track.is_stream()])
        )

        m = await ctx.send("Tracks found", view=view)

        if await view.wait():
            await m.edit(content="Timed out!", view=None, delete_after=30)
            return

        drop: Union[
            discord.ui.Item[discord.ui.View], TrackPickDropdown
        ] = view.children[0]
        vals = drop.values  # pyright: ignore

        if not vals:
            await m.delete()
            return

        if "Nope" in vals:
            await m.edit(content="All choices cleared", view=None)
            return

        soon_to_add_queue: List[wavelink.SearchableTrack] = []

        for val in vals:
            idx = int(val)
            soon_to_add_queue.append(tracks[idx])

        vc.queue.extend(soon_to_add_queue)
        await m.edit(content=f"Added {len(vals)} tracks into the queue", view=None)

        embeds = self.generate_embeds_from_tracks(soon_to_add_queue)
        await self.show_paginated_tracks(ctx, embeds)

    @queue.command()
    @commands.guild_only()
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @app_commands.describe(url="Playlist URL", source="Source to get playlist")
    @app_commands.choices(
        source=[Choice(name=k, value=k) for k in music_default_sources]
    )
    async def add_playlist(
        self, ctx: commands.Context, url: str, source: str = "youtube"
    ):
        """Add track(s) from playlist to queue"""
        await ctx.defer()

        tracks: List[wavelink.SearchableTrack] = []

        if source == "youtube":
            try:
                pl = (await wavelink.YouTubePlaylist.search(query=url)).tracks
            except wavelink.LoadTrackError:
                pl = await wavelink.YouTubeTrack.search(query=url)
            tracks = pl
        elif source == "ytmusic":
            tracks = await wavelink.YouTubeMusicTrack.search(query=url)
        elif source == "spotify":
            tracks = await spotify.SpotifyTrack.search(
                query=url, type=spotify.SpotifySearchType.playlist
            )
        elif source == "soundcloud":
            tracks = await wavelink.SoundCloudTrack.search(query=url)

        if not tracks:
            await ctx.send(
                f"No tracks found for {url} on {source}, have you checked your URL?"
            )
            return

        player: wavelink.Player = ctx.voice_client  # pyright: ignore
        accepted_tracks = [track for track in tracks if not track.is_stream()]
        player.queue.extend(accepted_tracks)
        await ctx.send(f"Added {len(tracks)} track(s) from {url} to the queue")

        embeds = self.generate_embeds_from_tracks(accepted_tracks)
        await self.show_paginated_tracks(ctx, embeds)

    @queue.command()
    @commands.guild_only()
    @app_commands.describe(before="Old position", after="New position")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.queue_has_element()
    async def move(self, ctx: commands.Context, before: int, after: int):
        """Move track to new position"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        int_queue = vc.queue._queue
        queue_length = len(int_queue)

        if not (
            before != after
            and 1 <= before <= queue_length
            and 1 <= after <= queue_length
        ):
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
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.queue_has_element()
    async def move_relative(self, ctx: commands.Context, pos: int, diff: int):
        """Move track to new position using relative difference"""
        await self.move(ctx, pos, pos + diff)

    @queue.command()
    @commands.guild_only()
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.queue_has_element()
    @app_commands.describe(
        pos1='First track positions, separated by comma, covered by pair of "',
        pos2='Second track positions, separated by comma, covered by pair of "',
    )
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def swap(self, ctx: commands.Context, pos1: str, pos2: str):
        """Swap two or more tracks. "swap "1,2,3" "4,5,6" will swap 1 with 4, 2 with 5, 4 with 6"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        int_q = vc.queue._queue
        q_length = len(int_q)

        a1 = pos1.replace(" ", "").split(",")
        a2 = pos2.replace(" ", "").split(",")

        if len(a1) != len(a2):
            await ctx.send("Position counts are not equal")
            return

        resp = ""

        for before, after in zip(a1, a2):
            try:
                before = int(before)
                after = int(after)

                if not (1 <= before <= q_length and 1 <= after <= q_length):
                    resp += f"Invalid position(s): ({before}, {after})\n"
                    continue

                int_q[before - 1], int_q[after - 1] = (
                    int_q[after - 1],
                    int_q[before - 1],
                )
                resp += f"Swapped #{before} and #{after}\n"
            except ValueError:
                resp += f"Invalid pair: ({before}, {after})\n"

        await ctx.send(resp[:996])

    @queue.command()
    @commands.guild_only()
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.queue_has_element()
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shuffle(self, ctx: commands.Context):
        """Shuffle the queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        random.shuffle(vc.queue._queue)
        await ctx.send("Shuffled the queue")

    @queue.command()
    @commands.guild_only()
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.queue_has_element()
    async def clear(self, ctx: commands.Context):
        """Clear the queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        if await VoteMenu("clear", "queue", ctx, vc).start():
            vc.queue.clear()
            await ctx.send("Cleared the queue")

    @queue.command()
    @commands.guild_only()
    @MusicCogChecks.bot_in_voice()
    @MusicCogChecks.user_in_voice()
    @MusicCogChecks.queue_has_element()
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def force_clear(self, ctx: commands.Context):
        """Clear the queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        vc.queue.clear()
        await ctx.send("Cleared the queue")

    @add.after_invoke
    @add_playlist.after_invoke
    async def add_track_after_invoke(self, ctx: commands.Context):
        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        if not vc.track and not vc.queue.is_empty:
            track = vc.queue.get()
            await self.__internal_play(ctx, track.uri)  # pyright: ignore


async def setup(bot: commands.AutoShardedBot):
    if hasattr(Config, "LAVALINK") and Config.LAVALINK and Config.LAVALINK["nodes"]:
        await bot.add_cog(MusicCog(bot))
        logging.info("Cog of %s added!", __name__)
    else:
        raise commands.ExtensionFailed(
            __name__, ValueError("Lavalink options are not properly provided")
        )


async def teardown(bot: commands.AutoShardedBot):
    await bot.remove_cog("MusicCog")
    logging.warning("Cog of %s removed!", __name__)
