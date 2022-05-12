import datetime
import logging
import random
from typing import List, Any, Type

import discord
import wavelink
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from wavelink.ext import spotify

import globals
from config import Config


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

    def callback(self, _: discord.Interaction) -> Any:
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
                await player.play(track)
            else:
                player.skip_sent = False
                track = player.queue.get()
                await player.play(track)
                await chn.send(
                    f"Playing: **{track.title}** from **{track.author}** ({track.uri})"
                )
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
        vc.trigger_channel_id = ctx.channel.id

        if is_radio:
            dbg, _ = globals.crud_database.get_or_create_guild_record(ctx.guild)
            dbg.radio_start_time = datetime.datetime.now()
            globals.crud_database.save_changes(guild_record=dbg)

        await ctx.send("Initiating playback")

        track = await vc.node.get_tracks(cls=wavelink.Track, query=url)
        self.bot.loop.create_task(vc.play(track[0]))

    @commands.hybrid_group(fallback="radio")
    @app_commands.describe(url="Radio url")
    @app_commands.guilds(*Config.GUILD_IDs)
    async def music(self, ctx: commands.Context, url: str):
        """Play a radio"""
        await ctx.defer()

        await ctx.author.voice.channel.connect(cls=wavelink.Player)  # type: ignore
        await self.__internal_play(ctx, url, True)

    @music.command()
    async def connect(self, ctx: commands.Context):
        """Connect to your current voice channel"""
        await ctx.defer()

        await ctx.author.voice.channel.connect(cls=wavelink.Player)  # type: ignore
        await ctx.send("Connected to your current voice channel")

    @music.command()
    async def disconnect(self, ctx: commands.Context):
        """Disconnect from my current voice channel"""
        await ctx.defer()

        await ctx.voice_client.disconnect(force=True)
        await ctx.send("Disconnected from my own voice channel")

    @music.command()
    async def loop(self, ctx: commands.Context):
        """Toggle loop playback of current track"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore
        track: wavelink.Track = vc.track  # type: ignore
        if track.is_stream():
            await ctx.send("Can not loop a stream, sorry")
            return

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
        track: wavelink.Track = vc.track  # type: ignore

        if track and track.is_stream():
            await ctx.send("Currently playing a stream, consider stopping it")
            return

        if not vc.queue:
            await ctx.send("Queue is empty")
            return

        track = vc.queue.get()

        await self.__internal_play(ctx, track.uri)

    @music.command()
    async def skip(self, ctx: commands.Context):
        """Skip a song. Remind you that the loop effect DOES NOT apply."""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore
        track: wavelink.Track = vc.track  # type: ignore

        if not track:
            await ctx.send("No track is played")
            return

        if track.is_stream():
            await ctx.send("Can not skip a stream")
            return

        vc.skip_sent = True
        await vc.stop()
        await ctx.send("Skipping.")

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
        dbg, _ = globals.crud_database.get_or_create_guild_record(ctx.guild)

        await ctx.send(
            embeds=[
                discord.Embed(
                    timestamp=datetime.datetime.now(), color=discord.Color.orange()
                )
                .set_author(name="Now playing track", icon_url=ctx.author.avatar.url)
                .add_field(
                    name="Title",
                    value=discord.utils.escape_markdown(track.title),
                    inline=False,
                )
                .add_field(
                    name="Author", value=discord.utils.escape_markdown(track.author)
                )
                .add_field(
                    name="Source", value=discord.utils.escape_markdown(track.uri)
                )
                .add_field(
                    name="Playtime" if is_stream else "Position",
                    value=str(
                        datetime.datetime.now().astimezone() - dbg.radio_start_time
                    ),
                )
                .add_field(
                    name="Looping", value="This is a stream" if is_stream else vc.loop_sent  # type: ignore
                )
                .add_field(name="Paused", value=vc.is_paused())
            ]
        )

    @music.group(fallback="view")
    async def queue(self, ctx: commands.Context):
        """View current queue"""
        pass

    @queue.command()
    @app_commands.describe(search="Search query", source="Source to search")
    @app_commands.choices(
        source=[
            Choice(name=k, value=k)
            for k in ["youtube", "soundcloud", "spotify", "ytmusic"]
        ]
    )
    async def enqueue(
        self, ctx: commands.Context, search: str, source: str = "youtube"
    ):
        """Enqueue a track"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore
        search_cls: Type[wavelink.SearchableTrack] = wavelink.YouTubeTrack

        match source:
            case "ytmusic":
                search_cls = wavelink.YouTubeMusicTrack
            case "spotify":
                search_cls = spotify.SpotifyTrack
            case "soundcloud":
                search_cls = wavelink.SoundCloudTrack

        tracks = await search_cls.search(query=search)

        if not tracks:
            await ctx.send(f"No tracks found for {search} on {source}")
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
    @app_commands.choices(source=[
            Choice(name=k, value=k)
            for k in ["youtube", "soundcloud", "spotify", "ytmusic"]
        ])
    async def enqueue_playlist(self, ctx: commands.Context, search: str, source: str = "youtube"):
        """Add tracks from playlist to queue"""
        await ctx.defer()

        tracks: List[wavelink.SearchableTrack] = []

        match source:
            case "ytmusic":
                tracks = await wavelink.YouTubePlaylist.search(query=search)
            case "spotify":
                tracks = await spotify.SpotifyTrack.search(query=search, type=spotify.SpotifySearchType.playlist)
            case "soundcloud":
                tracks = await wavelink.SoundCloudTrack.search(query=search)




    @queue.command()
    @commands.has_guild_permissions(manage_guild=True)
    async def shuffle(self, ctx: commands.Context):
        """Shuffle the queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if not vc.queue:
            await ctx.send("There is nothing in queue")
            return

        random.shuffle(vc.queue)
        await ctx.send("Shuffled the queue")

    @queue.command()
    @commands.has_guild_permissions(manage_guild=True)
    async def clear(self, ctx: commands.Context):
        """Clear the queue"""
        await ctx.defer()

        vc: wavelink.Player = ctx.voice_client  # type: ignore

        if not vc.queue:
            await ctx.send("The queue is already empty")
            return

        vc.queue = wavelink.WaitQueue()
        await ctx.send("Shuffled the queue")

    @music.before_invoke
    @queue.before_invoke
    @connect.before_invoke
    @stop.before_invoke
    @resume.before_invoke
    @pause.before_invoke
    @loop.before_invoke
    @now_playing.before_invoke
    @play_queue.before_invoke
    @enqueue.before_invoke
    @enqueue_playlist.before_invoke
    @clear.before_invoke
    @shuffle.before_invoke
    async def user_in_voice_before_invoke(self, ctx: commands.Context):
        if not ctx.author.voice:
            await ctx.send("You need to be in a voice channel")

    @music.before_invoke
    @queue.before_invoke
    @disconnect.before_invoke
    @stop.before_invoke
    @resume.before_invoke
    @pause.before_invoke
    @loop.before_invoke
    @now_playing.before_invoke
    @play_queue.before_invoke
    @enqueue.before_invoke
    @clear.before_invoke
    @shuffle.before_invoke
    async def bot_in_voice_before_invoke(self, ctx: commands.Context):
        if not ctx.voice_client:
            await ctx.send("I need to be in a voice channel")
