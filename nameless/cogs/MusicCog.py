import collections
import datetime
import logging
import math
import random
from typing import Any, Dict, List, Optional, Type, Union
from urllib import parse

import discord
import DiscordUtils
import wavelink
from discord import ClientException, app_commands
from discord.app_commands import Choice
from discord.ext import commands
from discord.ext.commands import Range
from discord.utils import escape_markdown
from NamelessConfig import NamelessConfig
from wavelink.ext import spotify

from nameless import Nameless, shared_vars
from nameless.cogs.checks import MusicCogCheck
from nameless.commons import Utility


__all__ = ["MusicCog"]

music_default_sources: List[str] = ["youtube", "soundcloud", "ytmusic"]


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
    def __init__(self, bot: Nameless):
        self.bot = bot
        self.can_use_spotify = bool(
            (sp := NamelessConfig.LAVALINK.get("spotify")) and sp.get("client_id") and sp.get("client_secret")
        )

        if not self.can_use_spotify:
            logging.warning("Spotify command option will be removed since you did not provide enough credentials.")
        else:
            # I know, bad design
            global music_default_sources  # pylint: disable=global-statement
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
                f"{idx + 1} - "
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
                    f"{idx + 1} - "
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
        for node in NamelessConfig.LAVALINK["nodes"]:
            await wavelink.NodePool.create_node(
                bot=self.bot,
                host=node["host"],
                port=node["port"],
                password=node["password"],
                https=node["is_secure"],
                spotify_client=spotify.SpotifyClient(
                    client_id=NamelessConfig.LAVALINK["spotify"]["client_id"],
                    client_secret=NamelessConfig.LAVALINK["spotify"]["client_secret"],
                )
                if self.can_use_spotify
                else None,
            )

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        logging.info("Node {%s} (%s) is ready!", node.identifier, node.host)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        # Technically auto disconnect the bot from lavalink
        # Sometimes on manual disconnection
        if member.id == self.bot.user.id:
            before_was_in_voice = before.channel is not None
            after_not_in_noice = after.channel is None

            if before_was_in_voice and after_not_in_noice:
                node_dict = wavelink.NodePool._nodes.items()
                guilds_players = [p for (_, node) in node_dict if (p := node.get_player(member.guild))]
                if guilds_players:
                    bot_player = [player for player in guilds_players if player.client.user.id == self.bot.user.id]
                    if bot_player:
                        logging.debug(
                            "Guild player %s still connected even if it is removed from voice, disconnecting",
                            bot_player[0].guild.id,
                        )
                        await bot_player[0].disconnect()

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, player: wavelink.Player, track: wavelink.Track):
        chn = player.guild.get_channel(getattr(player, "trigger_channel_id"))

        if getattr(player, "play_now_allowed") and (
            (chn is not None and not getattr(player, "loop_sent")) or (getattr(player, "should_send_play_now"))
        ):
            setattr(player, "should_send_play_now", False)

            if track.is_stream():
                await chn.send(f"Streaming music from {track.uri}")  # pyright: ignore
            else:
                await chn.send(f"Playing: **{track.title}** from **{track.author}** ({track.uri})")  # pyright: ignore

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: wavelink.Player, track: wavelink.Track, reason: str):
        if getattr(player, "stop_sent"):
            setattr(player, "stop_sent", False)
            return

        chn = player.guild.get_channel(getattr(player, "trigger_channel_id"))

        is_loop = getattr(player, "loop_sent")
        is_skip = getattr(player, "skip_sent")

        try:
            if is_loop and not is_skip:
                setattr(player, "loop_play_count", getattr(player, "loop_play_count") + 1)
            elif is_loop and is_skip:
                setattr(player, "loop_play_count", 0)
                setattr(player, "skip_sent", False)
                track = await player.queue.get_wait()  # pyright: ignore
            elif is_skip and not is_loop:
                track = await player.queue.get_wait()  # pyright: ignore
            elif not is_skip and not is_loop:
                track = await player.queue.get_wait()  # pyright: ignore

            await self.__internal_play2(player, track.uri)  # pyright: ignore
        except wavelink.QueueEmpty:
            if chn:
                await chn.send("The queue is empty now")  # pyright: ignore

    async def __internal_play(self, ctx: commands.Context, url: str, is_radio: bool = False):
        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        if is_radio:
            dbg, _ = shared_vars.crud_database.get_or_create_guild_record(ctx.guild)
            dbg.radio_start_time = discord.utils.utcnow()
            shared_vars.crud_database.save_changes()

        await self.__internal_play2(vc, url, is_radio)

    async def __internal_play2(self, vc: wavelink.Player, url: str, is_radio: bool = False):
        tracks = await vc.node.get_tracks(wavelink.SearchableTrack, url)

        if tracks:
            track = tracks[0]
            if is_radio and not track.is_stream():
                raise commands.CommandError("Radio track must be a stream")
            await vc.play(track)
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
            await ctx.author.voice.channel.connect(cls=wavelink.Player, self_deaf=True)  # pyright: ignore
            await ctx.send("Connected to your current voice channel")

            vc: wavelink.Player = ctx.voice_client  # pyright: ignore
            setattr(vc, "skip_sent", False)
            setattr(vc, "stop_sent", False)
            setattr(vc, "loop_sent", False)
            setattr(vc, "should_send_play_now", False)
            setattr(vc, "play_now_allowed", True)
            setattr(vc, "trigger_channel_id", ctx.channel.id)
            setattr(vc, "loop_play_count", 0)
        except ClientException:
            await ctx.send("Already connected")

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.bot_in_voice)
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
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def loop(self, ctx: commands.Context):
        """Toggle loop playback of current track"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        setattr(vc, "loop_sent", not getattr(vc, "loop_sent"))
        await ctx.send(f"Loop set to {'on' if getattr(vc, 'loop_sent') else 'off'}")

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_something)
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
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_silent)
    async def resume(self, ctx: commands.Context):
        """Resume current playback, if paused"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        if not vc.is_paused():
            await ctx.send("Already resuming")
            return

        await vc.resume()
        await ctx.send("Resumed")

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_something)
    async def stop(self, ctx: commands.Context):
        """Stop current playback."""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        setattr(vc, "stop_sent", True)

        await vc.stop()
        await ctx.send("Stopped")

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_silent)
    @commands.check(MusicCogCheck.queue_has_element)
    async def play_queue(self, ctx: commands.Context):
        """Play entire queue. Normally the queue should autoplay, but who knows?"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        if vc.queue.is_empty:
            await ctx.send("Queue is empty")
            return

        track = vc.queue.get()
        await self.__internal_play(ctx, track.uri)  # pyright: ignore

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    @commands.check(MusicCogCheck.queue_has_element)
    async def skip(self, ctx: commands.Context):
        """Skip a song."""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        track: wavelink.Track = vc.track  # pyright: ignore

        if await VoteMenu("skip", track.title, ctx, vc).start():
            setattr(vc, "should_send_play_now", True)

            setattr(vc, "skip_sent", True)
            await vc.stop()
            await ctx.send("Next track should be played now")
        else:
            await ctx.send("Not skipping because not enough votes!")

    @music.command()
    @commands.guild_only()
    @app_commands.describe(pos="Position to seek to in milliseconds, defaults to run from start")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def seek(self, ctx: commands.Context, pos: Range[int, 0] = 0):
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
    @app_commands.describe(segment="Segment to seek (from 0 to 10, respecting to 0%, 10%, ..., 100%)")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def seek_segment(self, ctx: commands.Context, segment: Range[int, 0, 10] = 0):
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
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def toggle_play_now(self, ctx: commands.Context):
        """Toggle 'Now playing' message delivery"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        setattr(vc, "play_now_allowed", not getattr(vc, "play_now_allowed"))

        await ctx.send(f"'Now playing' delivery is now {'on' if getattr(vc, 'play_now_allowed') else 'off'}")

    @music.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.bot_in_voice)
    @commands.check(MusicCogCheck.bot_must_play_something)
    async def now_playing(self, ctx: commands.Context):
        """Check now playing song"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        track: wavelink.Track = vc.track  # pyright: ignore

        is_stream = track.is_stream()
        dbg, _ = shared_vars.crud_database.get_or_create_guild_record(ctx.guild)
        # next_tr: Optional[Union[Type[wavelink.Track], wavelink.tracks.Playable]]

        try:
            next_tr = vc.queue.copy().get()
        except wavelink.QueueEmpty:
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
                    value=escape_markdown(track.uri) if track.uri else "N/A",
                )
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
                    else f"Looped {getattr(vc, 'loop_play_count')} time(s)"
                    if getattr(vc, "loop_sent") is True
                    else False,
                )
                .add_field(name="Paused", value=vc.is_paused())
                .add_field(
                    name="Next track",
                    value=f"[{escape_markdown(next_tr.title) if next_tr.title else 'Unknown title'} "  # pyright: ignore
                    f"by {escape_markdown(next_tr.author)}]"  # pyright: ignore
                    f"({next_tr.uri})"  # pyright: ignore
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

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        embeds = self.generate_embeds_from_queue(vc.queue)
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

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        q = vc.queue._queue

        deleted_track: wavelink.Track = q[idx - 1]

        vc.queue._queue = collections.deque([t for t in q if t])  # pyright: ignore
        await ctx.send(f"Deleted track at position #{idx}: **{deleted_track.title}** from **{deleted_track.author}**")

    @queue.command()
    @commands.guild_only()
    @app_commands.describe(search="Search query", source="Source to search")
    @app_commands.choices(source=[Choice(name=k, value=k) for k in music_default_sources])
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def add(self, ctx: commands.Context, search: str, source: str = "youtube"):
        """Add selected track(s) to queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        if search_cls := self.resolve_direct_url(search):
            track = (await vc.node.get_tracks(search_cls, search))[0]

            if track.is_stream():
                await ctx.send("This is a stream, cannot add to queue")
                return

            vc.queue.put(track)
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

        soon_to_add_queue: List[wavelink.SearchableTrack] = []

        for val in vals:
            idx = int(val)
            soon_to_add_queue.append(tracks[idx])

        vc.queue.extend(soon_to_add_queue)
        await m.edit(content=f"Added {len(vals)} tracks into the queue", view=None)

        embeds = self.generate_embeds_from_tracks(soon_to_add_queue)
        self.bot.loop.create_task(self.show_paginated_tracks(ctx, embeds))

    @queue.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.describe(url="Playlist URL", source="Source to get playlist")
    @app_commands.choices(source=[Choice(name=k, value=k) for k in music_default_sources])
    async def add_playlist(self, ctx: commands.Context, url: str, source: str = "youtube"):
        """Add track(s) from playlist to queue"""
        await ctx.defer()

        tracks: Optional[
            Union[
                List[wavelink.YouTubeTrack],
                List[wavelink.YouTubeMusicTrack],
                List[spotify.SpotifyTrack],
                List[wavelink.SoundCloudTrack],
                List[Type[wavelink.tracks.Playable]],
                List[Type[wavelink.SearchableTrack]],
            ]
        ] = []

        if source == "youtube":
            try:
                pl = (await wavelink.YouTubePlaylist.search(url)).tracks  # pyright: ignore
            except wavelink.LoadTrackError:
                pl = await wavelink.YouTubeTrack.search(url)
            tracks = pl
        elif source == "ytmusic":
            tracks = await wavelink.YouTubeMusicTrack.search(url)
        elif source == "spotify":
            tracks = await spotify.SpotifyTrack.search(url, type=spotify.SpotifySearchType.playlist)  # pyright: ignore
        elif source == "soundcloud":
            tracks = await wavelink.SoundCloudTrack.search(query=url)

        if not tracks:
            await ctx.send(f"No tracks found for {url} on {source}, have you checked your URL?")
            return

        player: wavelink.Player = ctx.voice_client  # pyright: ignore
        accepted_tracks = [track for track in tracks if not track.is_stream()]  # pyright: ignore
        player.queue.extend(accepted_tracks)  # pyright: ignore
        await ctx.send(f"Added {len(tracks)} track(s) from {url} to the queue")

        embeds = self.generate_embeds_from_tracks(accepted_tracks)  # pyright: ignore
        self.bot.loop.create_task(self.show_paginated_tracks(ctx, embeds))

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

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        int_queue = vc.queue._queue
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

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        q = vc.queue._queue
        q_length = len(q)

        if not (1 <= pos1 <= q_length and 1 <= pos2 <= q_length):
            await ctx.send(f"Invalid position(s): ({pos1}, {pos2})")
            return

        q[pos1 - 1], q[pos2 - 1] = (
            q[pos2 - 1],
            q[pos1 - 1],
        )

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

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        random.shuffle(vc.queue._queue)  # pyright: ignore
        await ctx.send("Shuffled the queue")

    @queue.command()
    @commands.guild_only()
    @commands.check(MusicCogCheck.user_and_bot_in_voice)
    @commands.check(MusicCogCheck.queue_has_element)
    async def clear(self, ctx: commands.Context):
        """Clear the queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        if await VoteMenu("clear", "queue", ctx, vc).start():
            vc.queue.clear()
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

        vc: wavelink.Player = ctx.voice_client  # pyright: ignore

        vc.queue.clear()
        await ctx.send("Cleared the queue")

    @add.after_invoke
    @add_playlist.after_invoke
    async def autoplay_queue(self, ctx: commands.Context):
        vc: wavelink.Player = ctx.voice_client  # pyright: ignore
        if not vc.is_playing():
            await vc.play(vc.queue.get())


async def setup(bot: Nameless):
    if (lvl := getattr(NamelessConfig, "LAVALINK", None)) and lvl.get("nodes", []):
        await bot.add_cog(MusicCog(bot))
        logging.info("Cog of %s added!", __name__)
    else:
        raise commands.ExtensionFailed(__name__, ValueError("Lavalink options are not properly provided"))


async def teardown(bot: Nameless):
    await bot.remove_cog("MusicCog")
    logging.warning("Cog of %s removed!", __name__)
