import collections
import datetime
import logging
import math
import random
from typing import List, Any, Type

import DiscordUtils
import discord
import discord.utils as d_utils
import wavelink
from discord import ClientException, app_commands
from discord.app_commands import Choice
from discord.ext import commands
from wavelink.ext import spotify

import global_deps
from config import Config

__all__ = ["MusicCog"]


class VoteMenuView(discord.ui.View):
    __slots__ = ("user", "value")

    def __init__(self):
        super().__init__(timeout=15)
        self.user = None
        self.value = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def approve(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.value = True
        self.user = interaction.user.mention

        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
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
        content: (wavelink.Track, str),
        ctx: commands.Context,
        voice_client: discord.VoiceClient,
    ):
        self.action = action
        self.content = (
            f"{content.title[:50]}..."
            if isinstance(content, wavelink.Track)
            else content
        )
        self.ctx = ctx
        self.max_vote_user = math.ceil(len(voice_client.channel.members) / 2)
        self.total_vote = 1

        self.approve_member = [ctx.author.mention]
        self.disapprove_member = []

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
                self.approve_member.append(menu.user)
            else:
                self.disapprove_member.append(menu.user)

        if len(self.disapprove_member) > len(self.approve_member):
            await message.edit(
                content=f"Not enough votes to {self.action}!", embed=None, view=None
            )
            return False
        else:
            await message.edit(
                content=f"{self.action.title()} {self.content}!", embed=None, view=None
            )
            return True

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
                description=track.uri[:100],
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
        v: discord.ui.View = self.view
        v.stop()


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot
        bot.loop.create_task(self.connect_nodes())

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
                if Config.LAVALINK["spotify"]
                and Config.LAVALINK["spotify"]["client_id"]
                and Config.LAVALINK["spotify"]["client_secret"]
                else None,
            )

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        logging.info(f"Node {node.identifier} ({node.host}) is ready!")

    @commands.Cog.listener()
    async def on_wavelink_track_start(
        self, player: wavelink.Player, track: wavelink.Track
    ):
        chn = player.guild.get_channel(player.trigger_channel_id)  # type: ignore
        if not player.loop_sent and player.play_now_allowed:  # type: ignore
            await chn.send(
                f"Playing: **{track.title}** from **{track.author}** ({track.uri})"
            )

    @commands.Cog.listener()
    async def on_wavelink_track_end(
        self, player: wavelink.Player, track: wavelink.Track, reason: str
    ):
        if player.stop_sent:  # type: ignore
            return

        chn = player.guild.get_channel(player.trigger_channel_id)  # type: ignore

        try:
            if player.loop_sent and not player.skip_sent:  # type: ignore
                pass
            else:
                player.skip_sent = False
                track = await player.queue.get_wait()

            await self.__internal_play2(player, track.uri)
        except wavelink.QueueEmpty:
            await chn.send("The queue is empty now")

    async def __internal_play(
        self, ctx: commands.Context, url: str, is_radio: bool = False
    ):
        vc: wavelink.Player = ctx.voice_client  # type: ignore

        # Props set
        vc.skip_sent = False
        vc.stop_sent = False
        vc.loop_sent = False
        vc.play_now_allowed = True
        vc.trigger_channel_id = ctx.channel.id

        if is_radio:
            dbg, _ = global_deps.crud_database.get_or_create_guild_record(ctx.guild)
            dbg.radio_start_time = datetime.datetime.now()
            global_deps.crud_database.save_changes(guild_record=dbg)

        await ctx.send("Initiating playback")
        await self.__internal_play2(vc, url)

    async def __internal_play2(self, vc: wavelink.Player, url: str):
        track = await vc.node.get_tracks(cls=wavelink.Track, query=url)
        await vc.play(track[0])

    @commands.hybrid_group(fallback="radio")
    @app_commands.describe(url="Radio url")
    @app_commands.guilds(*Config.GUILD_IDs)
    async def music(self, ctx: commands.Context, url: str):
        """Play a radio"""
        await ctx.defer()
        await self.__internal_play(ctx, url, True)

    @music.command()
    async def connect(self, ctx: commands.Context):
        """Connect to your current voice channel"""
        await ctx.defer()

        try:
            await ctx.author.voice.channel.connect(cls=wavelink.Player, self_deaf=True)  # type: ignore
            await ctx.send("Connected to your current voice channel")
        except ClientException:
            await ctx.send("Already connected")

    @music.command()
    async def disconnect(self, ctx: commands.Context):
        """Disconnect from my current voice channel"""
        await ctx.defer()

        try:
            await ctx.voice_client.disconnect(force=True)
            await ctx.send("Disconnected from my own voice channel")
        except AttributeError:
            await ctx.send("Already disconnected")

    @music.command()
    async def loop(self, ctx: commands.Context):
        """Toggle loop playback of current track"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        vc.loop_sent = not vc.loop_sent

        await ctx.send(f"Loop set to {'on' if vc.loop_sent else 'off'}")

    @music.command()
    async def pause(self, ctx: commands.Context):
        """Pause current playback"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if vc.is_paused():
            await ctx.send("Already paused")
            return

        await vc.pause()
        await ctx.send("Paused")

    @music.command()
    async def resume(self, ctx: commands.Context):
        """Resume current playback, if paused"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if not vc.is_paused():
            await ctx.send("Already resuming")
            return

        await vc.resume()
        await ctx.send("Resuming")

    @music.command()
    async def stop(self, ctx: commands.Context):
        """Stop current playback."""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore
        vc.stop_sent = True

        await vc.stop()
        await ctx.send("Stopping")

    @music.command()
    async def play_queue(self, ctx: commands.Context):
        """Play entire queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if vc.queue.is_empty:
            await ctx.send("Queue is empty")
            return

        track = vc.queue.get()
        await self.__internal_play(ctx, track.uri)

    @music.command()
    async def skip(self, ctx: commands.Context):
        """Skip a song. Remind you that the loop effect DOES NOT apply"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore
        track: wavelink.Track = vc.track  # type: ignore

        if await VoteMenu("skip", track, ctx, vc).start():  # type: ignore
            vc.skip_sent = True
            await vc.stop()

    @music.command()
    @app_commands.describe(
        pos="Position to seek to in milliseconds, defaults to run from start"
    )
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def seek(self, ctx: commands.Context, pos: int = 0):
        """Seek to a position in a track"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore
        track: wavelink.Track = vc.track  # type: ignore

        pos = pos if pos else 0

        if not (0 <= pos / 1000 <= track.length):
            await ctx.send("Invalid position to seek")
            return

        if await VoteMenu("seek", track, ctx, vc).start():  # type: ignore
            await vc.seek(pos)
            delta_pos = datetime.timedelta(milliseconds=pos)
            await ctx.send(f"Seek to position {delta_pos}")

    @music.command()
    @app_commands.describe(
        segment="Segment to seek (from 0 to 10, respecting to 0%, 10%, ..., 100%), defaults to 0"
    )
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def seek_segment(self, ctx: commands.Context, segment: int = 0):
        """Seek to a segment in a track"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore
        track: wavelink.Track = vc.track  # type: ignore

        if not (0 <= segment <= 10):
            await ctx.send("Invalid segment")
            return

        if await VoteMenu("seek_segment", track, ctx, vc).start():  # type: ignore
            pos = int(float(track.length * (segment * 10) / 100) * 1000)
            await vc.seek(pos)
            delta_pos = datetime.timedelta(milliseconds=pos)
            await ctx.send(f"Seek to segment #{segment}: {delta_pos}")

    @music.command()
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle_play_now(self, ctx: commands.Context):
        """Toggle 'Now playing' message delivery"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore
        vc.play_now_allowed = not vc.play_now_allowed  # type: ignore

        await ctx.send(
            f"'Now playing' delivery is now {'on' if vc.play_now_allowed else 'off'}"
        )

    @music.command()
    async def now_playing(self, ctx: commands.Context):
        """Check now playing song"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore
        track: wavelink.Track = vc.track  # type: ignore

        if not track:
            await ctx.send("No track is played")
            return

        is_stream = track.is_stream()
        dbg, _ = global_deps.crud_database.get_or_create_guild_record(ctx.guild)

        await ctx.send(
            embeds=[
                discord.Embed(
                    timestamp=datetime.datetime.now(), color=discord.Color.orange()
                )
                .set_author(name="Now playing track", icon_url=ctx.author.avatar.url)
                .add_field(
                    name="Title",
                    value=d_utils.escape_markdown(track.title),
                    inline=False,
                )
                .add_field(name="Author", value=d_utils.escape_markdown(track.author))
                .add_field(name="Source", value=d_utils.escape_markdown(track.uri))
                .add_field(
                    name="Playtime" if is_stream else "Position",
                    value=str(
                        datetime.datetime.now().astimezone() - dbg.radio_start_time
                        if is_stream
                        else f"{datetime.timedelta(seconds=vc.position)}/{datetime.timedelta(seconds=track.length)}"
                    ),
                )
                .add_field(name="Looping", value="This is a stream" if is_stream else vc.loop_sent)  # type: ignore
                .add_field(name="Paused", value=vc.is_paused())
            ]
        )

    @music.group(fallback="view")
    async def queue(self, ctx: commands.Context):
        """View current queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if vc.queue.is_empty:
            await ctx.send("The queue is empty")
            return

        txt = ""
        copycat = vc.queue.copy()
        idx = 1
        embeds = []

        try:
            while track := copycat.get():
                upcoming = (
                    f"{idx} - "
                    f"[{d_utils.escape_markdown(track.title)} by {d_utils.escape_markdown(track.author)}]"
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
        except wavelink.QueueEmpty:
            # Nothing else in queue
            pass
        finally:
            # Add the last bits
            embeds.append(
                discord.Embed(
                    title="Tracks currently in queue",
                    color=discord.Color.orange(),
                    description=txt,
                )
            )

        p = DiscordUtils.Pagination.AutoEmbedPaginator(ctx)
        await p.run(embeds)

    @queue.command()
    @app_commands.describe(
        indexes="The indexes to remove (1-based), separated by comma"
    )
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete(self, ctx: commands.Context, indexes: str):
        """Remove tracks from queue atomically (remove as much as possible)"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore

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
    @app_commands.describe(search="Search query", source="Source to search")
    @app_commands.choices(
        source=[
            Choice(name=k, value=k)
            for k in ["youtube", "soundcloud", "spotify", "ytmusic"]
        ]
    )
    async def add(self, ctx: commands.Context, search: str, source: str = "youtube"):
        """Add selected track(s) to queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore
        search_cls: Type[wavelink.SearchableTrack] = wavelink.YouTubeTrack

        if source == "ytmusic":
            search_cls = wavelink.YouTubeMusicTrack
        elif source == "spotify":
            search_cls = spotify.SpotifyTrack
        elif source == "soundcloud":
            search_cls = wavelink.SoundCloudTrack

        tracks = await search_cls.search(query=search)

        if not tracks:
            await ctx.send(
                f"No tracks found for {search} on {source}, have you tried passing search query instead?"
            )
            return

        view = discord.ui.View()
        view.add_item(TrackPickDropdown(tracks))

        m = await ctx.send("Tracks found", view=view)

        if await view.wait():
            await m.edit(content="Timed out!", view=None, delete_after=30)
            return

        drop: TrackPickDropdown = view.children[0]  # type: ignore
        vals = drop.values

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

    @queue.command()
    @app_commands.describe(url="Playlist URL", source="Source to get playlist")
    @app_commands.choices(
        source=[
            Choice(name=k, value=k)
            for k in ["youtube", "soundcloud", "spotify", "ytmusic"]
        ]
    )
    async def add_playlist(
        self, ctx: commands.Context, url: str, source: str = "youtube"
    ):
        """Add track(s) from playlist to queue"""
        await ctx.defer()

        tracks: List[wavelink.SearchableTrack] = []

        if source == "youtube":
            tracks = (await wavelink.YouTubePlaylist.search(query=url)).tracks
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

        player: wavelink.Player = ctx.voice_client  # type: ignore
        player.queue.extend(tracks)

        await ctx.send(f"Added {len(tracks)} track(s) from {url} to the queue")

    @queue.command()
    @app_commands.describe(before="Old position", after="New position")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def move(self, ctx: commands.Context, before: int, after: int):
        """Move track to new position"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore

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
    @app_commands.describe(pos="Current position", diff="Relative difference")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def move_relative(self, ctx: commands.Context, pos: int, diff: int):
        """Move track to new position using relative difference"""
        await self.move(ctx, pos, pos + diff)

    @queue.command()
    @app_commands.describe(
        pos1='First track positions, separated by comma, covered by pair of "',
        pos2='Second track positions, separated by comma, covered by pair of "',
    )
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def swap(self, ctx: commands.Context, pos1: str, pos2: str):
        """Swap two or more tracks. "swap "1,2,3" "4,5,6" will swap 1 with 4, 2 with 5, 4 with 6"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore
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
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shuffle(self, ctx: commands.Context):
        """Shuffle the queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        random.shuffle(vc.queue._queue)
        await ctx.send("Shuffled the queue")

    @queue.command()
    async def clear(self, ctx: commands.Context):
        """Clear the queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if await VoteMenu("clear", "queue", ctx, vc).start():  # type: ignore
            vc.queue.clear()
            await ctx.send("Cleared the queue")

    @queue.command()
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def force_clear(self, ctx: commands.Context):
        """Clear the queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        vc.queue.clear()
        await ctx.send("Cleared the queue")

    @music.before_invoke
    @connect.before_invoke
    @loop.before_invoke
    @pause.before_invoke
    @resume.before_invoke
    @stop.before_invoke
    @play_queue.before_invoke
    @skip.before_invoke
    @seek.before_invoke
    @seek_segment.before_invoke
    @toggle_play_now.before_invoke
    @now_playing.before_invoke
    @queue.before_invoke
    @delete.before_invoke
    @add.before_invoke
    @add_playlist.before_invoke
    @shuffle.before_invoke
    @clear.before_invoke
    @force_clear.before_invoke
    @move.before_invoke
    @move_relative.before_invoke
    @swap.before_invoke
    async def user_in_voice_before_invoke(self, ctx: commands.Context):
        if not ctx.author.voice:
            await ctx.send("You need to be in a voice channel")
            raise commands.CommandError("User did not join voice")

    @music.before_invoke
    @loop.before_invoke
    @pause.before_invoke
    @resume.before_invoke
    @stop.before_invoke
    @play_queue.before_invoke
    @skip.before_invoke
    @seek.before_invoke
    @seek_segment.before_invoke
    @toggle_play_now.before_invoke
    @now_playing.before_invoke
    @queue.before_invoke
    @delete.before_invoke
    @add.before_invoke
    @add_playlist.before_invoke
    @shuffle.before_invoke
    @clear.before_invoke
    @force_clear.before_invoke
    @move.before_invoke
    @move_relative.before_invoke
    @swap.before_invoke
    async def bot_in_voice_before_invoke(self, ctx: commands.Context):
        if not ctx.voice_client:
            await ctx.send("I need to be in a voice channel")
            raise commands.CommandError("Bot did not join voice")

    @music.before_invoke
    @play_queue.before_invoke
    async def no_play_anything_before_invoke(self, ctx: commands.Context):
        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if vc and vc.is_playing():
            await ctx.send("I am playing something else.")
            raise commands.CommandError("Something else is being played")

    @loop.before_invoke
    @pause.before_invoke
    @resume.before_invoke
    @stop.before_invoke
    @skip.before_invoke
    @seek.before_invoke
    @seek_segment.before_invoke
    @now_playing.before_invoke
    async def have_track_before_invoke(self, ctx: commands.Context):
        vc: wavelink.Player = ctx.voice_client  # type: ignore
        track: wavelink.Track = vc.track  # type: ignore

        if not track:
            await ctx.send("Nothing is being played right now")
            raise commands.CommandError("No track is being played")

    @queue.before_invoke
    @delete.before_invoke
    @shuffle.before_invoke
    @clear.before_invoke
    @force_clear.before_invoke
    @move.before_invoke
    @move_relative.before_invoke
    @swap.before_invoke
    async def queue_exists_before_invoke(self, ctx: commands.Context):
        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if vc.queue.is_empty:
            await ctx.send("Queue is empty")
            raise commands.CommandError("Queue is empty")

    @skip.before_invoke
    @loop.before_invoke
    @seek.before_invoke
    @seek_segment.before_invoke
    async def no_stream_before_invoke(self, ctx: commands.Context):
        vc: wavelink.Player = ctx.voice_client  # type: ignore
        track: wavelink.Track = vc.track  # type: ignore

        if track and track.is_stream():
            await ctx.send("Stream is not allowed on this command")
            raise commands.CommandError("Stream is not allowed")
