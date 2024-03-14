import asyncio
import datetime
import logging
import random
from typing import cast

import discord
import wavelink
from cachetools.func import ttl_cache
from discord import ClientException, app_commands
from discord.app_commands import Choice, Range
from discord.ext import commands
from discord.utils import escape_markdown
from reactionmenu import ViewButton, ViewMenu
from wavelink import AutoPlayMode, QueueMode

from nameless import Nameless
from nameless.cogs.checks.MusicCogCheck import MusicCogCheck
from nameless.customs import NamelessPlayer, QueueAction
from nameless.customs.ui_kit import NamelessTrackDropdown, NamelessVoteMenu
from nameless.database import CRUD
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

        self.nodes = [
            wavelink.Node(
                uri=f"{'https' if node.secure else 'http'}://{node.host}:{node.port}",
                password=node.password,
                inactive_player_timeout=NamelessConfig.MUSIC.AUTOLEAVE_TIME,
                client=self.bot,
            )
            for node in NamelessConfig.MUSIC.NODES
        ]

        self.bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        """Connect to lavalink nodes."""
        await self.bot.wait_until_ready()
        await wavelink.Pool.connect(client=self.bot, nodes=self.nodes, cache_capacity=100)

    @staticmethod
    @ttl_cache(ttl=300)
    def resolve_artist_name(name: str) -> str:
        if not name:
            return "N/A"
        name = escape_markdown(name, as_needed=True)
        return name.removesuffix(" - Topic")

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        logging.info("Node {%s} (%s) is ready!", payload.node.identifier, payload.node.uri)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player: NamelessPlayer = cast(NamelessPlayer, payload.player)
        original: wavelink.Playable | None = payload.original
        track = payload.track

        if not player.guild:
            logging.warning("Player is not connected. Or we have been banned from the guild!")
            return

        chn = player.guild.get_channel(player.trigger_channel_id)
        can_send = (
            chn is not None
            and player.play_now_allowed
            and player.should_send_play_now
            and player.queue.mode is not QueueMode.loop
        )

        if not can_send:
            return

        dbg = CRUD.get_or_create_guild_record(player.guild)
        if chn is not None and player.play_now_allowed and player.should_send_play_now:
            embed = self.generate_embed_from_track(
                player,
                track,
                self.bot.user,
                dbg,
                original is not None and original.recommended,
            )
            await chn.send(embed=embed)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player):
        await player.channel.send("I have been inactive for a while. Goodbye!")
        await player.disconnect()

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.id == self.bot.user.id and not after.deaf:
            await member.edit(deafen=True)

    def generate_embeds_from_tracks(
        self,
        tracks: wavelink.Queue | list[wavelink.Playable] | wavelink.Playlist,
        embed_title: str = "Tracks currently in queue",
    ) -> list[discord.Embed]:
        """Generate embeds from supported track list types."""
        txt = ""
        embeds: list[discord.Embed] = []
        track_list: list[wavelink.Playable] = []

        if isinstance(tracks, wavelink.Queue):
            track_list = tracks.copy()._items

        if isinstance(tracks, wavelink.Playlist):
            track_list = tracks.tracks

        for i, track in enumerate(track_list, start=1):
            upcoming = (
                f"{i} - " f"[{track.title} by {self.resolve_artist_name(track.author)}]" f"({track.uri or 'N/A'})\n"
            )

            if len(txt) + len(upcoming) > 2048:
                eb = discord.Embed(
                    title=embed_title,
                    color=discord.Color.orange(),
                    description=txt,
                )
                embeds.append(eb)
                txt = upcoming
            else:
                txt += upcoming

        embeds.append(
            discord.Embed(
                title=embed_title,
                color=discord.Color.orange(),
                description=txt,
            )
        )

        return embeds

    def generate_embed_from_track(
        self,
        player: NamelessPlayer,
        track: wavelink.Playable | None,
        user: discord.User | discord.Member | discord.ClientUser | None,
        dbg,
        is_recommended=False,
    ) -> discord.Embed:
        assert user is not None
        assert track is not None

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
            if player.queue.mode == QueueMode.loop:
                icon += "🔂"
            elif player.queue.mode == QueueMode.loop_all:
                icon += "🔁"
            return icon

        title = add_icon()
        title += "Autoplaying" if is_recommended else "Now playing"
        title += " track" if not is_stream else " stream"

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
                value=self.resolve_artist_name(track.author) if track.author else "N/A",
            )
            .add_field(
                name="Source",
                value=f"[{str.title(track.source)}]({track.uri})" if track.uri else "N/A",
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

        if player.queue.mode != QueueMode.loop and not track.is_stream and bool(player.queue):
            next_tr = player.queue[0]
            embed.add_field(
                name="Next track",
                value=f"[{escape_markdown(next_tr.title) if next_tr.title else 'Unknown title'} "
                f"by {self.resolve_artist_name(next_tr.author)}]"
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
        """Connect to your current voice channel."""
        await interaction.response.defer()

        try:
            await interaction.user.voice.channel.connect(cls=wavelink.Player, self_deaf=True)
            await interaction.followup.send("Connected to your voice channel")

            player = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore
            player.trigger_channel_id = interaction.channel.id  # type: ignore

        except ClientException:
            await interaction.followup.send("Already connected")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.bot_in_voice)
    async def disconnect(self, interaction: discord.Interaction):
        """Disconnect from my current voice channel."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore

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
        m: discord.WebhookMessage = await interaction.followup.send("Tracks found", view=view)  # type: ignore

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

        await m.delete()

        pick_list: list[wavelink.Playable] = [tracks[int(val)] for val in vals]
        return pick_list

    async def _play(
        self,
        interaction: discord.Interaction,
        query: str,
        source: str = "youtube",
        action: QueueAction = QueueAction.ADD,
        reverse: bool = False,
        shuffle: bool = False,
    ):
        """
        Add or insert a track or playlist in the player queue.

        Parameters:
        ----------
            interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
            query (str): The search query for the track or playlist.
            source (str, optional): The source of the track or playlist (default: "youtube").
            action (str, optional): The action to perform on the track or playlist (default: "add").
            reverse (bool, optional): Whether to reverse the order of the tracks (default: False).
            shuffle (bool, optional): Whether to shuffle the order of the tracks (default: False).

        Raises:
        ----------
            wavelink.LavalinkLoadException: If there is an error loading the track or playlist.

        """
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore
        should_play = not player.playing and not bool(player.queue) and player.auto_play_queue
        msg: str = ""

        async def add_to_queue(tracks: list[wavelink.Playable] | wavelink.Playlist) -> int:
            if reverse:
                if isinstance(tracks, wavelink.Playlist):
                    tracks = list(reversed(tracks))
                else:
                    tracks.reverse()

            if shuffle:
                random.shuffle(tracks if isinstance(tracks, list) else tracks.tracks)

            if action == QueueAction.ADD:
                return await player.queue.put_wait(tracks)
            elif action == QueueAction.INSERT:
                return await player.queue.insert_wait(tracks)
            return 0

        try:
            tracks: wavelink.Search = await wavelink.Playable.search(query, source=SOURCE_MAPPING[source])
        except wavelink.LavalinkLoadException as err:
            logging.error(err)
            await interaction.followup.send("Lavalink error occurred. Please contact the bot owner.")
            return

        if not tracks:
            await interaction.followup.send("No results found")
            return

        if isinstance(tracks, wavelink.Playlist):
            added = await add_to_queue(tracks)
            soon_added = tracks
            msg = f"Added the playlist **`{tracks.name}`** ({added} songs) to the queue."
        else:
            soon_added = await self.pick_track_from_results(interaction, tracks)

            if not soon_added:
                return

            added = await add_to_queue(soon_added)
            msg = f"{action.name.title()}ed {added} {'songs' if added > 1 else 'song'} to the queue"

        if soon_added:
            embeds = self.generate_embeds_from_tracks(soon_added, embed_title=msg)
            self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds))

        if player.current and player.current.is_stream:
            should_play = True
            await player.stop(force=True)

        if should_play:
            await player.play(player.queue.get(), add_history=False)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_is_playing_something)
    async def pause(self, interaction: discord.Interaction):
        """Pause current playback."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore

        if player.paused:
            await interaction.followup.send("Already paused.")
            return

        await player.pause(True)
        await interaction.followup.send("Paused.")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_is_silent)
    async def resume(self, interaction: discord.Interaction):
        """Resume current playback."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore

        if not player.paused:
            await interaction.followup.send("Already playing.")
            return

        await player.pause(False)
        await interaction.followup.send("Resuming.")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def stop(self, interaction: discord.Interaction):
        """Stop playback (or terminate the session, idk)."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore

        if not player.playing:
            await interaction.followup.send("Not playing anything.")
            return

        player.autoplay = AutoPlayMode.disabled
        await player.stop()

        await interaction.followup.send("Stopped")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_is_playing_something)
    async def now_playing(self, interaction: discord.Interaction):
        """Check now playing song"""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore
        track: wavelink.Playable | None = player.current

        if not track:
            await interaction.response.send_message("I am not playing anything.")
            return

        dbg = CRUD.get_or_create_guild_record(interaction.guild)
        embed = self.generate_embed_from_track(player, track, interaction.user, dbg)
        await interaction.followup.send(embed=embed)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def skip(self, interaction: discord.Interaction):
        """Skip a song. Even if it is looping."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)
        track: wavelink.Playable | None = player.current

        if (
            # The invoker has the MANAGE_GUILD
            interaction.user.guild_permissions.manage_guild
            or
            # Only you & the bot
            len(player.client.users) == 2
            or
            # The voting passes.
            await NamelessVoteMenu(interaction, player, "skip", track.title).start()
        ):
            await player.skip()
            await interaction.followup.send(content="Skipping current track.")

            if bool(player.queue):
                await interaction.followup.send("Next track should be played now.")
        else:
            await interaction.followup.send(content="Nah, I'd pass.")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(
        milliseconds="Milisecond component of position",
        seconds="Second component of position",
        minutes="Minute component of position",
        hours="Hour component of position",
        percent="Percentage of track, HAS THE HIGHEST OF PRECEDENCE.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def seek(
        self,
        interaction: discord.Interaction,
        # https://stackoverflow.com/a/35720280/9151833
        milliseconds: app_commands.Range[int, 0, 9999999] = 0,
        seconds: app_commands.Range[int, 0, 59] = 0,
        minutes: app_commands.Range[int, 0, 59] = 0,
        hours: app_commands.Range[int, 0] = 0,
        percent: app_commands.Range[float, 0, 100] = 0,
    ):
        """Seek to position in a track. Leave empty to seek to start of the track."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)
        track: wavelink.Playable | None = player.current

        if not track.is_seekable:
            await interaction.followup.send("This track is not seekable!")
            return

        if await NamelessVoteMenu(interaction, player, "seek", track.title).start():
            # In miliseconds.
            final_position = -1

            if percent:
                final_position = int(track.length * (percent / 100) / 100)
            else:
                total_seconds = hours * 3600 + minutes * 60 + seconds
                final_position = total_seconds * 1000 + milliseconds

            await player.seek(final_position)

            dbg = CRUD.get_or_create_guild_record(interaction.guild)
            embed = self.generate_embed_from_track(player, track, interaction.user, dbg)
            await interaction.followup.send(content="Seeked", embed=embed)

    queue = app_commands.Group(name="queue", description="Commands related to queue management.")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def start(self, interaction: discord.Interaction):
        """Start playing the queue."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore

        if not bool(player.queue):
            await interaction.followup.send("Nothing in the queue")
            return

        player.autoplay = AutoPlayMode.partial
        await player.play(player.queue.get())

        await interaction.followup.send("Started playing the queue")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(query="Search query", source="Source to search")
    @app_commands.choices(source=[Choice(name=k, value=k) for k in SOURCE_MAPPING])
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def add(self, interaction: discord.Interaction, query: str, source: str = "youtube"):
        """Alias for `play` command."""
        await self._play(interaction, query, source)

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(
        url="Playlist URL",
        position="Position to add the playlist, '-1' means at the end of queue",
        reverse="Process pending playlist in reversed order",
        shuffle="Process pending playlist in shuffled order",
    )
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def add_playlist(
        self,
        interaction: discord.Interaction,
        url: str,
        position: app_commands.Range[int, -1] = -1,
        reverse: bool = False,
        shuffle: bool = False,
    ):
        """Add playlist to the queue."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore

        await self._play(interaction, url, reverse=reverse, shuffle=shuffle)

    @queue.command()
    @app_commands.guild_only()
    async def view(self, interaction: discord.Interaction):
        """View current queue"""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore

        if not player.queue:
            await interaction.followup.send("Wow, such empty queue. Mind adding some cool tracks?")
            return

        embeds = self.generate_embeds_from_tracks(player.queue)
        self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds))

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def view_autoplay(self, interaction: discord.Interaction):
        """View current autoplay queue. Can be none if autoplay is 'disabled' or 'partial'."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore

        if player.autoplay != AutoPlayMode.enabled and not bool(player.auto_queue):
            await interaction.followup.send(
                "Seems like autoplay is disabled or autoplay queue is has not been populated yet."
            )
            return

        embeds = self.generate_embeds_from_tracks(player.auto_queue, embed_title="Autoplay queue")
        self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds))

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def repopulate_autoqueue(self, interaction: discord.Interaction):
        """Repopulate autoplay queue based on current song(s)."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore

        if player.autoplay != AutoPlayMode.enabled:
            await interaction.followup.send("Seems like autoplay is disabled.")
            return

        await player.repopulate_auto_queue()
        await interaction.followup.send("Repopulated autoplay queue!")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(index="The index to remove.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def delete(self, interaction: discord.Interaction, index: Range[int, 1]):
        """Remove track from queue"""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore

        if not 0 <= index <= player.queue.count:
            await interaction.followup.send("Oops! You picked the position beyond the queue.")
            return

        index = index - 1

        deleted_track = player.queue.get_at(index)
        player.queue.delete(index)

        await interaction.followup.send(
            f"Deleted track #{index}: **{deleted_track.title}** from **{deleted_track.author}**"
        )

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(pos="Current position.", value="Position value.", mode="Move mode.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.choices(mode=[Choice(name=k, value=k) for k in ["difference", "position"]])
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def move(self, interaction: discord.Interaction, pos: Range[int, 1], value: int, mode: str = "position"):
        """Move a track to new position using relative difference/absolute position."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore

        queue_length = player.queue.count

        before = pos
        after = -1

        if mode == "difference":
            after = pos + value
        elif mode == "position":
            after = value

        if not (1 <= before <= queue_length and 1 <= after <= queue_length and before <= after):
            await interaction.followup.send(f"Invalid position(s): `before: {before} -> after: {after}`")
            return

        track_temp = player.queue.get_at(before - 1)
        player.queue.delete(before - 1)
        player.queue.put_at(after - 1, track_temp)

        await interaction.followup.send(f"Moved track from #{before} to #{after}")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    @app_commands.describe(pos1="Position of first track", pos2="Position of second track")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def swap(self, interaction: discord.Interaction, pos1: Range[int, 1], pos2: Range[int, 1]):
        """Swap two tracks in the queue."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore

        player.queue.swap(pos1 - 1, pos2 - 1)
        await interaction.followup.send(f"Swapped track #{pos1} and #{pos2}.")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shuffle(self, interaction: discord.Interaction):
        """Shuffle the queue."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore

        player.queue.shuffle()
        await interaction.followup.send("Done shuffling the queue.")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def clear(self, interaction: discord.Interaction):
        """Clear the queue - vote if you don't have MANAGE_GUILD permission, 'no questions' otherwise."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore

        if (
            # The invoker has the MANAGE_GUILD
            interaction.user.guild_permissions.manage_guild
            or
            # Only you & the bot
            len(player.client.users) == 2
            or
            # The voting passes.
            await NamelessVoteMenu(interaction, player, "clear", "queue").start()
        ):
            player.queue.clear()
            await interaction.followup.send(content="Cleared the queue.")
        else:
            await interaction.followup.send(content="Nah, I'd pass.")

    config = app_commands.Group(name="config", description="Configure this music session.")

    @config.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.describe(channel="The target channel for 'Now playing' message delivery.")
    async def set_feed_channel(self, interaction: discord.Interaction, channel: discord.abc.Messageable):
        """Change where the now-playing messages are sent."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore
        if not channel.permissions_for(player.guild.me).send_messages:  # type: ignore
            await interaction.followup.send("I don't have permission to send messages in that channel")
            return

        player.trigger_channel_id = channel.id
        await interaction.followup.send(f"Changed the trigger channel to {channel.mention}")

    @config.command()
    @app_commands.guild_only()
    @app_commands.describe(value="Desired 'Now playing' message delivery status.")
    @app_commands.choices(
        value=[
            Choice(name="on", value=1),
            Choice(name="off", value=0),
        ]
    )
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def set_now_playing(self, interaction: discord.Interaction, value: int):
        """Change 'Now playing' message mode."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore
        player.play_now_allowed = bool(value)

        await interaction.followup.send(f"Now playing message is now {'on' if player.play_now_allowed else 'off'}")

    @config.command()
    @app_commands.guild_only()
    @app_commands.describe(value="Autoplay mode. 'partial' means no auto_queue population.")
    @app_commands.choices(
        value=[
            Choice(name="Enabled - enable autoplay with 'auto_queue' population.", value=0),
            Choice(name="Partial - enable autoplay WITHOUT 'auto_queue' population.", value=1),
            Choice(name="Disabled - disable autoplay.", value=2),
        ]
    )
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.must_not_be_a_stream)
    async def set_auto_play(
        self,
        interaction: discord.Interaction,
        value: int,
    ):
        """Change AutoPlay mode."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)
        player.autoplay = AutoPlayMode(value)

        await interaction.followup.send(f"AutoPlay mode is now {player.autoplay.name}")

    @config.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.describe(mode="Loop mode.")
    @app_commands.choices(
        mode=[
            Choice(name="Disable - disable looping.", value=0),
            Choice(name="Track - looping the current track.", value=1),
            Choice(name="All - looping *every* track in the queue.", value=2),
        ]
    )
    async def set_loop(self, interaction: discord.Interaction, mode: int):
        """Set loop mode."""
        await interaction.response.defer()

        player: NamelessPlayer = cast(NamelessPlayer, interaction.guild.voice_client)  # type: ignore
        enum_mode = QueueMode(mode)

        def normalize_enum_name(e: QueueMode) -> str:
            return e.name.lower().replace(" ", "_")

        if player.queue.mode is enum_mode:
            await interaction.followup.send("Already in this mode")
            return

        player.queue.mode = enum_mode
        await interaction.followup.send(f"Loop mode set to {normalize_enum_name(enum_mode)}")


async def setup(bot: Nameless):
    if NamelessConfig.MUSIC.NODES:
        await bot.add_cog(MusicCog(bot))
        logging.info("%s cog added!", __name__)
    else:
        raise commands.ExtensionFailed(__name__, ValueError("Lavalink options are not properly provided"))


async def teardown(bot: Nameless):
    await bot.remove_cog(MusicCog.__cog_name__)
    logging.warning("%s cog removed!", __name__)
