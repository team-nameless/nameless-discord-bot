from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, final

import discord
import pomice
from discord import app_commands
from discord.ext import commands

from nameless.config import nameless_config
from nameless.custom.ui import NamelessPaginatedView

from .cache import TrackCache
from .embeds import EmbedGenerator
from .exceptions import (
    AutoplayDisabledError,
    EmptyQueueError,
    InvalidPositionError,
    InvalidVolumeError,
    NoTracksFoundError,
    TrackNotSeekableError,
)
from .player import CustomPlayer, lavalink
from .player_manager import PlayerManager
from .track_selector import TrackSelector
from .views import MusicControlView

if TYPE_CHECKING:
    from nameless.config import LavalinkNode
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
        "player_manager",
        "embed_generator",
        "track_selector",
        "cache",
        "config",
    )

    def __init__(self, bot: Nameless):
        self.bot = bot
        self.is_ready = asyncio.Event()

        self.player_manager = PlayerManager(bot)
        self.embed_generator = EmbedGenerator()
        self.track_selector = TrackSelector()
        self.cache = TrackCache()

        self.pomice = pomice.NodePool()
        self._connect_task = self.bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        logging.info("Waiting for Discord connection before connecting to Lavalink...")
        await self.bot.wait_until_ready()
        logging.info("Discord ready. Connecting to Lavalink nodes...")

        for node in nameless_config.get("lavalinks", []):
            try:
                _node = await self.pomice.create_node(
                    bot=self.bot,
                    host=node["host"],
                    port=node["port"],
                    password=node["password"],
                    identifier=node.get("identifier"),
                    secure=node.get("secure", False),
                )
                logging.info("Connected to Lavalink node: %s", _node._identifier)  # type: ignore
            except Exception as e:
                logging.error("Failed to connect to node %s: %s", node.get("identifier", "unknown"), e)

        self.is_ready.set()
        if self._connect_task:
            self._connect_task = None

    @commands.Cog.listener()
    async def on_pomice_track_start(self, player: CustomPlayer, track: pomice.Track):
        if not player.guild:
            logging.warning("Player guild is None - bot may have been kicked")
            return

        if not player.play_now_allowed and player.queue.loop_mode != pomice.LoopMode.QUEUE:
            return

        if self.bot.user:
            embed = self.embed_generator.create_now_playing_embed(player, track, self.bot.user)
            view = MusicControlView(player)
            await player.send_to_trigger(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: CustomPlayer):
        await player.send_to_trigger("🔇 I've been inactive for a while. Goodbye!")
        await player.disconnect()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, _: discord.VoiceState, after: discord.VoiceState):
        if self.bot.user and member.id == self.bot.user.id and not after.deaf:
            await member.edit(deafen=True)

    async def _search_tracks(
        self, query: str, source: str, player: CustomPlayer
    ) -> list[pomice.Track] | pomice.Playlist | None:
        cached_result = self.cache.get(query, source)
        if cached_result:
            return cached_result

        search_type = SOURCE_MAPPING.get(source, pomice.SearchType.ytsearch)
        results = await player.get_tracks(query, search_type=search_type)  # type: ignore

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
            queue_list = list(player.queue._queue)  # type: ignore
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

        try:
            player = await self.player_manager.connect_to_voice(ctx, channel)
            if player and ctx.guild:
                embed = self.embed_generator.create_success_embed(
                    "Connected", f"Connected to **{player.channel.name}**"
                )
                view = MusicControlView(player)
                await ctx.send(embed=embed, view=view)
            else:
                raise commands.CommandError("Failed to connect to voice channel")
        except Exception as e:
            embed = self.embed_generator.create_error_embed("Connection Failed", str(e))
            await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["dc", "leave"])
    @app_commands.guild_only()
    async def disconnect(self, ctx: commands.Context[Nameless]) -> None:
        try:
            success = await self.player_manager.disconnect_player(ctx)
            if success:
                embed = self.embed_generator.create_success_embed(
                    "Disconnected", "Successfully disconnected from voice channel"
                )
            else:
                embed = self.embed_generator.create_error_embed("Not Connected", "I'm not connected to a voice channel")
            await ctx.send(embed=embed)
        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)

    class PlayFlags(commands.FlagConverter):
        position: int = commands.flag(default=0, description="Position in queue (0 = end)")
        source: str = commands.flag(default="youtube", description="Music source")
        shuffle: bool = commands.flag(default=False, description="Shuffle tracks before adding")

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

        try:
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

            added_count = await self._add_tracks_to_queue(player, tracks, position)

            if not player.is_playing and player.queue:
                await player.play(player.queue.get())

            view = MusicControlView(player)
            await ctx.send(embed=embed, view=view)

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Playback Error", str(e))
            await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def pause(self, ctx: commands.Context[Nameless]) -> None:
        try:
            player = await self.player_manager.get_or_create_player(ctx)

            if player.is_paused:
                embed = self.embed_generator.create_info_embed("Already Paused", "The player is already paused")
            else:
                await player.set_pause(True)
                embed = self.embed_generator.create_success_embed("Paused", "Playback has been paused")

            view = MusicControlView(player)
            await ctx.send(embed=embed, view=view)

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def resume(self, ctx: commands.Context[Nameless]) -> None:
        try:
            player = await self.player_manager.get_or_create_player(ctx)

            if not player.is_paused:
                embed = self.embed_generator.create_info_embed("Already Playing", "The player is already playing")
            else:
                await player.set_pause(False)
                embed = self.embed_generator.create_success_embed("Resumed", "Playback has been resumed")

            view = MusicControlView(player)
            await ctx.send(embed=embed, view=view)

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def skip(self, ctx: commands.Context[Nameless]) -> None:
        try:
            player = await self.player_manager.get_or_create_player(ctx)

            if not player.current:
                raise EmptyQueueError()

            current_track = player.current
            await player.stop()

            embed = self.embed_generator.create_success_embed("Skipped", f"Skipped **{current_track.title}**")
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def stop(self, ctx: commands.Context[Nameless]) -> None:
        try:
            player = await self.player_manager.get_or_create_player(ctx)

            await player.stop()
            player.queue.clear()

            embed = self.embed_generator.create_success_embed("Stopped", "Playback stopped and queue cleared")
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["q"])
    @app_commands.guild_only()
    async def queue(self, ctx: commands.Context[Nameless]) -> None:
        try:
            player = await self.player_manager.get_or_create_player(ctx)

            if not player.queue and not player.auto_queue:
                raise EmptyQueueError()

            all_tracks = list(player.queue._queue)  # type: ignore
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

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["np", "nowplaying", "playing"])
    @app_commands.guild_only()
    async def current(self, ctx: commands.Context[Nameless]) -> None:
        try:
            player = await self.player_manager.get_or_create_player(ctx)

            if not player.current:
                embed = self.embed_generator.create_info_embed("Nothing Playing", "No track is currently playing")
                await ctx.send(embed=embed)
                return

            embed = self.embed_generator.create_now_playing_embed(player, player.current, ctx.author)
            view = MusicControlView(player)
            await ctx.send(embed=embed, view=view)

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["random"])
    @app_commands.guild_only()
    async def shuffle(self, ctx: commands.Context[Nameless]) -> None:
        try:
            player = await self.player_manager.get_or_create_player(ctx)

            if not player.queue:
                raise EmptyQueueError()

            player.queue.shuffle()
            embed = self.embed_generator.create_success_embed("Shuffled", f"Shuffled {len(player.queue)} tracks")
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    @app_commands.describe(volume="Volume level (0-200)")
    async def volume(self, ctx: commands.Context[Nameless], volume: int) -> None:
        try:
            if not 0 <= volume <= 200:
                raise InvalidVolumeError(volume)

            player = await self.player_manager.get_or_create_player(ctx)
            await player.set_volume(volume)

            embed = self.embed_generator.create_success_embed("Volume Changed", f"Volume set to **{volume}%**")
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    @app_commands.describe(index="Track number to remove (1-based)")
    async def remove(self, ctx: commands.Context[Nameless], index: int) -> None:
        try:
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

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def clear(self, ctx: commands.Context[Nameless]) -> None:
        try:
            player = await self.player_manager.get_or_create_player(ctx)

            if not player.queue:
                raise EmptyQueueError()

            track_count = len(player.queue)
            player.queue.clear()

            embed = self.embed_generator.create_success_embed(
                "Queue Cleared", f"Removed {track_count} tracks from queue"
            )
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)

    class SeekFlags(commands.FlagConverter):
        hours: int = commands.flag(default=0, description="Hours")
        minutes: int = commands.flag(default=0, description="Minutes")
        seconds: int = commands.flag(default=0, description="Seconds")
        percent: float = commands.flag(default=0.0, description="Percentage of track")

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def seek(
        self, ctx: commands.Context[Nameless], hours: int = 0, minutes: int = 0, seconds: int = 0, percent: float = 0.0
    ) -> None:
        try:
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
                embed = self.embed_generator.create_error_embed(
                    "Invalid Position", "Seek position is out of track bounds"
                )
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

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)

    @commands.hybrid_group(name="autoplay")
    async def autoplay(self, ctx: commands.Context[Nameless]):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @autoplay.command(name="enable")
    @app_commands.guild_only()
    async def autoplay_enable(self, ctx: commands.Context[Nameless]) -> None:
        try:
            player = await self.player_manager.get_or_create_player(ctx)

            if player.is_autoplaying:
                embed = self.embed_generator.create_info_embed("Already Enabled", "Autoplay is already enabled")
                await ctx.send(embed=embed)
                return

            if not player.current:
                embed = self.embed_generator.create_error_embed("No Track", "Need a track playing to enable autoplay")
                await ctx.send(embed=embed)
                return

            await player.refresh_auto_queue()
            player.is_autoplaying = True

            embed = self.embed_generator.create_success_embed("Autoplay Enabled", "Autoplay mode has been enabled")
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)

    @autoplay.command(name="disable")
    @app_commands.guild_only()
    async def autoplay_disable(self, ctx: commands.Context[Nameless]) -> None:
        try:
            player = await self.player_manager.get_or_create_player(ctx)

            if not player.is_autoplaying:
                embed = self.embed_generator.create_info_embed("Already Disabled", "Autoplay is already disabled")
                await ctx.send(embed=embed)
                return

            player.is_autoplaying = False
            player.clear_auto_queue()

            embed = self.embed_generator.create_success_embed("Autoplay Disabled", "Autoplay mode has been disabled")
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)

    @autoplay.command(name="refresh")
    @app_commands.guild_only()
    async def autoplay_refresh(self, ctx: commands.Context[Nameless]) -> None:
        await ctx.defer()

        try:
            player = await self.player_manager.get_or_create_player(ctx)

            if not player.is_autoplaying:
                raise AutoplayDisabledError()

            if not player.current:
                embed = self.embed_generator.create_error_embed("No Track", "Need a track playing to refresh autoplay")
                await ctx.send(embed=embed)
                return

            await player.refresh_auto_queue()

            embed = self.embed_generator.create_success_embed("Autoplay Refreshed", "Autoplay queue has been refreshed")
            await ctx.send(embed=embed)

        except Exception as e:
            embed = self.embed_generator.create_error_embed("Error", str(e))
            await ctx.send(embed=embed)


async def setup(bot: Nameless):
    autostart_lavalink = False
    autoupdate_lavalink = False

    lavalinks = nameless_config.setdefault("lavalinks", [])
    for node in lavalinks:
        if node.get("auto_start", False):
            autostart_lavalink = True
            autoupdate_lavalink = node.get("auto_update", False)
            break
    else:
        default_node: LavalinkNode = {
            "host": "localhost",
            "port": 8233,
            "password": "youshallnotpass",
            "auto_start": True,
            "auto_update": True,
            "identifier": "default-node",
        }
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
    lavalinks = nameless_config.get("lavalinks", [])
    for node in lavalinks:
        if node.get("auto_start", False):
            try:
                logging.info("Stopping Lavalink node...")
                await lavalink.stop()
            except ImportError:
                logging.warning("Could not import lavalink stop function")
            except Exception as e:
                logging.error("Error stopping lavalink: %s", e)
            break

    await bot.remove_cog("music")
    logging.info("Enhanced music commands unloaded!")
