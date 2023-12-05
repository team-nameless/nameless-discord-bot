import asyncio
import datetime  # noqa: F401
import logging
from typing import Any, Optional, Union, cast  # noqa: F401

import discord
import wavelink
from discord import ClientException, app_commands
from discord.app_commands import AppCommandError, Choice, Range  # noqa: F401
from discord.ext import commands
from discord.utils import escape_markdown
from reactionmenu import ViewButton, ViewMenu
from wavelink import Queue, QueueMode, TrackStartEventPayload  # noqa: F401

from nameless import Nameless
from nameless.cogs.checks.MusicCogCheck import MusicCogCheck
from nameless.commons import Utility  # noqa: F401
from nameless.customs.voice_backends import BaseVoiceBackend
from nameless.database import CRUD  # noqa: F401
from nameless.ui_kit import NamelessTrackDropdown, NamelessVoteMenu
from NamelessConfig import NamelessConfig

__all__ = ["MusicCog"]
SOURCE_MAPPING = {
    "youtube": wavelink.TrackSource.YouTube,
    "soundcloud": wavelink.TrackSource.SoundCloud,
    "ytmusic": wavelink.TrackSource.YouTubeMusic,
}


class MusicCog(commands.GroupCog, name="music"):
    def __init__(self, bot: Nameless):
        self.bot = bot
        self.is_ready = asyncio.Event()

        bot.loop.create_task(self.connect_nodes())
        self.autoleave_waiter_task = {}

    @staticmethod
    def remove_artist_suffix(name: str) -> str:
        if not name:
            return "N/A"
        return name.removesuffix(" - Topic")

    async def connect_nodes(self):
        await self.bot.wait_until_ready()

        nodes = [
            wavelink.Node(
                uri=f"{'https' if node.secure else 'http'}://{node.host}:{node.port}",
                password=node.password,
            )
            for node in NamelessConfig.MUSIC.NODES
        ]

        await wavelink.Pool.connect(client=self.bot, nodes=nodes, cache_capacity=100)

        if not self.is_ready.is_set():
            self.is_ready.set()

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        node = payload.node
        logging.info("Node {%s} (%s) is ready!", node.identifier or "N/A", node.uri)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: TrackStartEventPayload):
        player: BaseVoiceBackend.Player = cast(BaseVoiceBackend.Player, payload.player)
        track = payload.track

        chn = player.guild.get_channel(player.trigger_channel_id)
        dbg = CRUD.get_or_create_guild_record(chn.guild)
        if chn is not None and player.play_now_allowed and player.should_send_play_now:
            embed = self.generate_embed_np_from_playable(player, track, self.bot.user, dbg)  # type: ignore
            await chn.send(embed=embed)  # type: ignore

            # build_title = track.title if not track.uri else f"[{track.title}](<{track.uri}>)"
            # build_artist = self.remove_artist_suffix(track.author)
            # await chn.send(f"Playing: {build_title} by **{build_artist}**")  # type: ignore

    @staticmethod
    def generate_embeds_from_playable(
        tracks: wavelink.Queue | list[wavelink.Playable] | wavelink.Playlist,
        title: str = "Tracks currently in queue",
    ) -> list[discord.Embed]:
        txt = ""
        embeds: list[discord.Embed] = []

        for idx, track in enumerate(tracks, start=1):
            upcoming = (
                f"{idx} - "
                f"[{escape_markdown(track.title)} by {escape_markdown(track.author)}]"
                f"({track.uri or 'N/A'})\n"
            )

            if len(txt) + len(upcoming) > 2048:
                eb = discord.Embed(
                    title=title,
                    color=discord.Color.orange(),
                    description=txt,
                )
                embeds.append(eb)
                txt = upcoming
            else:
                txt += upcoming

        embeds.append(
            discord.Embed(
                title=title,
                color=discord.Color.orange(),
                description=txt,
            )
        )

        return embeds

    @staticmethod
    def generate_embed_np_from_playable(
        player: BaseVoiceBackend.Player,
        track: wavelink.Playable,
        user: discord.User | discord.Member,
        dbg,
    ) -> discord.Embed:
        def convert_time(milli):
            td = str(datetime.timedelta(milliseconds=milli)).split(".")[0].split(":")
            after_td = []
            for t in td:
                if t == "0":
                    continue
                after_td.append(t.zfill(2))

            return ":".join(after_td)

        # thumbnail_url: str = await track. if isinstance(track, wavelink.TrackSource.YouTube) else ""
        thumbnail_url: str = track.artwork if track.artwork else ""
        is_stream = track.is_stream

        def add_icon():
            icon = "⏸️" if player.paused else "▶️"
            if player.queue.mode.value == wavelink.QueueMode.loop:
                icon += "🔂"
            elif player.queue.mode.value == wavelink.QueueMode.loop_all:
                icon += "🔁"
            return icon

        embed = (
            discord.Embed(timestamp=datetime.datetime.now(), color=discord.Color.orange())
            .set_author(
                name=f"{add_icon()} Now playing {'stream' if is_stream else 'track'}",
                icon_url=user.display_avatar.url,
            )
            .add_field(
                name="Title",
                value=escape_markdown(track.title),
            )
            .add_field(
                name="Author",
                value=escape_markdown(track.author) if track.author else "N/A",
            )
            .add_field(
                name="Source",
                value=f"[{escape_markdown(str.title(track.source))}]({escape_markdown(track.uri)})"
                if track.uri
                else "N/A",
                inline=False,
            )
            .add_field(
                name="Playtime" if is_stream else "Position",
                value=str(
                    discord.utils.utcnow().replace(tzinfo=None) - dbg.radio_start_time
                    if is_stream
                    else f"{convert_time(player.position)}/{convert_time(track.length)}"
                ),
            )
            # .add_field(name="Looping", value="This is a stream" if is_stream else vc.queue.loop)
            # .add_field(name="Paused", value=vc.is_paused())
            .set_thumbnail(url=thumbnail_url)
        )

        if player.queue.mode != wavelink.QueueMode.loop and not track.is_stream and bool(player.queue):
            next_tr = player.queue._queue[0]
            embed.add_field(
                name="Next track",
                value=f"[{escape_markdown(next_tr.title) if next_tr.title else 'Unknown title'} "
                f"by {escape_markdown(next_tr.author)}]"
                f"({next_tr.uri or 'N/A'})",
            )

        return embed

    @staticmethod
    async def show_paginated_tracks(interaction: discord.Interaction, embeds: list[discord.Embed]):
        view_menu = ViewMenu(interaction, menu_type=ViewMenu.TypeEmbed)
        view_menu.add_pages(embeds)

        view_menu.add_button(ViewButton.back())
        view_menu.add_button(ViewButton.end_session())
        view_menu.add_button(ViewButton.next())

        await view_menu.start()

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_in_voice)
    async def connect(self, interaction: discord.Interaction):
        """
        Connect to your current voice channel.
        """
        await interaction.response.defer()

        # A rare case where LavaLink node is slow to connect and causes an error
        if not self.is_ready.is_set():
            await interaction.followup.send("Waiting for the bot to connect to all Lavalink nodes...")
            await self.is_ready.wait()

        try:
            await interaction.user.voice.channel.connect(cls=BaseVoiceBackend.Player, self_deaf=True)  # type: ignore
            await interaction.followup.send("Connected to your voice channel")

            player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore
            player.trigger_channel_id = interaction.channel.id  # type: ignore

        except ClientException:
            await interaction.followup.send("Already connected")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.bot_in_voice)
    async def disconnect(self, interaction: discord.Interaction):
        """Disconnect from my current voice channel"""
        await interaction.response.defer()

        player: BaseVoiceBackend.Player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore
        if not player:
            await interaction.followup.send("I am not connected to a voice channel")
            return

        try:
            await player.disconnect(force=True)
            player.cleanup()
            await interaction.followup.send("Disconnected from my own voice channel")
        except AttributeError:
            await interaction.followup.send("I am already disconnected!")

    async def pick_track_from_results(
        self,
        interaction: discord.Interaction,
        tracks: list[wavelink.Playable],
    ) -> list[wavelink.Playable]:
        if len(tracks) == 1:
            return tracks

        view = discord.ui.View().add_item(NamelessTrackDropdown([track for track in tracks if not track.is_stream]))
        m: discord.WebhookMessage = await interaction.followup.send("Tracks found", view=view)  # pyright: ignore

        if await view.wait():
            await m.edit(content="Timed out! Please try again!", view=None)
            return []

        drop: discord.ui.Item[discord.ui.View] | NamelessTrackDropdown = view.children[0]
        vals = drop.values  # type: ignore

        if not vals:
            await m.edit(content="No tracks selected!", view=None)
            return []

        if "Nope" in vals:
            await m.edit(content="All choices cleared", view=None)
            return []

        await m.edit(content=f"Added {len(vals)} tracks into the queue", view=None)

        pick_list: list[wavelink.Playable] = [tracks[int(val)] for val in vals]
        return pick_list

    async def _play(self, interaction: discord.Interaction, search: str, source: str = "youtube"):
        """Start playing the queue."""
        await interaction.response.defer()

        player: BaseVoiceBackend.Player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore
        play_after = not player.playing and not bool(player.queue) and player.auto_play_queue
        show_embed = None

        tracks: wavelink.Search = await wavelink.Playable.search(search)
        if not tracks:
            await interaction.followup.send("No results found")
            return

        if isinstance(tracks, wavelink.Playlist):
            # tracks is a playlist...
            added: int = await player.queue.put_wait(tracks)
            show_embed = tracks
            await interaction.followup.send(f"Added the playlist **`{tracks.name}`** ({added} songs) to the queue.")
        else:
            soon_added = await self.pick_track_from_results(interaction, tracks)
            if not soon_added:
                return

            await player.queue.put_wait(soon_added)
            show_embed = soon_added

        if show_embed:
            embeds = self.generate_embeds_from_playable(show_embed, title="List of tracks added to the queue")
            self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds))

        if play_after:
            await player.play(player.queue.get())

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(search="Search query", source="Source to search")
    @app_commands.choices(source=[Choice(name=k, value=k) for k in SOURCE_MAPPING])
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def play(self, interaction: discord.Interaction, search: str, source: str = "youtube"):
        """Start playing the queue."""
        await self._play(interaction, search, source)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_is_playing_something)
    async def pause(self, interaction: discord.Interaction):
        """Pause current track"""
        await interaction.response.defer()

        player: BaseVoiceBackend.Player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore

        if player.paused:
            await interaction.followup.send("Already paused")
            return

        await player.pause(True)
        await interaction.followup.send("Paused")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_is_silent)
    async def resume(self, interaction: discord.Interaction):
        """Resume current playback, if paused"""
        await interaction.response.defer()

        player: BaseVoiceBackend.Player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore

        if not player.paused:
            await interaction.followup.send("Already resuming")
            return

        await player.pause(False)
        await interaction.followup.send("Resumed")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(show_next_track="Whether the next track should be shown (useless in looping)")
    @app_commands.check(MusicCogCheck.bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_is_playing_something)
    async def now_playing(self, interaction: discord.Interaction, show_next_track: bool = True):
        """Check now playing song"""
        await interaction.response.defer()

        player: wavelink.Player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore
        track: wavelink.Playable | None = player.current
        if not track:
            await interaction.response.send_message("Not playing anything")
            return

        dbg = CRUD.get_or_create_guild_record(interaction.guild)
        embed = self.generate_embed_np_from_playable(player, track, interaction.user, dbg)
        await interaction.followup.send(embed=embed)

    queue = app_commands.Group(name="queue", description="Commands related to queue management.")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def start(self, interaction: discord.Interaction):
        """Start playing the queue"""
        await interaction.response.defer()

        player: BaseVoiceBackend.Player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore
        if not bool(player.queue):
            await interaction.followup.send("Nothing in the queue")
            return

        await player.play(player.queue.get())

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(search="Search query", source="Source to search")
    @app_commands.choices(source=[Choice(name=k, value=k) for k in SOURCE_MAPPING])
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def add(self, interaction: discord.Interaction, search: str, source: str = "youtube"):
        "Alias for `play`"
        await self._play(interaction, search, source)

    @queue.command()
    @app_commands.guild_only()
    async def view(self, interaction: discord.Interaction):
        """View current queue"""
        await interaction.response.defer()

        player: BaseVoiceBackend.Player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore

        if not player.queue:
            await interaction.followup.send("Wow, such empty queue. Mind adding some cool tracks?")
            return

        embeds = self.generate_embeds_from_playable(player.queue)
        self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds))

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(index="The index to remove")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def delete(self, interaction: discord.Interaction, index: Range[int, 1]):
        """Remove track from queue"""
        await interaction.response.defer()

        player: BaseVoiceBackend.Player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore

        q = player.queue._queue
        index = index - 1

        if index < 0 or index >= len(q):
            await interaction.followup.send("Oops!")
            return

        try:
            deleted_track = q[index]
            await player.queue.delete(index)
            await interaction.followup.send(
                f"Deleted track at position #{index}: **{deleted_track.title}** from **{deleted_track.author}**"
            )
        except IndexError:
            await interaction.followup.send("Oops!")

    # TODO: rewrite for perfomance
    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(before="Old position", after="New position")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def move(self, interaction: discord.Interaction, before: Range[int, 1], after: Range[int, 1]):
        """Move track to new position"""
        await interaction.response.defer()

        player: BaseVoiceBackend.Player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore

        int_queue = player.queue._queue
        queue_length = len(int_queue)

        if not (before != after and 1 <= before <= queue_length and 1 <= after <= queue_length):
            await interaction.followup.send(f"Invalid position(s): `{before} -> {after}`")
            return

        temp = int_queue[before - 1]
        del int_queue[before - 1]
        int_queue.insert(after - 1, temp)

        await interaction.followup.send(f"Moved track #{before} to #{after}")

    # TODO: rewrite for perfomance
    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(pos="Current position", diff="Relative difference")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def move_relative(self, interaction: discord.Interaction, pos: Range[int, 1], diff: int):
        """Move track to new position using relative difference"""
        await interaction.response.defer()

        player: BaseVoiceBackend.Player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore

        int_queue = player.queue._queue
        queue_length = len(int_queue)

        before = pos
        after = pos + diff

        if not (before != after and 1 <= before <= queue_length and 1 <= after <= queue_length):
            await interaction.followup.send(f"Invalid position(s): `{before} -> {after}`")
            return

        temp = int_queue[before - 1]
        del int_queue[before - 1]
        int_queue.insert(after - 1, temp)

        await interaction.followup.send(f"Moved track #{before} to #{after}")

    # TODO: rewrite for perfomance
    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    @app_commands.describe(pos1="Position of first track", pos2="Position of second track")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def swap(self, interaction: discord.Interaction, pos1: Range[int, 1], pos2: Range[int, 1]):
        """Swap two tracks."""
        await interaction.response.defer()

        player: BaseVoiceBackend.Player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore

        q = player.queue._queue
        q_length = len(q)

        if not (1 <= pos1 <= q_length and 1 <= pos2 <= q_length):
            await interaction.followup.send(f"Invalid position(s): ({pos1}, {pos2})")
            return

        q[pos1 - 1], q[pos2 - 1] = (q[pos2 - 1], q[pos1 - 1])

        await interaction.followup.send(f"Swapped track #{pos1} and #{pos2}")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shuffle(self, interaction: discord.Interaction):
        """Shuffle the queue"""
        await interaction.response.defer()

        player: BaseVoiceBackend.Player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore
        player.queue.shuffle()
        await interaction.followup.send("Shuffled the queue")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def clear(self, interaction: discord.Interaction):
        """Clear the queue, using vote system."""
        await interaction.response.defer()

        player: BaseVoiceBackend.Player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore

        async def clear_action():
            player.queue.clear()
            await interaction.followup.send(content="Cleared the queue")

        if len(player.client.users) == 2:
            await clear_action()
            return

        if await NamelessVoteMenu(interaction, player, "clear", "queue").start():
            await clear_action()
            return

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def force_clear(self, interaction: discord.Interaction):
        """Force clear the queue, guild managers only."""
        await interaction.response.defer()

        player: BaseVoiceBackend.Player = cast(BaseVoiceBackend.Player, interaction.guild.voice_client)  # type: ignore
        player.queue.clear()
        await interaction.followup.send("Cleared the queue")


async def setup(bot: Nameless):
    if NamelessConfig.MUSIC.NODES:
        await bot.add_cog(MusicCog(bot))
        logging.info("%s cog added!", __name__)
    else:
        raise commands.ExtensionFailed(__name__, ValueError("Lavalink options are not properly provided"))


async def teardown(bot: Nameless):
    await bot.remove_cog("MusicLavalinkCog")
    logging.warning("%s cog removed!", __name__)
