from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import random
from typing import TYPE_CHECKING, cast, final, override

import aiohttp.client_exceptions
import discord
import pomice
from discord import app_commands
from discord.ext import commands

from nameless.config import LavalinkNode, nameless_config
from nameless.custom.ui import NamelessPaginatedView

from .cache import TrackCache
from .exceptions import (
    AutoplayDisabledError,
    EmptyQueueError,
    InvalidParameterError,
    InvalidPositionError,
    InvalidVolumeError,
    NoTracksFoundError,
    TrackNotSeekableError,
)
from .player import CustomPlayer, lavalink
from .player_manager import PlayerManager
from .ui.embeds import (
    create_added_embed,
    create_eq_preview_embed,
    create_error_embed,
    create_error_embed_from_exception,
    create_info_embed,
    create_now_playing_embed,
    create_playlist_embed,
    create_queue_embed,
    create_success_embed,
    format_duration,
)
from .ui.options import EQSettingsView
from .ui.track_selector import TrackSelector
from .ui.vote_skip import VoteSkipView

if TYPE_CHECKING:
    from nameless.nameless import Nameless


__all__ = ["MusicCommands"]

SOURCE_MAPPING = {
    "youtube": pomice.SearchType.ytsearch,
    "soundcloud": pomice.SearchType.scsearch,
    "ytmusic": pomice.SearchType.ytmsearch,
}


