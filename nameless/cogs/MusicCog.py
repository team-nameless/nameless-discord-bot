import asyncio
import datetime
import logging
import random
from typing import cast

import discord
import wavelink
from discord import ClientException, app_commands
from discord.app_commands import Choice, Range
from discord.ext import commands
from discord.utils import escape_markdown
from reactionmenu import ViewButton, ViewMenu
from wavelink import AutoPlayMode, QueueMode, TrackStartEventPayload

from nameless import Nameless
from nameless.cogs.checks.MusicCogCheck import MusicCogCheck
from nameless.commons.Cache import lru_cache
from nameless.customs.voice_backends.BaseVoiceBackend import Player
from nameless.database import CRUD
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

        self.nodes = [
            wavelink.Node(
                uri=f"{'https' if node.secure else 'http'}://{node.host}:{node.port}",
                password=node.password,
            )
            for node in NamelessConfig.MUSIC.NODES
        ]

        bot.loop.create_task(self.connect_nodes())
        self.autoleave_waiter_task: dict[int, asyncio.Task] = {}

    async def autoleave(self, chn: discord.VoiceChannel | discord.StageChannel):
        logging.warning("Initiating autoleave for voice channel ID:%s of guild %s", chn.id, chn.guild.id)
        await asyncio.sleep(NamelessConfig.MUSIC.AUTOLEAVE_TIME)

        guild = self.bot.get_guild(chn.guild.id)
        player = cast(Player, guild.voice_client)  # type: ignore

        await player.disconnect(force=True)
        player.cleanup()

        if chn.id in self.autoleave_waiter_task:
            del self.autoleave_waiter_task[chn.id]

        logging.warning("Autoleave timeout! Disconnect from voice channel ID:%s of guild %s", chn.id, chn.guild.id)

    @staticmethod
    async def list_voice_state_change(before: discord.VoiceState, after: discord.VoiceState):
        """Method to check what has been updated in voice state."""
        # diff = []
        # for k in before.__slots__:
        #     if getattr(before, k) != getattr(after, k):
        #         diff.append(k)
        return [k for k in before.__slots__ if getattr(before, k) != getattr(after, k)]

    @staticmethod
    @lru_cache(maxsize=128)
    def remove_artist_suffix(name: str) -> str:
        if not name:
            return "N/A"
        name = escape_markdown(name, as_needed=True)
        return name.removesuffix(" - Topic")

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        await wavelink.Pool.connect(client=self.bot, nodes=self.nodes, cache_capacity=100)

        if not self.is_ready.is_set():
            self.is_ready.set()

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        node = payload.node
        logging.info("Node {%s} (%s) is ready!", node.identifier or "N/A", node.uri)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: TrackStartEventPayload):
        player: Player = cast(Player, payload.player)
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
            embed = self.generate_embed_np_from_playable(
                player,
                track,
                self.bot.user,
                dbg,
                original is not None and original.recommended,
            )
            await chn.send(embed=embed)  # type: ignore

    def __make_data_from_state(
        self, state: discord.VoiceState, member: discord.Member
    ) -> tuple[discord.VoiceChannel | discord.StageChannel, bool, Player, int]:
        chn: discord.VoiceChannel | discord.StageChannel = state.channel  # type: ignore
        voice_client = cast(Player, chn.guild.voice_client)
        bot_is_in_vc = voice_client is not None and voice_client.channel.id == chn.id
        member_count = len(chn.members) - 1 if bot_is_in_vc else len(chn.members)

        return chn, bot_is_in_vc, voice_client, member_count

    async def handle_leave_event(self, member: discord.Member, state: discord.VoiceState):
        chn, bot_is_in_vc, vc, member_count = self.__make_data_from_state(state, member)
        if bot_is_in_vc and member_count <= 0:
            # random check to prevent multiple autoleave
            if self.autoleave_waiter_task.get(chn.id):
                self.autoleave_waiter_task.pop(chn.id).cancel()

            logging.info(
                "No member present in voice channel ID:%s in guild %s, creating autoleave", chn.id, member.guild.id
            )
            self.autoleave_waiter_task[vc.channel.id] = asyncio.create_task(self.autoleave(chn))
            return

        # we got disconnected and we has autoleave task for this voice channel
        if not bot_is_in_vc and self.autoleave_waiter_task.get(chn.id):
            logging.debug(f"Looks like we got disconnected from voice channel ID:{chn.id} in guild {member.guild.id}")
            logging.info("Cancel autoleave task for voice channel ID:%s in guild %s", chn.id, member.guild.id)
            self.autoleave_waiter_task.pop(chn.id).cancel()

    async def handle_join_event(self, member: discord.Member, state: discord.VoiceState):
        chn, bot_is_in_vc, _, member_count = self.__make_data_from_state(state, member)
        guild = chn.guild

        if bot_is_in_vc and self.autoleave_waiter_task.get(chn.id):
            # check if autoleave is already in progress, and if it is done, remove it and return
            waiter_task = self.autoleave_waiter_task[chn.id]
            if waiter_task.done():
                self.autoleave_waiter_task.pop(chn.id)
                return

            if member_count > 0:
                logging.info(
                    "New member present in voice channel ID:%s in guild %s, cancel autoleave", chn.id, guild.id
                )

                waiter_task.cancel()
                self.autoleave_waiter_task.pop(chn.id)

    async def handle_move_channel_event(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        before_chn, bot_in_before, _, before_member_count = self.__make_data_from_state(before, member)
        after_chn, bot_in_after, _, after_member_count = self.__make_data_from_state(after, member)

        if bot_in_before:
            if self.autoleave_waiter_task.get(before_chn.id):
                logging.info(
                    "Move to new voice channel ID:%s in guild %s, cancel autoleave from %s",
                    after_chn.id,
                    before_chn.guild.id,
                    before_chn.id,
                )
                self.autoleave_waiter_task.pop(before_chn.id).cancel()

            if before_member_count <= 0:
                if self.autoleave_waiter_task.get(before_chn.id):
                    self.autoleave_waiter_task.pop(before_chn.id).cancel()

                logging.info(
                    "No member present in voice channel ID:%s in guild %s, creating autoleave",
                    before_chn.id,
                    before_chn.guild.id,
                )
                self.autoleave_waiter_task[before_chn.id] = asyncio.create_task(self.autoleave(before_chn))

        if bot_in_after:
            if after_member_count > 0:
                if self.autoleave_waiter_task.get(after_chn.id):
                    logging.info(
                        "New member present in voice channel ID:%s in guild %s, cancel autoleave",
                        after_chn.id,
                        after_chn.guild.id,
                    )
                    self.autoleave_waiter_task.pop(after_chn.id).cancel()

                if self.autoleave_waiter_task.get(before_chn.id):
                    logging.info("Cancel autoleave from %s", before_chn.id)
                    self.autoleave_waiter_task.pop(before_chn.id).cancel()

            elif after_member_count <= 0:
                if self.autoleave_waiter_task.get(after_chn.id):
                    self.autoleave_waiter_task.pop(after_chn.id).cancel()

                logging.info(
                    "No member present in voice channel ID:%s in guild %s, creating autoleave",
                    after_chn.id,
                    after_chn.guild.id,
                )
                self.autoleave_waiter_task[after_chn.id] = asyncio.create_task(self.autoleave(after_chn))

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if before.channel and after.channel:
            return await self.handle_move_channel_event(member, before, after)

        if before.channel:
            return await self.handle_leave_event(member, before)

        if after.channel:
            return await self.handle_join_event(member, after)

    def generate_embeds_from_playable(
        self,
        tracks: wavelink.Queue | list[wavelink.Playable] | wavelink.Playlist,
        title: str = "Tracks currently in queue",
    ) -> list[discord.Embed]:
        txt = ""
        embeds: list[discord.Embed] = []

        for idx, track in enumerate(tracks, start=1):
            upcoming = (
                f"{idx} - " f"[{track.title} by {self.remove_artist_suffix(track.author)}]" f"({track.uri or 'N/A'})\n"
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

    def generate_embed_np_from_playable(
        self,
        player: Player,
        track: wavelink.Playable,
        user: discord.User | discord.Member | discord.ClientUser | None,
        dbg,
        is_recommended=False,
    ) -> discord.Embed:
        assert user is not None

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
                value=self.remove_artist_suffix(track.author) if track.author else "N/A",
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
                f"by {self.remove_artist_suffix(next_tr.author)}]"
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
            await interaction.user.voice.channel.connect(cls=Player, self_deaf=True)  # type: ignore
            await interaction.followup.send("Connected to your voice channel")

            player = cast(Player, interaction.guild.voice_client)  # type: ignore
            player.trigger_channel_id = interaction.channel.id  # type: ignore

        except ClientException:
            await interaction.followup.send("Already connected")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.bot_in_voice)
    async def disconnect(self, interaction: discord.Interaction):
        """Disconnect from my current voice channel"""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore

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
        search: str,
        source: str = "youtube",
        action: str = "add",
        reverse: bool = False,
        shuffle: bool = False,
    ):
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
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

            if action == "add":
                return await player.queue.put_wait(tracks)
            elif action == "insert":
                return await player.queue.insert_wait(tracks)
            return 0

        try:
            tracks: wavelink.Search = await wavelink.Playable.search(search, source=SOURCE_MAPPING[source])
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
            msg = f"{action.title()}ed {added} {'songs' if added > 1 else 'song'} to the queue"

        if soon_added:
            embeds = self.generate_embeds_from_playable(soon_added, title=msg)
            self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds))

        if player.current and player.current.is_stream:
            should_play = True
            await player.stop(force=True)

        if should_play:
            await player.play(player.queue.get(), add_history=False)

    async def set_loop_mode(self, interaction: discord.Interaction, mode: int):
        """Set loop mode"""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
        enum_mode = QueueMode(mode)

        if player.queue.mode is enum_mode:
            await interaction.followup.send("Already in this mode")
            return

        player.queue.mode = enum_mode
        await interaction.followup.send(f"Loop mode set to {player.queue.mode.name}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(search="Search query", source="Source to search")
    @app_commands.choices(source=[Choice(name=k, value=k) for k in SOURCE_MAPPING])
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def play(self, interaction: discord.Interaction, search: str, source: str = "youtube"):
        """Add or search track(s) to queue. Also allows you to play a playlist"""
        await self._play(interaction, search, source)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_is_playing_something)
    async def pause(self, interaction: discord.Interaction):
        """Pause current track"""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore

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

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore

        if not player.paused:
            await interaction.followup.send("Already resuming")
            return

        await player.pause(False)
        await interaction.followup.send("Resumed")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def stop(self, interaction: discord.Interaction):
        """Stop playback. To start playing again, use 'music.queue.start'"""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore

        if not player.playing:
            await interaction.followup.send("Not playing anything")
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

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
        track: wavelink.Playable | None = player.current
        if not track:
            await interaction.response.send_message("Not playing anything")
            return

        dbg = CRUD.get_or_create_guild_record(interaction.guild)
        embed = self.generate_embed_np_from_playable(player, track, interaction.user, dbg)
        await interaction.followup.send(embed=embed)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.describe(volume="Change player volume")
    async def volume(self, interaction: discord.Interaction, volume: Range[int, 0, 500]):
        """Change the volume."""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
        await player.set_volume(volume)
        await interaction.followup.send(f"Changed the volume to {volume}%")

    @app_commands.command(name="autoplay")
    @app_commands.guild_only()
    @app_commands.describe(value="Intended autoplay mode if enabled: 'enable' or 'disable'")
    @app_commands.choices(
        value=[
            Choice(name="enable", value=0),  # wavelink.AutoPlayMode.enabled
            Choice(name="disable", value=1),  # wavelink.AutoPlayMode.partial
        ]
    )
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.must_not_be_a_stream)
    async def autoplay_mode(
        self,
        interaction: discord.Interaction,
        value: int,
    ):
        """
        Change AutoPlay mode.
        Priority normal queue over autoqueue so you can add songs to the normal queue and autoqueue won't be triggered.
        """
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
        await player.set_autoplay_mode(value)

        await interaction.followup.send(
            f"AutoPlay mode is now {'enabled' if player.autoplay is AutoPlayMode.enabled else 'disabled'}"
        )

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(value="Intended track loop mode value: 'enable' or 'disable'")
    @app_commands.choices(
        value=[
            Choice(name="enable", value=1),  # wavelink.QueueMode.loop
            Choice(name="disable", value=0),  # wavelink.QueueMode.normal
        ]
    )
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def loop_track(self, interaction: discord.Interaction, value: int):
        """Change 'Loop track' mode."""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
        player.queue.mode = QueueMode(value)

        await interaction.followup.send(f"Loop track is now {'on' if player.queue.mode is QueueMode.loop else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.describe(mode="All mode available for looping")
    @app_commands.choices(
        mode=[
            Choice(name="Disable", value=0),
            Choice(name="Track", value=1),
            Choice(name="All", value=2),
        ]
    )
    async def loop(self, interaction: discord.Interaction, mode: int):
        """Change 'Loop' mode."""
        await self.set_loop_mode(interaction, mode)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def skip(self, interaction: discord.Interaction):
        """Skip a song. Even if it is looping."""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
        track: wavelink.Playable = player.current  # type: ignore

        if await NamelessVoteMenu(interaction, player, "skip", track.title).start():
            await player.skip()
            if bool(player.queue):
                await interaction.followup.send("Next track should be played now")
        else:
            await interaction.followup.send("Not skipping because not enough votes!")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def force_skip(self, interaction: discord.Interaction):
        """Force skip a song, if you have enough permissions"""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
        if interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.manage_channels:  # type: ignore
            await player.skip()
            await interaction.followup.send("Force skip success! Next track should be played now")
        else:
            await interaction.followup.send("Not skipping because not enough permissions!")

    async def seek_position(self, player: Player, position: int):
        """Seek to position in milliseconds. Returns the new position in milliseconds"""

        if not 0 <= position <= player.current.length:  # type: ignore
            raise ValueError("Invalid position to seek")
        await player.seek(position)

    async def seek_position_sec(self, player: Player, position: float):
        """Seek to position in seconds"""
        await self.seek_position(player, int(position * 1000))

    async def seek_position_format(self, player: Player, position: str):
        """Seek to position in time format (ex: `position="7:27"` or `position="00:07:27"`)"""
        time_split = position.split(":")
        if len(time_split) == 2:
            real_sec = int(time_split[0]) * 60 + int(time_split[1])
        elif len(time_split) == 3:
            real_sec = int(time_split[0]) * 3600 + int(time_split[1]) * 60 + int(time_split[2])
        else:
            raise ValueError("Invalid time format")

        await self.seek_position(player, real_sec * 1000)

    async def seek_percent(self, player: Player, percent: int):
        pos = 0
        if not 0 <= percent <= 100:
            raise ValueError("Invalid percent to seek")

        # last check
        if not player.current:
            raise ValueError("Not playing anything")

        if percent == 0:
            pos = 0
        elif percent == 100:
            pos = player.current.length
        else:
            pos = int(player.current.length * percent / 100)

        await player.seek(pos)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(
        in_milliseconds="Seek to position in milliseconds",
        in_seconds="Seek to position in seconds",
        in_percent="Seek to position in percent",
        position='Seek to position in time format (ex: `position="7:27"` or `position="00:07:27"`)',
    )
    # @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def seek(
        self,
        interaction: discord.Interaction,
        in_milliseconds: app_commands.Range[int, 0] = 0,
        in_seconds: app_commands.Range[int, 0] = 0,
        in_percent: app_commands.Range[int, 0] = 0,
        position: str = "0",
    ):
        """Seek to position in a track. Leave empty to seek to track beginning."""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
        track: wavelink.Playable = player.current  # type: ignore

        if not track.is_seekable:
            await interaction.followup.send("This track is not seekable!")
            return

        if await NamelessVoteMenu(interaction, player, "seek", track.title).start():
            if in_seconds:
                await self.seek_position_sec(player, in_seconds)
            elif position != "0":
                await self.seek_position_format(player, position)
            elif in_percent:
                await self.seek_percent(player, in_percent)
            else:
                await self.seek_position(player, in_milliseconds)

            dbg = CRUD.get_or_create_guild_record(interaction.guild)
            embed = self.generate_embed_np_from_playable(player, track, interaction.user, dbg)
            await interaction.followup.send(content="Seeked", embed=embed)

    toggle = app_commands.Group(name="toggle", description="Commands related to toggling function in player.")

    @toggle.command(name="nowplaying_message")
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def toggle_nowplaying_message(self, interaction: discord.Interaction):
        """Toggle 'Now playing' message delivery on every non-looping track."""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
        player.play_now_allowed = not player.play_now_allowed
        await interaction.followup.send(f"'Now playing message' is now {'on' if player.play_now_allowed else 'off'}")

    @toggle.command(name="autoplay")
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.must_not_be_a_stream)
    async def toggle_autoplay(
        self,
        interaction: discord.Interaction,
    ):
        """Toggle AutoPlay feature."""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
        current_mode = await player.toggle_autoplay()

        await interaction.followup.send(f"AutoPlay is now {'on' if current_mode else 'off'}")

    queue = app_commands.Group(name="queue", description="Commands related to queue management.")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def start(self, interaction: discord.Interaction):
        """Start playing the queue"""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore

        if not bool(player.queue):
            await interaction.followup.send("Nothing in the queue")
            return

        player.autoplay = AutoPlayMode.partial
        await player.play(player.queue.get())

        await interaction.followup.send("Started playing the queue")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(search="Search query", source="Source to search")
    @app_commands.choices(source=[Choice(name=k, value=k) for k in SOURCE_MAPPING])
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def add(self, interaction: discord.Interaction, search: str, source: str = "youtube"):
        """Alias for `play` command."""
        await self._play(interaction, search, source)

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(
        search="Playlist URL", reverse="Add playlist in reverse order", shuffle="Add playlist in shuffled order"
    )
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def add_playlist(
        self, interaction: discord.Interaction, search: str, reverse: bool = False, shuffle: bool = False
    ):
        """Add playlist to the queue"""
        await self._play(interaction, search, reverse=reverse, shuffle=shuffle)

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(
        search="Playlist URL", reverse="Insert playlist in reverse order", shuffle="Insert playlist in shuffled order"
    )
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def insert_playlist(
        self, interaction: discord.Interaction, search: str, reverse: bool = False, shuffle: bool = False
    ):
        """Insert playlist to the queue"""
        await self._play(interaction, search, action="insert", reverse=reverse, shuffle=shuffle)

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(search="Search query", source="Source to search")
    @app_commands.choices(source=[Choice(name=k, value=k) for k in SOURCE_MAPPING])
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def insert(self, interaction: discord.Interaction, search: str, source: str = "youtube"):
        """Insert track(s) to the front queue"""
        await self._play(interaction, search, source, action="insert")

    @queue.command()
    @app_commands.guild_only()
    async def view(self, interaction: discord.Interaction):
        """View current queue"""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore

        if not player.queue:
            await interaction.followup.send("Wow, such empty queue. Mind adding some cool tracks?")
            return

        embeds = self.generate_embeds_from_playable(player.queue)
        self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds))

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def view_autoplay(self, interaction: discord.Interaction):
        """View current autoplay queue. Can be none if autoplay is disabled."""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore

        if player.autoplay != AutoPlayMode.enabled and not bool(player.auto_queue):
            await interaction.followup.send(
                "Seems like autoplay is disabled or autoplay queue is has not been populated yet."
            )
            return

        embeds = self.generate_embeds_from_playable(player.auto_queue, title="Autoplay queue")
        self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds))

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def repopulate_autoqueue(self, interaction: discord.Interaction):
        """Repopulate autoplay queue based on current song"""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore

        if player.autoplay != AutoPlayMode.enabled:
            await interaction.followup.send("Seems like autoplay is disabled")
            return

        await player.repopulate_auto_queue()
        await interaction.followup.send("Repopulated autoplay queue!")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(index="The index to remove")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def delete(self, interaction: discord.Interaction, index: Range[int, 1]):
        """Remove track from queue"""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore

        q = player.queue._queue
        index = index - 1

        if index >= len(q):
            await interaction.followup.send("Oops! You picked the position beyond the queue size.")
            return

        deleted_track = q[index]
        await player.queue.delete(index)
        await interaction.followup.send(
            f"Deleted track at position #{index}: **{deleted_track.title}** from **{deleted_track.author}**"
        )

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(pos="Current position", value="Position value", mode="Move mode")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.choices(mode=[Choice(name=k, value=k) for k in ["difference", "position"]])
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def move(self, interaction: discord.Interaction, pos: Range[int, 1], value: int, mode: str = "pos"):
        """Move track to new position using relative difference"""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore

        int_queue = player.queue._queue
        queue_length = len(int_queue)

        before = pos
        after = -1

        if mode == "diff":
            after = pos + value
        elif mode == "pos":
            after = value

        if not (1 <= before <= queue_length and 1 <= after <= queue_length):
            await interaction.followup.send(f"Invalid position(s): `{before} -> {after}`")
            return

        temp = int_queue[before - 1]
        del int_queue[before - 1]
        int_queue.insert(after - 1, temp)

        await interaction.followup.send(f"Moved track #{before} to #{after}")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    @app_commands.describe(pos1="Position of first track", pos2="Position of second track")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def swap(self, interaction: discord.Interaction, pos1: Range[int, 1], pos2: Range[int, 1]):
        """Swap two tracks."""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore

        q = player.queue._queue
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
    async def shuffle(self, interaction: discord.Interaction):
        """Shuffle the queue"""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
        player.queue.shuffle()
        await interaction.followup.send("Shuffled the queue")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def clear(self, interaction: discord.Interaction):
        """Clear the queue, using vote system."""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore

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

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
        player.queue.clear()
        await interaction.followup.send("Cleared the queue")

    settings = app_commands.Group(name="settings", description="Settings for the music cog")

    @settings.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.describe(channel="The channel that you want the now-playing messages to be sent to")
    async def set_feed_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Change where the now-playing messages are sent."""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
        if not channel.permissions_for(player.guild.me).send_messages:  # type: ignore
            await interaction.followup.send("I don't have permission to send messages in that channel")
            return

        player.trigger_channel_id = channel.id
        await interaction.followup.send(f"Changed the trigger channel to {channel.mention}")

    @settings.command(name="nowplaying_message")
    @app_commands.guild_only()
    @app_commands.describe(value="Intended 'Now playing' message mode value: 'enable' or 'disable'")
    @app_commands.choices(
        value=[
            Choice(name="enable", value=1),
            Choice(name="disable", value=0),
        ]
    )
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def settings_nowplaying_message(self, interaction: discord.Interaction, value: int):
        """Change 'Now playing' message mode."""
        await interaction.response.defer()

        player: Player = cast(Player, interaction.guild.voice_client)  # type: ignore
        player.play_now_allowed = bool(value)

        await interaction.followup.send(f"Now playing message is now {'on' if player.play_now_allowed else 'off'}")


async def setup(bot: Nameless):
    if NamelessConfig.MUSIC.NODES:
        await bot.add_cog(MusicCog(bot))
        logging.info("%s cog added!", __name__)
    else:
        raise commands.ExtensionFailed(__name__, ValueError("Lavalink options are not properly provided"))


async def teardown(bot: Nameless):
    await bot.remove_cog("MusicLavalinkCog")
    logging.warning("%s cog removed!", __name__)
