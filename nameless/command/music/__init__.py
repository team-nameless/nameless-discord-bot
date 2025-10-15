from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, final, override

import aiohttp.client_exceptions
import discord
import pomice
from discord import app_commands
from discord.ext import commands

from nameless.config import LavalinkNode, nameless_config
from nameless.custom.ui import NamelessPaginatedView

from .cache import TrackCache
from .embeds import EmbedGenerator
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
from .track_selector import TrackSelector

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
        "bot",
        "is_ready",
        "pomice",
        "_connect_task",
        "_lavalink_nodes",
        "player_manager",
        "embed_generator",
        "track_selector",
        "cache",
        "config",
    )

    if TYPE_CHECKING:
        bot: Nameless
        node_pool: pomice.NodePool
        _connect_task: asyncio.Task[None] | None
        _lavalink_nodes: list[LavalinkNode]

    def __init__(self, bot: Nameless):
        self.bot = bot
        self.is_ready = asyncio.Event()

        self.player_manager = PlayerManager(bot)
        self.embed_generator = EmbedGenerator()
        self.track_selector = TrackSelector()
        self.cache = TrackCache()

        self.node_pool = pomice.NodePool()
        self._connect_task = self.bot.loop.create_task(self.connect_nodes())
        self._lavalink_nodes = nameless_config.lavalinks

    async def connect_nodes(self, max_retries: int = 5, retry_delay: int = 5) -> None:
        logging.info("Waiting for Discord connection before connecting to Lavalink...")
        await self.bot.wait_until_ready()
        logging.info("Discord ready. Connecting to Lavalink nodes...")

        pending_nodes = self._lavalink_nodes.copy()

        for retry_attempt in range(max_retries + 1):
            if not pending_nodes:
                break

            if retry_attempt > 0:
                logging.info("Retry attempt %d/%d after %d seconds...", retry_attempt, max_retries, retry_delay)
                await asyncio.sleep(retry_delay)

            nodes_to_retry = pending_nodes.copy()
            pending_nodes.clear()

            for node in nodes_to_retry:
                try:
                    _node = await self.node_pool.create_node(
                        bot=self.bot,
                        host=node.host,
                        port=node.port,
                        password=node.password,
                        identifier=node.identifier,
                        secure=node.secure,
                    )
                    logging.info("Connected to Lavalink node: %s", _node._identifier)
                except Exception as e:
                    node_id = node.identifier
                    if retry_attempt < max_retries:
                        logging.warning(
                            "Failed to connect to node %s (attempt %d/%d): %s",
                            node_id,
                            retry_attempt + 1,
                            max_retries + 1,
                            e,
                        )
                        pending_nodes.append(node)
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

        self.is_ready.set()
        if self._connect_task:
            self._connect_task = None

    @commands.Cog.listener()
    async def on_pomice_track_start(self, player: CustomPlayer, track: pomice.Track):
        if not player.np_message_allowed or player.queue.loop_mode == pomice.LoopMode.TRACK:
            return

        if self.bot.user:
            embed = self.embed_generator.create_now_playing_embed(player, track, self.bot.user)
            await player.send_to_trigger_channel(embed=embed, make_controller=True)

    @commands.Cog.listener()
    async def on_pomice_track_end(self, player: CustomPlayer, _reason: str, _track: pomice.Track):
        await player.do_next()

    @commands.Cog.listener()
    async def on_pomice_track_stuck(self, player: CustomPlayer, track: pomice.Track, _threshold: int):
        logging.warning("Track stuck: %s in guild %s", track.title, player.guild.id if player.guild else "Unknown")
        await player.do_next()

    @commands.Cog.listener()
    async def on_pomice_track_exception(self, player: CustomPlayer, track: pomice.Track, exception: dict[str, str]):
        logging.error(
            "Track exception: %s in guild %s - %s",
            track.title,
            player.guild.id if player.guild else "Unknown",
            "\n\t".join(f"{k}={v}" for k, v in exception.items()),
        )

        should_skip = await player.handle_track_error(track)
        if should_skip:
            await player.do_next()
            return

        cause = exception.get("cause", "Unknown error")
        if "403" in cause or "java.lang.RuntimeException" in cause:
            embed = self.embed_generator.create_error_embed("Playback Error", f"Cannot play track: {cause}")
            await player.send_to_trigger_channel(embed=embed, make_controller=False)
            await player.disable_last_control_view()
        else:
            embed = self.embed_generator.create_error_embed("Playback Error", f"An error occurred: {cause}")
            await player.send_to_trigger_channel(embed=embed, make_controller=False)

        await player.do_next()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, _: discord.VoiceState, after: discord.VoiceState):
        if self.bot.user and member.id == self.bot.user.id and not after.deaf:
            await member.edit(deafen=True)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context[Nameless], error: commands.CommandError):
        embed = self.embed_generator.create_error_embed_from_exception("Error", error)
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

    async def _add_tracks_to_queue(self, player: CustomPlayer, tracks: list[pomice.Track], position: int = 0) -> int:
        if not tracks:
            return 0

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
    ) -> None:
        await ctx.defer()

        player = await self.player_manager.connect_to_voice(ctx, channel)
        if player and ctx.guild:
            embed = self.embed_generator.create_success_embed("Connected", f"Connected to **{player.channel.name}**")
            await player.send_to_channel(ctx, embed=embed, make_controller=True)
        else:
            raise commands.CommandError("Failed to connect to voice channel")

    @commands.hybrid_command(aliases=["dc", "leave"])
    @app_commands.guild_only()
    async def disconnect(self, ctx: commands.Context[Nameless]) -> None:
        success = await self.player_manager.disconnect_player(ctx)
        if success:
            embed = self.embed_generator.create_success_embed(
                "Disconnected", "Successfully disconnected from voice channel"
            )
        else:
            embed = self.embed_generator.create_error_embed("Not Connected", "I'm not connected to a voice channel")
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

        if isinstance(results, pomice.Playlist):
            tracks = results.tracks
            embed = self.embed_generator.create_playlist_embed(results)
        else:
            tracks = await self.track_selector.select_tracks(ctx, results)
            if not tracks:
                return

            embed = self.embed_generator.create_added_embed(tracks, len(tracks))

        if shuffle:
            import random

            random.shuffle(tracks)

        await self._add_tracks_to_queue(player, tracks, position)

        if not player.is_playing and player.queue:
            await player.play(player.queue.get())

        await player.send_to_channel(ctx, embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def pause(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if player.is_paused:
            embed = self.embed_generator.create_info_embed("Already Paused", "The player is already paused")
        else:
            await player.set_pause(True)
            embed = self.embed_generator.create_success_embed("Paused", "Playback has been paused")

        await player.send_to_channel(ctx, embed=embed, make_controller=True)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def resume(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.is_paused:
            embed = self.embed_generator.create_info_embed("Already Playing", "The player is already playing")
        else:
            await player.set_pause(False)
            embed = self.embed_generator.create_success_embed("Resumed", "Playback has been resumed")

        await player.send_to_channel(ctx, embed=embed, make_controller=True)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def skip(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.current:
            raise EmptyQueueError()

        current_track = player.current
        await player.stop()

        embed = self.embed_generator.create_success_embed("Skipped", f"Skipped **{current_track.title}**")
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def stop(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        await player.stop()
        player.queue.clear()

        embed = self.embed_generator.create_success_embed("Stopped", "Playback stopped and queue cleared")
        await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["q"])
    @app_commands.guild_only()
    async def queue(self, ctx: commands.Context[Nameless]) -> None:
        await ctx.defer()
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.queue and not player.auto_queue:
            raise EmptyQueueError()

        all_tracks = list(player.queue._queue)
        if player.auto_queue:
            all_tracks.extend(list(player.auto_queue))

        if not all_tracks:
            raise EmptyQueueError()

        tracks_per_page = 10
        pages: list[discord.Embed] = []

        for i in range(0, len(all_tracks), tracks_per_page):
            page_tracks = all_tracks[i : i + tracks_per_page]
            page_num = i // tracks_per_page + 1
            total_pages = (len(all_tracks) + tracks_per_page - 1) // tracks_per_page

            embed = self.embed_generator.create_queue_embed(page_tracks, page_num, total_pages)
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
            embed = self.embed_generator.create_info_embed("Nothing Playing", "No track is currently playing")
            await ctx.send(embed=embed)
            return

        embed = self.embed_generator.create_now_playing_embed(player, player.current, ctx.author)
        await player.send_to_channel(ctx, embed=embed, make_controller=True)

    @commands.hybrid_command(aliases=["random"])
    @app_commands.guild_only()
    async def shuffle(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.queue:
            raise EmptyQueueError()

        player.queue.shuffle()
        embed = self.embed_generator.create_success_embed("Shuffled", f"Shuffled {len(player.queue)} tracks")
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
                embed=self.embed_generator.create_info_embed(
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
        embed = self.embed_generator.create_success_embed("Loop Mode Changed", f"Loop mode set to **{mode or 'Off'}**")
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    @app_commands.describe(volume="Volume level (0-200)")
    async def volume(self, ctx: commands.Context[Nameless], volume: int) -> None:
        if not 0 <= volume <= 200:
            raise InvalidVolumeError(volume)

        player = await self.player_manager.get_or_create_player(ctx)
        await player.set_volume(volume)

        embed = self.embed_generator.create_success_embed("Volume Changed", f"Volume set to **{volume}%**")
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

        embed = self.embed_generator.create_success_embed(
            "Track Removed", f"Removed **{removed_track.title}** from queue"
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def clear(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.queue:
            raise EmptyQueueError()

        track_count = len(player.queue)
        player.queue.clear()

        embed = self.embed_generator.create_success_embed("Queue Cleared", f"Removed {track_count} tracks from queue")
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def seek(
        self, ctx: commands.Context[Nameless], hours: int = 0, minutes: int = 0, seconds: int = 0, percent: float = 0.0
    ) -> None:
        player = await self.player_manager.get_or_create_player(ctx)

        if not player.current:
            embed = self.embed_generator.create_error_embed("No Track", "No track is currently playing")
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
            embed = self.embed_generator.create_error_embed("Invalid Position", "Seek position is out of track bounds")
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

        embed = self.embed_generator.create_success_embed("Seeked", f"Seeked to **{pos_str}**")
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="autoplay")
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

        embed = self.embed_generator.create_success_embed(
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
            embed = self.embed_generator.create_error_embed("No Track", "Need a track playing to refresh autoplay")
            await ctx.send(embed=embed)
            return

        await player.refresh_auto_queue()

        embed = self.embed_generator.create_success_embed("Autoplay Refreshed", "Autoplay queue has been refreshed")
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
            embed = self.embed_generator.create_success_embed(
                "Auto-Disconnect Disabled",
                "Auto-disconnect has been disabled",
            )
        else:
            player.set_auto_disconnect(True, timeout)
            embed = self.embed_generator.create_success_embed(
                "Auto-Disconnect Set",
                f"Auto-disconnect timeout set to **{timeout} seconds**",
            )
        await ctx.send(embed=embed)

    @auto_disconnect.command(name="toggle")
    @app_commands.guild_only()
    async def toggle_auto_disconnect(self, ctx: commands.Context[Nameless]) -> None:
        player = await self.player_manager.get_or_create_player(ctx)
        player.set_auto_disconnect(not player.is_auto_disconnect_enabled)
        embed = self.embed_generator.create_success_embed(
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
    autostart_lavalink = False
    autoupdate_lavalink = False

    lavalinks = nameless_config.lavalinks
    for node in lavalinks:
        if node.auto_start:
            autostart_lavalink = True
            autoupdate_lavalink = node.auto_update
            break
    else:
        default_node = LavalinkNode(
            host="localhost",
            port=18233,
            password="youshallnotpass",
            auto_start=True,
            auto_update=True,
            identifier="default-node",
        )
        lavalinks.append(default_node)
        logging.warning("No Lavalink nodes configured. Added default node.")
        autostart_lavalink = True
        autoupdate_lavalink = True

    if autostart_lavalink:
        try:
            await lavalink.main(bot.loop, autoupdate_lavalink)
        except ImportError:
            logging.warning("Could not import lavalink module. Lavalink auto-start disabled.")
        except Exception as e:
            logging.error("Failed to start lavalink: %s", e)

    await bot.add_cog(MusicCommands(bot))
    logging.info("Enhanced music commands loaded successfully!")


async def teardown(bot: Nameless):
    lavalinks = nameless_config.lavalinks
    for node in lavalinks:
        if node.auto_start:
            try:
                logging.info("Stopping Lavalink node...")
                await lavalink.stop()
            except Exception as e:
                logging.error("Error stopping lavalink: %s", e, exc_info=True)
            break

    await bot.remove_cog("music")
    logging.info("Music commands unloaded!")