@final
class MusicCommands(commands.GroupCog, name="music"):
    __slots__ = (
        "_connect_task",
        "_lavalink_nodes",
        "bot",
        "cache",
        "node_pool",
        "player_manager",
        "track_selector",
    )

    if TYPE_CHECKING:
        bot: Nameless
        node_pool: pomice.NodePool
        _connect_task: asyncio.Task[None] | None
        _lavalink_nodes: list[LavalinkNode]

    def __init__(self, bot: Nameless):
        self.bot = bot

        self.player_manager = PlayerManager(bot)
        self.track_selector = TrackSelector()
        self.cache = TrackCache()

        self.node_pool = pomice.NodePool()
        self._lavalink_nodes = nameless_config.lavalinks
        self._connect_task = self.bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self, max_retries: int = 5, retry_delay: int = 5) -> None:
        logging.info("Waiting for Discord connection before connecting to Lavalink...")
        await self.bot.wait_until_ready()
        logging.info("Discord ready. Connecting to Lavalink nodes...")

        pending_nodes = self._lavalink_nodes.copy()

        for retry_attempt in range(max_retries + 1):
            if not pending_nodes:
                break

            if retry_attempt > 0:
                retry_timer = retry_delay * retry_attempt
                logging.info("Retry attempt %d/%d after %d seconds...", retry_attempt, max_retries, retry_timer)
                await asyncio.sleep(retry_timer)

            nodes_to_retry = pending_nodes.copy()
            pending_nodes.clear()

            for try_node in nodes_to_retry:
                node = pomice.Node(
                    pool=pomice.NodePool,
                    bot=self.bot,
                    host=try_node.host,
                    port=try_node.port,
                    password=try_node.password,
                    identifier=try_node.identifier,
                    secure=try_node.secure,
                    fallback=True,
                )
                try:
                    await node.connect()
                    self.node_pool.nodes[node._identifier] = node
                    logging.info("Connected to Lavalink node: %s", node._identifier)
                except Exception as e:
                    # manual cleanup
                    with contextlib.suppress(Exception):
                        await node._session.close()
                    with contextlib.suppress(Exception):
                        await node._websocket.close()

                    node_id = try_node.identifier
                    pending_nodes.append(try_node)
                    if retry_attempt < max_retries:
                        logging.warning(
                            "Failed to connect to node %s (attempt %d/%d): %s",
                            node_id,
                            retry_attempt + 1,
                            max_retries + 1,
                            e,
                        )
                    else:
                        logging.error(
                            "Failed to connect to node %s after %d attempts: %s",
                            node_id,
                            max_retries + 1,
                            e,
                            exc_info=True,
                        )

        if pending_nodes:
            logging.warning("Failed to connect to %d node(s) after %d retry attempts", len(pending_nodes), max_retries)
        else:
            logging.info("Successfully connected to all Lavalink nodes")

        if self._connect_task:
            self._connect_task = None

    @commands.Cog.listener()
    async def on_pomice_track_start(self, player: CustomPlayer, track: pomice.Track):
        player.cancel_disconnect_timer()

        if not player.np_message_allowed or player.queue.loop_mode == pomice.LoopMode.TRACK:
            return

        if self.bot.user:
            embed = create_now_playing_embed(player, track, track.requester or self.bot.user)
            await player.send_to_trigger_channel(embed=embed, make_controller=True)

    @commands.Cog.listener()
    async def on_pomice_track_end(self, player: CustomPlayer, track: pomice.Track, reason: str):
        logging.info(
            "Track ended in guild %s, reason: %s, track_title: %s",
            player.guild.id if player.guild else "Unknown",
            reason,
            track.title,
        )
        reason = reason.lower()
        # https://lavalink.dev/api/websocket.html#track-end-reason
        # https://github.com/lavalink-devs/Lavalink/blob/71cde9161ffd4fdbeba99e0f2d8d766904056926/protocol/src/commonMain/kotlin/dev/arbjerg/lavalink/protocol/v4/messages.kt#L164-L200
        if reason in ("finished", "loadfailed", "stopped"):
            await player.do_next()

    @commands.Cog.listener()
    async def on_pomice_track_stuck(self, player: CustomPlayer, track: pomice.Track, _threshold: int):
        logging.warning("Track stuck: %s in guild %s", track.title, player.guild.id if player.guild else "Unknown")
        # await player.do_next()

    @commands.Cog.listener()
    async def on_pomice_track_exception(self, player: CustomPlayer, track: pomice.Track, exception: dict[str, str]):
        logging.error(
            "Track exception: %s in guild %s - %s",
            track.title,
            player.guild.id if player.guild else "Unknown",
            "\n\t".join(f"{k}={v}" for k, v in exception.items()),
        )

        cause = exception.get("cause", "Unknown error")
        if "403" in cause or "java.lang.RuntimeException" in cause:
            embed = create_error_embed("Playback Error", f"Cannot play track: {cause}")
            await player.send_to_trigger_channel(embed=embed, make_controller=False)
            await player.disable_last_control_view()
        else:
            embed = create_error_embed("Playback Error", f"An error occurred: {cause}")
            await player.send_to_trigger_channel(embed=embed, make_controller=False)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if not member.guild:
            return

        player = await self.player_manager.get_player_by_guild_id(member.guild.id)
        if not player:
            return

        assert self.bot.user is not None  # for type checking
        if not after.channel:
            if member.id == self.bot.user.id and player.is_playing:
                await player.destroy()
                player.cleanup()
            embed = create_info_embed("Disconnected", "I have been disconnected from the voice channel.")
            await player.send_to_trigger_channel(embed=embed, make_controller=False)
        else:
            vc_members = filter(lambda m: not m.bot, after.channel.members)
            if not any(m.id != self.bot.user.id for m in vc_members):
                # TODO: add a config option for auto-pause instead of hardcoding it here
                await player.set_pause(True)
                embed = create_info_embed(
                    "Auto-Paused",
                    "Playback has been auto-paused because everyone left the voice channel. "
                    "It will automatically resume when someone joins.",
                )
                await player.send_to_trigger_channel(embed=embed, make_controller=False)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context[Nameless], error: commands.CommandError):
        embed = create_error_embed_from_exception("Error", error)
        await ctx.send(embed=embed)

    async def _search_tracks(
        self, query: str, source: str, player: CustomPlayer
    ) -> list[pomice.Track] | pomice.Playlist | None:
        cached_result = self.cache.get(query, source)
        if cached_result:
            return cached_result

        search_type = SOURCE_MAPPING.get(source, pomice.SearchType.ytsearch)
        results = await player.get_tracks(query, search_type=search_type)

        if isinstance(results, list):
            self.cache.set(query, source, results)

        return results

    async def _add_tracks_to_queue(
        self, player: CustomPlayer, tracks: list[pomice.Track], requester: discord.Member, position: int = 0
    ) -> int:
        if not tracks:
            return 0

        for track in tracks:
            track.requester = requester

        total_size = len(player.queue) + len(tracks)
        if player.queue.max_size and (total_size > player.queue.max_size):
            raise commands.CommandError(f"Queue size limit exceeded! Maximum {player.queue.max_size} tracks allowed.")

        if position <= 0:
            player.queue.extend(tracks)
        else:
            queue_list = list(player.queue._queue)
            insert_pos = min(position - 1, len(queue_list))
            queue_list[insert_pos:insert_pos] = tracks
            player.queue.clear()
            player.queue.extend(queue_list)

        return len(tracks)

    @commands.hybrid_command()
    @app_commands.describe(channel="Voice channel to connect to")
    async def connect(
        self,
        ctx: commands.Context[Nameless],
        channel: discord.VoiceChannel | discord.StageChannel | None = None,
        bypass_checks: bool = False,
    ) -> None:
        await ctx.defer()

        player = await self.player_manager.connect_to_voice(ctx, channel, bypass_checks=bypass_checks)
        if player and ctx.guild:
            embed = create_success_embed("Connected", f"Connected to **{player.channel.name}**")
            await player.send_to_channel(ctx, embed=embed, make_controller=True)
        else:
            raise commands.CommandError("Failed to connect to voice channel")

    @commands.hybrid_command(aliases=["dc", "leave"])
    @app_commands.guild_only()
    async def disconnect(self, ctx: commands.Context[Nameless]) -> None:
        success = await self.player_manager.disconnect_player(ctx)
        if success:
            embed = create_success_embed("Disconnected", "Successfully disconnected from voice channel")
        else:
            embed = create_error_embed("Not Connected", "I'm not connected to a voice channel")
        await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["p", "add"])
    @app_commands.guild_only()
    @app_commands.describe(
        query="Song name, URL, or playlist to play",
        position="Position in queue (0 = end)",
        source="Music source to search",
        shuffle="Shuffle tracks before adding",
    )
    @app_commands.choices(
        source=[
            app_commands.Choice(name=name.title(), value=value)
            for name, value in {"youtube": "youtube", "youtube_music": "ytmusic", "soundcloud": "soundcloud"}.items()
        ]
    )
    async def play(
        self,
        ctx: commands.Context[Nameless],
        query: str,
        position: int = 0,
        source: str = "youtube",
        shuffle: bool = False,
    ) -> None:
        await ctx.defer()

        player = await self.player_manager.get_or_create_player(ctx)

        results = await self._search_tracks(query, source, player)
        if not results:
            raise NoTracksFoundError(query)

        tracks: list[pomice.Track]
        if isinstance(results, pomice.Playlist):
            tracks = results.tracks
            embed = create_playlist_embed(results)
        else:
            tracks = await self.track_selector.select_tracks(ctx, results)
            if not tracks:
                return

            embed = create_added_embed(tracks, len(tracks))

        if shuffle:
            random.shuffle(tracks)

        await self._add_tracks_to_queue(player, tracks, cast("discord.Member", ctx.author), position)

        if player.current:
            await player.update_now_playing_embed()

        if not player.is_playing and player.queue:
            await player.play(player.queue.get())

        await player.send_to_channel(ctx, embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def pause(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if player.is_paused:
            embed = create_info_embed("Already Paused", "The player is already paused")
        else:
            await player.set_pause(True)
            await player.update_now_playing_embed()
            embed = create_success_embed("Paused", "Playback has been paused")

        await player.send_to_channel(ctx, embed=embed, make_controller=True)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def resume(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.is_paused:
            embed = create_info_embed("Already Playing", "The player is already playing")
        else:
            await player.set_pause(False)
            await player.update_now_playing_embed()
            embed = create_success_embed("Resumed", "Playback has been resumed")

        await player.send_to_channel(ctx, embed=embed, make_controller=True)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def skip(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.current:
            raise EmptyQueueError()

        current_track = player.current
        await player.stop()

        embed = create_success_embed("Skipped", f"Skipped **{current_track.title}**")
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def voteskip(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.current:
            raise EmptyQueueError()

        if player.vote_skip_in_progress:
            await ctx.send("A vote to skip this track is already in progress.", ephemeral=True)
            return

        vc_members = [m for m in player.channel.members if not m.bot]
        required = (len(vc_members) // 2) + 1

        async with player.vote_skip_context():
            view = VoteSkipView(player, ctx.author.id, required, timeout=60)
            embed = view.create_embed(player.current.title, ctx.author.display_name)

            message = await ctx.send(embed=embed, view=view)
            view.set_message(message)
            await view.wait()

            track_title = player.current.title if player.current else "track"
            final_embed = view.create_result_embed(track_title, ctx.author.display_name)
            await message.edit(embed=final_embed, view=None)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def history(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.history:
            await ctx.send("No history found.")
            return

        history_text: list[str] = []
        for i, track in enumerate(iter(player.history), 1):
            history_text.append(f"{i}. **{track.title}**")

        embed = discord.Embed(
            title="📜 Recently Played", description="\n".join(history_text), color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def export(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.queue:
            raise EmptyQueueError()

        content = "\n".join(f"{track.title} - {track.uri}" for track in player.queue)
        file = discord.File(io.BytesIO(content.encode()), filename="queue.txt")

        await ctx.send("Here is your exported queue:", file=file)

    @commands.hybrid_command()
    @app_commands.guild_only()
    @app_commands.describe(index="Queue index (0 for current)")
    async def info(self, ctx: commands.Context[Nameless], index: int = 0) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        track: pomice.Track | None = None
        if index == 0:
            track = player.current
        elif 1 <= index <= len(player.queue):
            track = player.queue[index - 1]

        if not track:
            await ctx.send("Track not found.")
            return

        embed = discord.Embed(title="Track Info", color=discord.Color.blue())
        embed.add_field(name="Title", value=track.title, inline=False)
        embed.add_field(name="Author", value=track.author, inline=True)
        embed.add_field(name="Duration", value=format_duration(track.length), inline=True)
        embed.add_field(name="Identifier", value=f"`{track.identifier}`", inline=True)
        embed.add_field(name="Seekable", value="Yes" if track.is_seekable else "No", inline=True)
        embed.add_field(name="Stream", value="Yes" if track.is_stream else "No", inline=True)
        embed.set_thumbnail(url=track.thumbnail)

        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    @app_commands.describe(speed="Playback speed (0.5 - 2.0)")
    async def speed(self, ctx: commands.Context[Nameless], speed: float) -> None:
        if not 0.5 <= speed <= 2.0:
            await ctx.send("Speed must be between 0.5 and 2.0.")
            return

        player = await self.player_manager.get_or_create_player(ctx)
        await player.set_speed(speed)

        embed = create_success_embed("Speed Changed", f"Playback speed set to **{speed}x**")
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="filter", with_app_command=True)
    async def filter(self, ctx: commands.Context[Nameless]):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @filter.command()
    @app_commands.guild_only()
    async def equalizer(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_player(ctx, raise_on_unconnected=True)

        embed = create_eq_preview_embed(player)
        view = EQSettingsView(player)
        await ctx.send(embed=embed, view=view)

    @filter.command()
    @app_commands.guild_only()
    async def stop(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        await player.stop()
        player.queue.clear()

        embed = create_success_embed("Stopped", "Playback stopped and queue cleared")
        await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["q"])
    @app_commands.guild_only()
    async def queue(self, ctx: commands.Context[Nameless]) -> None:
        await ctx.defer()
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.queue and not player.auto_queue:
            raise EmptyQueueError()

        all_tracks = player.queue._queue

        tracks_per_page = 10
        pages: list[discord.Embed] = []
        total_duration = player.total_duration

        for i in range(0, len(all_tracks), tracks_per_page):
            page_tracks = all_tracks[i : i + tracks_per_page]
            page_num = i // tracks_per_page + 1
            total_pages = (len(all_tracks) + tracks_per_page - 1) // tracks_per_page

            embed = create_queue_embed(page_tracks, page_num, total_pages, total_duration)
            pages.append(embed)

        view = NamelessPaginatedView(ctx, timeout=120)
        view.add_pages(pages)
        view.add_predefined_buttons()
        await view.start()

    @commands.hybrid_command(aliases=["np", "nowplaying", "playing"])
    @app_commands.guild_only()
    async def current(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.current:
            embed = create_info_embed("Nothing Playing", "No track is currently playing")
            await ctx.send(embed=embed)
            return

        embed = create_now_playing_embed(player, player.current, ctx.author)
        await player.send_to_channel(ctx, embed=embed, make_controller=True)

    @commands.hybrid_command(aliases=["random"])
    @app_commands.guild_only()
    async def shuffle(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.queue:
            raise EmptyQueueError()

        player.queue.shuffle()
        embed = create_success_embed("Shuffled", f"Shuffled {len(player.queue)} tracks")
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Off", value="OFF"),
            app_commands.Choice(name="Track", value="TRACK"),
            app_commands.Choice(name="Queue", value="QUEUE"),
        ]
    )
    async def loop(self, ctx: commands.Context[Nameless], mode: str | None = None) -> None:
        player = await self.player_manager.get_or_create_player(ctx)
        if not mode:
            await ctx.send(
                embed=create_info_embed(
                    "Loop Mode",
                    "Current loop mode is **{mode}**".format(
                        mode=player.queue.loop_mode.name if player.queue.loop_mode else "OFF"
                    ),
                )
            )
            return

        mode = mode.upper()
        if mode == "OFF":
            player.queue.disable_loop()
        else:
            player.queue.set_loop_mode(pomice.LoopMode[mode])

        # Update the last control message if it exists
        await player.update_now_playing_embed()

        embed = create_success_embed("Loop Mode Changed", f"Loop mode set to **{mode or 'Off'}**")
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    @app_commands.describe(volume="Volume level (0-200)")
    async def volume(self, ctx: commands.Context[Nameless], volume: int) -> None:
        if not 0 <= volume <= 200:
            raise InvalidVolumeError(volume)

        player = await self.player_manager.get_or_create_player(ctx)
        await player.set_volume(volume)

        # Update the last control message if it exists
        await player.update_now_playing_embed()

        embed = create_success_embed("Volume Changed", f"Volume set to **{volume}%**")
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    @app_commands.describe(index="Track number to remove (1-based)")
    async def remove(self, ctx: commands.Context[Nameless], index: int) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.queue:
            raise EmptyQueueError()

        if not 1 <= index <= len(player.queue):
            raise InvalidPositionError(index, len(player.queue))

        removed_track = player.queue[index - 1]
        player.queue.remove(removed_track)

        embed = create_success_embed("Track Removed", f"Removed **{removed_track.title}** from queue")
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    @app_commands.describe(from_pos="Current position", to_pos="New position")
    async def move(self, ctx: commands.Context[Nameless], from_pos: int, to_pos: int) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.queue:
            raise EmptyQueueError()

        if not (1 <= from_pos <= len(player.queue)) or not (1 <= to_pos <= len(player.queue)):
            raise commands.CommandError("Invalid positions provided.")

        queue_list = list(player.queue._queue)
        track = queue_list.pop(from_pos - 1)
        queue_list.insert(to_pos - 1, track)

        player.queue.clear()
        player.queue.extend(queue_list)

        embed = create_success_embed("Track Moved", f"Moved **{track.title}** from #{from_pos} to #{to_pos}")
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    @app_commands.describe(pos1="First position", pos2="Second position")
    async def swap(self, ctx: commands.Context[Nameless], pos1: int, pos2: int) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.queue:
            raise EmptyQueueError()

        if not (1 <= pos1 <= len(player.queue)) or not (1 <= pos2 <= len(player.queue)):
            raise commands.CommandError("Invalid positions provided.")

        player.queue.swap(pos1 - 1, pos2 - 1)

        embed = create_success_embed("Tracks Swapped", f"Swapped tracks at #{pos1} and #{pos2}")
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    @app_commands.describe(index="Position to jump to")
    async def jump(self, ctx: commands.Context[Nameless], index: int) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.queue:
            raise EmptyQueueError()

        if not 1 <= index <= len(player.queue):
            raise InvalidPositionError(index, len(player.queue))

        # Remove tracks before the index
        for _ in range(index - 1):
            player.queue.get()

        await player.stop()
        embed = create_success_embed("Jumped", f"Jumped to track #{index}")
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def clear(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.queue:
            raise EmptyQueueError()

        track_count = len(player.queue)
        player.queue.clear()

        embed = create_success_embed("Queue Cleared", f"Removed {track_count} tracks from queue")
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def seek(
        self, ctx: commands.Context[Nameless], hours: int = 0, minutes: int = 0, seconds: int = 0, percent: float = 0.0
    ) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.current:
            embed = create_error_embed("No Track", "No track is currently playing")
            await ctx.send(embed=embed)
            return

        if not player.current.is_seekable:
            raise TrackNotSeekableError()

        if percent > 0:
            position = int(player.current.length * (percent / 100))
        else:
            total_seconds = hours * 3600 + minutes * 60 + seconds
            position = total_seconds * 1000

        if position < 0 or position > player.current.length:
            embed = create_error_embed("Invalid Position", "Seek position is out of track bounds")
            await ctx.send(embed=embed)
            return

        await player.seek(position)

        pos_seconds = position // 1000
        pos_minutes, pos_seconds = divmod(pos_seconds, 60)
        pos_hours, pos_minutes = divmod(pos_minutes, 60)

        if pos_hours:
            pos_str = f"{pos_hours}:{pos_minutes:02d}:{pos_seconds:02d}"
        else:
            pos_str = f"{pos_minutes}:{pos_seconds:02d}"

        embed = create_success_embed("Seeked", f"Seeked to **{pos_str}**")
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="autoplay", with_app_command=True)
    async def autoplay(self, ctx: commands.Context[Nameless]):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @autoplay.command(name="toggle")
    @app_commands.guild_only()
    async def autoplay_toggle(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        player.toggle_autoplay()
        if player.is_autoplay_enabled:
            await player.refresh_auto_queue()

        # Update the last control message if it exists
        await player.update_now_playing_embed()

        embed = create_success_embed(
            "Autoplay Toggled", f"Autoplay mode has been {'enabled' if player.is_autoplay_enabled else 'disabled'}"
        )
        await ctx.send(embed=embed)

    @autoplay.command(name="refresh")
    @app_commands.guild_only()
    async def autoplay_refresh(self, ctx: commands.Context[Nameless]) -> None:
        await ctx.defer()

        player = await self.player_manager.get_or_create_player(ctx)

        if not player.is_autoplay_enabled:
            raise AutoplayDisabledError()

        if not player.current:
            embed = create_error_embed("No Track", "Need a track playing to refresh autoplay")
            await ctx.send(embed=embed)
            return

        await player.refresh_auto_queue()

        # Update the last control message if it exists
        await player.update_now_playing_embed()

        embed = create_success_embed("Autoplay Refreshed", "Autoplay queue has been refreshed")
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="auto_disconnect")
    async def auto_disconnect(self, ctx: commands.Context[Nameless]):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    # scaffold
    @auto_disconnect.command(name="set")
    @app_commands.guild_only()
    @app_commands.describe(timeout="Timeout in seconds (0 to disable)")
    async def set_auto_disconnect(self, ctx: commands.Context[Nameless], timeout: int) -> None:
        if timeout < 0:
            raise InvalidParameterError("timeout", f"{timeout}. Must be 0 or positive.")

        player = await self.player_manager.get_or_create_player(ctx)
        if timeout == 0:
            player.set_auto_disconnect(False, 0)
            embed = create_success_embed(
                "Auto-Disconnect Disabled",
                "Auto-disconnect has been disabled",
            )
        else:
            player.set_auto_disconnect(True, timeout)
            embed = create_success_embed(
                "Auto-Disconnect Set",
                f"Auto-disconnect timeout set to **{timeout} seconds**",
            )
        await ctx.send(embed=embed)

    @auto_disconnect.command(name="toggle")
    @app_commands.guild_only()
    async def toggle_auto_disconnect(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)
        player.set_auto_disconnect(not player.is_auto_disconnect_enabled)
        embed = create_success_embed(
            "Auto-Disconnect Toggled",
            f"Auto-disconnect has been {'enabled' if player.is_auto_disconnect_enabled else 'disabled'}",
        )
        await ctx.send(embed=embed)

    @override
    async def cog_unload(self):
        if self._connect_task:
            self._connect_task.cancel()
            self._connect_task = None
        with contextlib.suppress(aiohttp.client_exceptions.ClientConnectorError, ConnectionRefusedError):
            await self.node_pool.disconnect()


async def setup(bot: Nameless):
    lavalink_host_settings = nameless_config.lavalink_host_settings
    autostart_lavalink = lavalink_host_settings.auto_start
    autoupdate_lavalink = lavalink_host_settings.auto_update

    lavalinks = nameless_config.lavalinks
    if autostart_lavalink:
        default_node = LavalinkNode(
            host="localhost",
            port=18233,
            password="youshallnotpass",  # noqa  default password
            identifier="default-node",
        )
        lavalinks.append(default_node)

    if autostart_lavalink:
        try:
            await lavalink.main(bot.loop, autoupdate_lavalink)
        except ImportError:
            logging.warning("Could not import lavalink module. Lavalink auto-start disabled.")
        except Exception as e:
            logging.error("Failed to start lavalink: %s", e)
    elif not lavalinks:
        logging.warning("No lavalink nodes configured and auto-start is disabled. Music commands will not work.")

    await bot.add_cog(MusicCommands(bot))
    logging.info("Enhanced music commands loaded successfully!")


async def teardown(bot: Nameless):
    # unloaded the cog first to trigger the cog_unload and
    # disconnect from lavalink nodes before we lose access to the node pool
    await bot.remove_cog("music")
    logging.info("Music commands unloaded!")

    # lavalink should be unloaded last for cleaner shutdown and to ensure we can disconnect properly
    if nameless_config.lavalink_host_settings.auto_start:
        try:
            logging.info("Stopping Lavalink node...")
            await lavalink.stop()
        except Exception as e:
            logging.error("Error stopping lavalink: %s", e, exc_info=True)
