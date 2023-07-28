import asyncio
import datetime
import logging
import random
from typing import Any, Dict, List, Optional, Type, Union
from urllib import parse

import discord
import wavelink
from discord import ClientException, app_commands
from discord.app_commands import AppCommandError, Choice, Range
from discord.ext import commands
from discord.utils import escape_markdown
from reactionmenu import ViewButton, ViewMenu
from wavelink import TrackEventPayload
from wavelink.ext import spotify

from nameless import Nameless
from nameless.cogs.checks import MusicLavalinkCogCheck
from nameless.commons import Utility
from nameless.ui_kit import TrackSelectDropdown, VoteMenu
from NamelessConfig import NamelessConfig


__all__ = ["MusicLavalinkCog"]

from nameless.database import CRUD


music_default_sources: List[str] = ["youtube", "soundcloud", "ytmusic"]


class MusicLavalinkCog(commands.GroupCog, name="music"):
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

        self.autoleave_waiter_task = {}

    async def autoleave(self, chn: discord.VoiceChannel):
        logging.warning("Initiating autoleave for voice channel ID:%s of guild %s", chn.id, chn.guild.id)
        await asyncio.sleep(120)
        await self.bot.get_guild(chn.guild.id).voice_client.disconnect(force=True)
        self.bot.get_guild(chn.guild.id).voice_client.cleanup()
        logging.warning("Disconnect from voice channel ID:%s of guild %s", chn.id, chn.guild.id)

    @staticmethod
    def generate_embeds_from_tracks(
        tracks: List[wavelink.Playable],
    ) -> List[discord.Embed]:
        embeds: List[discord.Embed] = []
        txt = ""

        for idx, track in enumerate(tracks):
            upcoming = (
                f"{idx + 1} - "
                f"[{escape_markdown(track.title)} from {escape_markdown(track.author)}]"  # pyright: ignore
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
                    f"({track.uri or 'N/A'})\n"
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
    async def show_paginated_tracks(interaction: discord.Interaction, embeds: List[discord.Embed]):
        view_menu = ViewMenu(interaction, menu_type=ViewMenu.TypeEmbed)
        view_menu.add_pages(embeds)

        view_menu.add_button(ViewButton.back())
        view_menu.add_button(ViewButton.end_session())
        view_menu.add_button(ViewButton.next())

        await view_menu.start()

    @staticmethod
    def resolve_direct_url(search: str) -> Optional[Type[wavelink.Playable]]:
        locations = {
            "soundcloud.com": wavelink.SoundCloudTrack,
            "open.spotify.com": spotify.SpotifyTrack,
            "music.youtube.com": wavelink.YouTubeMusicTrack,
            "youtube.com": wavelink.YouTubeTrack,
            "youtu.be": wavelink.YouTubeTrack,
        }

        if domain := parse.urlparse(search).netloc:
            return locations.get(domain, wavelink.Playable)

        return None

    async def connect_nodes(self):
        await self.bot.wait_until_ready()

        nodes = [
            wavelink.Node(
                uri=f"{node['host']}:{node['port']}",
                secure=node["is_secure"],
                password=node["password"],
            )
            for node in NamelessConfig.LAVALINK["nodes"]
        ]

        await wavelink.NodePool.connect(
            client=self.bot,
            nodes=nodes,
            spotify=spotify.SpotifyClient(
                client_id=NamelessConfig.LAVALINK["spotify"]["client_id"],
                client_secret=NamelessConfig.LAVALINK["spotify"]["client_secret"],
            )
            if self.can_use_spotify
            else None,
        )

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        logging.info("Node {%s} (%s) is ready!", node.id, node.uri)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        # Technically auto disconnect the bot from lavalink if no member present for 120 seconds
        chn = before.channel if before.channel else after.channel
        guild = before.channel.guild if before.channel else after.channel.guild

        voice_members = [member for member in chn.members if member.id != self.bot.user.id]
        bot_is_in_vc = any(member for member in chn.members if member.id == self.bot.user.id)

        if bot_is_in_vc:
            if len(voice_members) == 0:
                logging.info(
                    "No member present in voice channel ID:%s in guild %s, creating autoleave", chn.id, guild.id
                )
                self.autoleave_waiter_task[chn.id] = self.bot.loop.create_task(self.autoleave(chn))  # pyright: ignore
                logging.debug("%s", self.autoleave_waiter_task)
            else:
                if self.autoleave_waiter_task:
                    logging.info(
                        "New member present in voice channel ID:%s in guild %s, cancel autoleave", chn.id, guild.id
                    )
                    self.autoleave_waiter_task[chn.id].cancel()
                    del self.autoleave_waiter_task[chn.id]
                    logging.debug("%s", self.autoleave_waiter_task)

        # Auto disconnect the bot from lavalink if disconnected manually
        if member.id == self.bot.user.id:
            before_was_in_voice = before.channel is not None
            after_not_in_noice = after.channel is None

            if before_was_in_voice and after_not_in_noice:
                node_dict = wavelink.NodePool.nodes.items()
                guilds_players = [p for (_, node) in node_dict if (p := node.get_player(member.guild.id))]
                if guilds_players:
                    bot_player: List[wavelink.Player] = [
                        player for player in guilds_players if player.client.user.id == self.bot.user.id
                    ]
                    if bot_player:
                        logging.debug(
                            "Guild player %s still connected even if it is removed from voice, disconnecting",
                            bot_player[0].guild.id,
                        )
                        await bot_player[0].disconnect()
                        bot_player[0].cleanup()

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: TrackEventPayload):
        player = payload.player
        track = payload.track

        chn = player.guild.get_channel(getattr(player, "trigger_channel_id"))

        if chn is not None and getattr(player, "play_now_allowed") and getattr(player, "should_send_play_now"):
            """
            if track.is_stream:
                await chn.send(f"Streaming music from {track.uri}")  # pyright: ignore
            else:
                await chn.send(f"Playing: **{track.title}** from **{track.author}** ({track.uri})")  # pyright: ignore
            """
            if not track.is_stream:
                await chn.send(f"Playing: **{track.title}** from **{track.author}** ({track.uri})")  # pyright: ignore


    async def __preprocess_radio_then_play(
        self, interaction: discord.Interaction, message: discord.WebhookMessage, url: str, is_radio: bool = False
    ):
        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        # In case of sudden switch from queued music -> radio
        if not vc.queue.is_empty:
            vc.queue.clear()

        if not vc.auto_queue.is_empty:
            vc.auto_queue.clear()

        if is_radio:
            db_guild = CRUD.get_or_create_guild_record(interaction.guild)
            db_guild.radio_start_time = discord.utils.utcnow()

        tracks = await vc.current_node.get_tracks(wavelink.GenericTrack, url or "")

        if tracks:
            track = tracks[0]
            if is_radio and not track.is_stream:
                raise AppCommandError("Radio track must be a stream")

            setattr(vc, "should_send_play_now", True)
            await chn.send(f"Streaming music from {url}")  # pyright: ignore
            vc.queue.loop = True
            await vc.play(track)
        else:
            raise AppCommandError(f"No tracks found for {url}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(source_url="Radio site URL to broadcast, like 'https://listen.moe/stream'")
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    async def radio(self, interaction: discord.Interaction, source_url: str):
        """Play a radio stream. Clear any queue that exists."""
        await interaction.response.defer()

        if not Utility.is_an_url(source_url):
            await interaction.followup.send(
                "You should provide a direct URL to the stream. " "Use 'https://listen.moe/stream' as example."
            )
            return

        m: discord.WebhookMessage = await interaction.followup.send(
            content="Connecting to the radio stream..."
        )  # pyright: ignore

        await self.__preprocess_radio_then_play(interaction, m, source_url, True)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_in_voice)
    async def connect(self, interaction: discord.Interaction):
        """
        Connect to your current voice channel.
        """
        await interaction.response.defer()

        try:
            await interaction.user.voice.channel.connect(cls=wavelink.Player, self_deaf=True)  # pyright: ignore
            await interaction.followup.send("Connected to your voice channel")

            vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

            setattr(vc, "should_send_play_now", True)
            setattr(vc, "play_now_allowed", True)
            setattr(vc, "trigger_channel_id", interaction.channel.id)
            vc.autoplay = True
        except ClientException:
            await interaction.followup.send("Already connected")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.bot_in_voice)
    async def disconnect(self, interaction: discord.Interaction):
        """Disconnect from my current voice channel"""
        await interaction.response.defer()

        try:
            await interaction.guild.voice_client.disconnect(force=True)
            interaction.guild.voice_client.cleanup()
            await interaction.followup.send("Disconnected from my own voice channel")
        except AttributeError:
            await interaction.followup.send("I am already disconnected!")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.queue_has_element)
    async def play(self, interaction: discord.Interaction):
        """Start playing the queue."""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        # When the user switch from radio -> normal queued track
        vc.queue.loop = False
        setattr(vc, "should_send_play_now", True)

        await interaction.followup.send("The queue should be playing now.")
        await vc.play(vc.queue.get(), populate=vc.autoplay)  # pyright: ignore

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.bot_must_play_track_not_stream)
    async def toggle_loop_track(self, interaction: discord.Interaction):
        """Toggle loop of current track."""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore
        vc.queue.loop = not vc.queue.loop
        setattr(vc, "should_send_play_now", not vc.queue.loop)
        await interaction.followup.send(f"Track loop set to {'on' if vc.queue.loop else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    async def toggle_loop_queue(self, interaction: discord.Interaction):
        """Toggle loop of current queue."""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if vc.queue.loop:
            await interaction.followup.send("You must have track looping disabled before using this.")
            return

        vc.queue.loop_all = not vc.queue.loop_all
        await interaction.followup.send(f"Queue loop set to {'on' if vc.queue.loop_all else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.bot_is_playing_something)
    async def pause(self, interaction: discord.Interaction):
        """Pause current track"""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if vc.is_paused():
            await interaction.followup.send("Already paused")
            return

        await vc.pause()
        await interaction.followup.send("Paused")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.bot_is_silent)
    async def resume(self, interaction: discord.Interaction):
        """Resume current playback, if paused"""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if not vc.is_paused():
            await interaction.followup.send("Already resuming")
            return

        await vc.resume()
        await interaction.followup.send("Resumed")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.bot_must_play_track_not_stream)
    @app_commands.check(MusicLavalinkCogCheck.queue_has_element)
    async def skip(self, interaction: discord.Interaction):
        """Skip a song. Even if it is looping."""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        track: wavelink.Playable = vc.current  # pyright: ignore
        should_set_play_now_again: bool = False
        current_play_now_state: bool = True

        if await VoteMenu("skip", track.title, interaction, vc).start():
            if vc.queue.loop:
                current_play_now_state = getattr(vc, "should_send_play_now")
                setattr(vc, "should_send_play_now", True)
                should_set_play_now_again = True

            await vc.stop()
            await interaction.followup.send("Next track should be played now")

            if should_set_play_now_again:
                setattr(vc, "should_send_play_now", current_play_now_state)
        else:
            await interaction.followup.send("Not skipping because not enough votes!")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(position="Position to seek to in milliseconds, defaults to run from start")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.bot_must_play_track_not_stream)
    async def seek(self, interaction: discord.Interaction, position: app_commands.Range[int, 0] = 0):
        """Seek to named position in a track"""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore
        track: wavelink.Playable = vc.current  # pyright: ignore

        if not 0 <= position <= track.length:
            await interaction.followup.send("Invalid position to seek")
            return

        if await VoteMenu("seek", track.title, interaction, vc).start():
            await vc.seek(position)
            delta_pos = datetime.timedelta(milliseconds=position)
            await interaction.followup.send(content=f"Seeking to position {delta_pos}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(segment="Segment percentage to seek (from 0 to 100, respecting with from 0% to 100%)")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.bot_must_play_track_not_stream)
    async def seek_segment(self, interaction: discord.Interaction, segment: Range[int, 0, 100] = 0):
        """Seek to percentage-based position in a track."""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore
        track: wavelink.Playable = vc.current  # pyright: ignore

        if await VoteMenu("seek_segment", track.title, interaction, vc).start():
            pos = int(float(track.length * segment / 100))
            await vc.seek(pos)
            delta_pos = datetime.timedelta(milliseconds=pos)
            await interaction.followup.send(f"Seek to {segment}%: {delta_pos}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    async def toggle_now_playing(self, interaction: discord.Interaction):
        """Toggle 'Now playing' message delivery on every non-looping track."""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore
        setattr(vc, "play_now_allowed", not getattr(vc, "play_now_allowed"))

        await interaction.followup.send(f"'Now playing' is now {'on' if getattr(vc, 'play_now_allowed') else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.must_not_be_a_stream)
    async def toggle_autoplay(self, interaction: discord.Interaction):
        """Toggle AutoPlay feature."""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore
        vc.autoplay = not vc.autoplay

        await interaction.followup.send(f"AutoPlay is now {'on' if vc.autoplay else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(show_next_track="Whether the next track should be shown (useless in looping)")
    @app_commands.check(MusicLavalinkCogCheck.bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.bot_is_playing_something)
    async def now_playing(self, interaction: discord.Interaction, show_next_track: bool = True):
        """Check now playing song"""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore
        track: wavelink.Playable = vc.current  # pyright: ignore

        thumbnail_url: str = await track.fetch_thumbnail() if isinstance(track, wavelink.YouTubeTrack) else ""

        is_stream = track.is_stream
        dbg = CRUD.get_or_create_guild_record(interaction.guild)

        embed = (
            discord.Embed(timestamp=datetime.datetime.now(), color=discord.Color.orange())
            .set_author(
                name="Now playing track",
                icon_url=interaction.user.display_avatar.url,
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
                    discord.utils.utcnow().replace(tzinfo=None) - dbg.radio_start_time
                    if is_stream
                    else f"{datetime.timedelta(milliseconds=vc.position)}/"
                    f"{datetime.timedelta(milliseconds=track.length)}"
                ),
            )
            .add_field(name="Looping", value="This is a stream" if is_stream else vc.queue.loop)
            .add_field(name="Paused", value=vc.is_paused())
            .set_thumbnail(url=thumbnail_url)
        )

        if not vc.queue.loop and show_next_track and not track.is_stream:
            try:
                next_tr = vc.queue.copy().get()
            except wavelink.QueueEmpty:
                next_tr = None

            embed.add_field(
                name="Next track",
                value=f"[{escape_markdown(next_tr.title) if next_tr.title else 'Unknown title'} "
                f"by {escape_markdown(next_tr.author)}]"  # pyright: ignore
                f"({next_tr.uri or 'N/A'})"
                if next_tr
                else "N/A",
            )

        await interaction.followup.send(embed=embed)

    queue = app_commands.Group(name="queue", description="Commands related to queue management.")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    async def view(self, interaction: discord.Interaction):
        """View current queue"""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if vc.queue.is_empty:
            await interaction.followup.send("Wow, such empty queue. Mind adding some cool tracks?")
            return

        embeds = self.generate_embeds_from_queue(vc.queue)
        self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds))

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    async def view_autoplay(self, interaction: discord.Interaction):
        """View current autoplay queue"""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if vc.auto_queue.is_empty:
            await interaction.followup.send("Wow, such empty autoplay queue. Mind enable it with `toggle_autoplay`?")
            return

        embeds = self.generate_embeds_from_queue(vc.auto_queue)
        self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds))

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(index="The index to remove")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.queue_has_element)
    async def delete(self, interaction: discord.Interaction, index: Range[int, 1]):
        """Remove track from queue"""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore
        q = vc.queue._queue

        try:
            deleted_track = q[index - 1]
            del q[index - 1]
            await interaction.followup.send(
                f"Deleted track at position #{index}: **{deleted_track.title}** from **{deleted_track.author}**"
            )
        except IndexError:
            await interaction.followup.send("Oops!")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(search="Search query", source="Source to search")
    @app_commands.choices(source=[Choice(name=k, value=k) for k in music_default_sources])
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    async def add(self, interaction: discord.Interaction, search: str, source: str = "youtube"):
        """Add selected track(s) to queue"""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if search_cls := self.resolve_direct_url(search):
            track = (await vc.current_node.get_tracks(search_cls, search))[0]

            if track.is_stream:
                await interaction.followup.send("This is a stream, cannot add to queue.")
                return

            vc.queue.put(track)
            await interaction.followup.send(f"Added `{track.title}` into the queue")
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
            await interaction.followup.send(f"No tracks found for '{search}' on '{source}'.")
            return

        view = discord.ui.View().add_item(TrackSelectDropdown([track for track in tracks if not track.is_stream]))

        m: discord.WebhookMessage = await interaction.followup.send("Tracks found", view=view)  # pyright: ignore

        if await view.wait():
            await m.edit(content="Timed out! Please try again!", view=None)
            return

        drop: Union[discord.ui.Item[discord.ui.View], TrackSelectDropdown] = view.children[0]
        vals = drop.values  # pyright: ignore

        if not vals:
            await m.edit(content="No track selected!", view=None)
            return

        if "Nope" in vals:
            await m.edit(content="All choices cleared", view=None)
            return

        soon_to_add_queue: List[wavelink.Playable] = []

        for val in vals:
            idx = int(val)
            soon_to_add_queue.append(tracks[idx])

        vc.queue.extend(soon_to_add_queue)
        await m.edit(content=f"Added {len(vals)} tracks into the queue", view=None)

        embeds = self.generate_embeds_from_tracks(soon_to_add_queue)
        self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds))

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.describe(url="Playlist URL", source="Source to get playlist")
    @app_commands.choices(source=[Choice(name=k, value=k) for k in music_default_sources])
    async def add_playlist(self, interaction: discord.Interaction, url: str, source: str = "youtube"):
        """Add track(s) from playlist to queue"""
        await interaction.response.defer()

        tracks: Optional[
            Union[
                List[wavelink.YouTubeTrack],
                List[wavelink.YouTubeMusicTrack],
                List[spotify.SpotifyTrack],
                List[wavelink.SoundCloudTrack],
                List[Type[wavelink.tracks.Playable]],
            ]
        ] = []

        if source == "youtube":
            try:
                pl = (await wavelink.YouTubePlaylist.search(url)).tracks  # pyright: ignore
            except wavelink.NoTracksError:
                pl = await wavelink.YouTubeTrack.search(url)
            tracks = pl
        elif source == "ytmusic":
            tracks = await wavelink.YouTubeMusicTrack.search(url)
        elif source == "spotify":
            tracks = await spotify.SpotifyTrack.search(url, type=spotify.SpotifySearchType.playlist)  # pyright: ignore
        elif source == "soundcloud":
            tracks = await wavelink.SoundCloudTrack.search(url)

        if not tracks:
            await interaction.followup.send(f"No tracks found for {url} on {source}, have you checked your URL?")
            return

        player: wavelink.Player = interaction.guild.voice_client  # pyright: ignore
        accepted_tracks = [track for track in tracks if not track.is_stream]  # pyright: ignore
        player.queue.extend(accepted_tracks)  # pyright: ignore
        await interaction.followup.send(f"Added {len(tracks)} track(s) from {url} to the queue")

        embeds = self.generate_embeds_from_tracks(accepted_tracks)  # pyright: ignore
        self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds))

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(before="Old position", after="New position")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.queue_has_element)
    async def move(self, interaction: discord.Interaction, before: Range[int, 1], after: Range[int, 1]):
        """Move track to new position"""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        int_queue = vc.queue._queue
        queue_length = len(int_queue)

        if not (before != after and 1 <= before <= queue_length and 1 <= after <= queue_length):
            await interaction.followup.send(f"Invalid position(s): `{before} -> {after}`")
            return

        temp = int_queue[before - 1]
        del int_queue[before - 1]
        int_queue.insert(after - 1, temp)

        await interaction.followup.send(f"Moved track #{before} to #{after}")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(pos="Current position", diff="Relative difference")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.queue_has_element)
    async def move_relative(self, interaction: discord.Interaction, pos: Range[int, 1], diff: int):
        """Move track to new position using relative difference"""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        int_queue = vc.queue._queue
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

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.queue_has_element)
    @app_commands.describe(
        pos1="Position of first track",
        pos2="Position of second track",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def swap(self, interaction: discord.Interaction, pos1: Range[int, 1], pos2: Range[int, 1]):
        """Swap two tracks."""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore
        q = vc.queue._queue
        q_length = len(q)

        if not (1 <= pos1 <= q_length and 1 <= pos2 <= q_length):
            await interaction.followup.send(f"Invalid position(s): ({pos1}, {pos2})")
            return

        q[pos1 - 1], q[pos2 - 1] = (
            q[pos2 - 1],
            q[pos1 - 1],
        )

        await interaction.followup.send(f"Swapped track #{pos1} and #{pos2}")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.queue_has_element)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shuffle(self, interaction: discord.Interaction):
        """Shuffle the queue"""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        random.shuffle(vc.queue._queue)
        await interaction.followup.send("Shuffled the queue")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.queue_has_element)
    async def clear(self, interaction: discord.Interaction):
        """Clear the queue, using vote system."""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        if await VoteMenu("clear", "queue", interaction, vc).start():
            vc.queue.clear()
            await interaction.followup.send(content="Cleared the queue")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicLavalinkCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicLavalinkCogCheck.queue_has_element)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def force_clear(self, interaction: discord.Interaction):
        """Force clear the queue, guild managers only."""
        await interaction.response.defer()

        vc: wavelink.Player = interaction.guild.voice_client  # pyright: ignore

        vc.queue.clear()
        await interaction.followup.send("Cleared the queue")


async def setup(bot: Nameless):
    if (lvl := getattr(NamelessConfig, "LAVALINK", None)) and lvl.get("nodes", []):
        await bot.add_cog(MusicLavalinkCog(bot))
        logging.info("%s cog added!", __name__)
    else:
        raise commands.ExtensionFailed(__name__, ValueError("Lavalink options are not properly provided"))


async def teardown(bot: Nameless):
    await bot.remove_cog("MusicLavalinkCog")
    logging.warning("%s cog removed!", __name__)
