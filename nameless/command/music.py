import asyncio
import datetime
import logging
from typing import Literal, cast, final, overload

import discord
import wavelink
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown

from nameless.config import nameless_config
from nameless.custom.player import CustomPlayer, TrackDropdown
from nameless.custom.player.settings import sponsorblock_make
from nameless.custom.player.settings.filters import filter_make

# from ..custom.player.settings.sponsorblock_settings import SponsorBlockSettings
from nameless.custom.ui import NamelessPaginatedView
from nameless.nameless import Nameless

__all__ = ["MusicCommands"]

SOURCE_MAPPING = {
    "youtube": wavelink.TrackSource.YouTube,
    "soundcloud": wavelink.TrackSource.SoundCloud,
    "ytmusic": wavelink.TrackSource.YouTubeMusic,
}


@final
class MusicCommands(commands.GroupCog, name="music"):
    __slots__ = ("bot", "is_ready", "nodes", "_connect_task")

    def __init__(self, bot: Nameless):
        self.bot = bot
        self.is_ready = asyncio.Event()

        self.nodes = [
            wavelink.Node(uri=node["uri"], password=node["password"], client=self.bot)
            for node in nameless_config.get("wavelinks", {})
        ]

        self._connect_task = self.bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        """Connect to lavalink nodes."""
        logging.info(
            "Wait for discord connection to be ready before connect to Lavalink..."
        )
        await self.bot.wait_until_ready()
        logging.info("Discord connection is ready. Connecting to Lavalink nodes...")
        await wavelink.Pool.connect(
            client=self.bot, nodes=self.nodes, cache_capacity=100
        )
        if self._connect_task:
            self._connect_task = None

    @commands.Cog.listener()
    async def on_command_error(
        self, ctx: commands.Context[Nameless], error: commands.CommandError
    ):
        if isinstance(error, commands.CheckFailure | commands.UserInputError):
            logging.warning(
                '%s: command_name=%s args=%s kwargs=%s author=%s error="%s"',
                error.__class__.__name__,
                ctx.command.name,  # pyright: ignore[reportOptionalMemberAccess]
                ctx.args if ctx.args else "None",
                ctx.kwargs if ctx.kwargs else "None",
                ctx.author.name if ctx.author else "Unknown",
                error,
            )
            await ctx.send(str(error))
        elif isinstance(error, commands.CommandNotFound):
            pass  # Ignore this error
        else:
            raise error

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        logging.debug(
            "LavalinkNode {%s} (%s) is ready!",
            payload.node.identifier,
            payload.node.uri,
        )
        # Notify that the node is ready.
        self.is_ready.set()

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player: CustomPlayer = cast(CustomPlayer, payload.player)
        track = payload.track

        if not player.guild:
            logging.warning(
                "Player is not connected. Or we have been banned from the guild!"
            )
            return

        chn = player.guild.get_channel(player.trigger_channel_id)
        if not isinstance(chn, discord.abc.Messageable):
            return

        can_send = (
            player.play_now_allowed and player.queue.mode is not wavelink.QueueMode.loop
        )

        if not can_send:
            return

        embed = self.generate_embed_from_track(player, track, self.bot.user)

        await chn.send(embed=embed)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: CustomPlayer):
        await player.channel.send("I have been inactive for a while. Goodbye!")
        await player.disconnect()

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, _: discord.VoiceState, after: discord.VoiceState
    ):
        if (
            self.bot.user is not None
            and member.id == self.bot.user.id
            and not after.deaf
        ):
            await member.edit(deafen=True)

    @commands.Cog.listener()
    async def on_wavelink_extra_event(self, payload: wavelink.ExtraEventPayload):
        logging.warning("Extra event: %s", payload.data)

    @staticmethod
    def resolve_artist_name(name: str) -> str:
        if not name:
            return "N/A"
        name = escape_markdown(name, as_needed=True)
        return name.removesuffix(" - Topic")

    def generate_embeds_from_tracks(
        self,
        tracks: wavelink.Queue | list[wavelink.Playable] | wavelink.Playlist | None,
        embed_title: str = "Tracks currently in queue",
    ) -> list[discord.Embed]:
        """Generate embeds from supported track list types."""
        txt = ""
        embeds: list[discord.Embed] = []
        track_list: list[wavelink.Playable] = []

        if isinstance(tracks, wavelink.Queue | wavelink.Playlist):
            track_list = list(tracks)
        elif isinstance(tracks, list):
            track_list = tracks
        else:
            return []

        for i, track in enumerate(track_list, start=1):
            upcoming = (
                f"{i} - "
                f"[{track.title} by {self.resolve_artist_name(track.author)}]"
                f"({track.uri or 'N/A'})\n"
            )

            if len(txt) + len(upcoming) > 2048:
                embeds.append(
                    discord.Embed(
                        title=embed_title, color=discord.Color.orange(), description=txt
                    )
                )
                txt = upcoming
            else:
                txt += upcoming

        embeds.append(
            discord.Embed(
                title=embed_title, color=discord.Color.orange(), description=txt
            )
        )

        return embeds

    def generate_embed_from_track(
        self,
        player: CustomPlayer,
        track: wavelink.Playable | None,
        user: discord.User | discord.Member | discord.ClientUser | None,
    ) -> discord.Embed:
        assert user is not None
        assert track is not None

        # thumbnail_url: str = await track. if isinstance(
        #    track, wavelink.TrackSource.YouTube
        # ) else ""

        def add_icon():
            icon = "⏸️" if player.paused else "▶️"
            if player.queue.mode == wavelink.QueueMode.loop:
                icon += "🔂"
            elif player.queue.mode == wavelink.QueueMode.loop_all:
                icon += "🔁"
            return icon

        title = add_icon()
        title += "Autoplaying" if track.recommended else "Now playing"
        title += " track" if not track.is_stream else " stream"

        embed = (
            discord.Embed(
                timestamp=datetime.datetime.now(), color=discord.Color.orange()
            )
            .set_author(
                name=f"{add_icon()} Now playing {
                    'stream' if track.is_stream else 'track'
                }",
                icon_url=user.display_avatar.url,
            )
            .add_field(name="Title", value=escape_markdown(track.title))
            .add_field(
                name="Author",
                value=self.resolve_artist_name(track.author) if track.author else "N/A",
            )
            .add_field(
                name="Source",
                value=f"[{str.title(track.source)}]({track.uri})"
                if track.uri
                else "N/A",
                inline=False,
            )
            # .add_field(
            #     name="Looping",
            #     value="This is a stream" if is_stream else vc.queue.loop
            # )
            # .add_field(name="Paused", value=vc.is_paused())
            .set_thumbnail(url=track.artwork or "")
        )

        if (
            player.queue.mode != wavelink.QueueMode.loop
            and not track.is_stream
            and bool(player.queue)
        ):
            next_tr = player.queue[0]
            embed.add_field(
                name="Next track",
                value=(
                    f"[{
                        escape_markdown(next_tr.title)
                        if next_tr.title
                        else 'Unknown title'
                    } "
                    + f"by {self.resolve_artist_name(next_tr.author)}]"
                    + f"({next_tr.uri or 'N/A'})",
                ),
            )

        return embed

    @staticmethod
    async def show_paginated_tracks(
        ctx: commands.Context[Nameless], embeds: list[discord.Embed]
    ):
        view_menu = NamelessPaginatedView(ctx, timeout=60)
        view_menu.add_pages(embeds)
        view_menu.add_predefined_buttons()
        await view_menu.start()

    @overload
    async def ensure_guild_voice_client(
        self, ctx: commands.Context[Nameless]
    ) -> CustomPlayer: ...
    @overload
    async def ensure_guild_voice_client(
        self, ctx: commands.Context[Nameless], *, auto_connect: Literal[False]
    ) -> CustomPlayer | None: ...
    @overload
    async def ensure_guild_voice_client(
        self, ctx: commands.Context[Nameless], *, auto_connect: Literal[True]
    ) -> CustomPlayer: ...

    async def ensure_guild_voice_client(
        self, ctx: commands.Context[Nameless], *, auto_connect: bool = True
    ) -> CustomPlayer | None:
        if not ctx.guild:
            await ctx.send("This command can only be used in a guild.")
            raise

        if not ctx.guild.voice_client:
            if auto_connect:
                await self.connect.invoke(ctx)
            else:
                await ctx.send("I'm not connected to a voice channel.")
                return None

        if not isinstance(ctx.guild.voice_client, CustomPlayer):
            raise ValueError("The voice client is not a CustomPlayer instance.")

        return ctx.guild.voice_client

    @commands.hybrid_command()
    @app_commands.describe(channel="Which channel to connect to.")
    async def connect(
        self,
        ctx: commands.Context[Nameless],
        channel: discord.VoiceChannel | discord.StageChannel | None = None,
    ) -> None:
        """Connect to a voice channel."""
        await ctx.defer()

        if not self.is_ready.is_set():
            await self.is_ready.wait()

        if channel is None:
            if not isinstance(ctx.author, discord.Member) or ctx.author.voice is None:
                raise commands.CheckFailure("You are not in a voice channel.")
            channel = ctx.author.voice.channel

        try:
            if channel is not None:
                await channel.connect(self_deaf=True, cls=CustomPlayer)
                voice_client = cast(CustomPlayer, ctx.guild.voice_client)  # pyright: ignore[reportOptionalMemberAccess]
                voice_client.trigger_channel_id = ctx.channel.id  # type: ignore
                # voice_client.sponsorblock_settings = (  # type: ignore
                #     await SponsorBlockSettings.get_from_database(ctx.guild)
                # )
                await ctx.send(f"Connected to {channel.name}.")
            else:
                await ctx.send("Failed to connect to the voice channel.")
        except discord.ClientException:
            await ctx.send("I'm already connected to a voice channel.")

    @commands.hybrid_command(aliases=["dc", "leave"])
    @app_commands.guild_only()
    async def disconnect(self, ctx: commands.Context[Nameless]) -> None:
        """Disconnect from the voice channel."""
        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)

        await player.disconnect()
        await ctx.send("Disconnected.")

    async def pick_track_from_results(
        self, ctx: commands.Context[Nameless], tracks: list[wavelink.Playable]
    ) -> list[wavelink.Playable]:
        if len(tracks) == 1:
            return tracks

        view = discord.ui.View().add_item(
            TrackDropdown([track for track in tracks if not track.is_stream])
        )
        m = await ctx.send("Tracks found", view=view)

        if await view.wait():
            await m.edit(content="Timed out! Please try again!", view=None)
            return []

        drop = view.children[0]
        if isinstance(drop, TrackDropdown):
            vals = drop.values
        else:
            await m.edit(content="Unexpected dropdown type!", view=None)
            return []

        if not vals:
            await m.edit(content="No tracks selected!", view=None)
            return []

        if "Nope" in vals:
            await m.edit(content="All choices cleared", view=None)
            return []

        await m.delete()

        pick_list: list[wavelink.Playable] = [tracks[int(val)] for val in vals]
        return pick_list

    class PlayFlags(commands.FlagConverter):
        position: int = 0
        origin: str = "youtube"
        reverse: bool = False

    @commands.hybrid_command(aliases=["p", "add"])
    @app_commands.guild_only()
    @app_commands.describe(
        query="Playlist URL or query search.",
        position="Position to add the playlist, '0' means at the end of queue.",
        origin="Where to search for your source, defaults to 'YouTube' origin.",
        reverse="Whether to reverse the input track list before adding to queue."
        + "Has higher precedence.",
    )
    @app_commands.choices(
        origin=[app_commands.Choice(name=k, value=k) for k in SOURCE_MAPPING]
    )
    async def play(
        self, ctx: commands.Context[Nameless], query: str, flags: PlayFlags
    ) -> None:
        """Play a song."""
        await ctx.defer()

        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)
        msg: str = ""

        tracks: wavelink.Search = await wavelink.Playable.search(
            query, source=SOURCE_MAPPING[flags.origin]
        )

        if not tracks:
            await ctx.send("No results found.")
            return

        if isinstance(tracks, wavelink.Playlist):
            soon_added = tracks.tracks
            msg = f"Added the playlist **`{tracks.name}`** ({len(tracks.tracks)} songs) to the queue."
        else:
            soon_added = await self.pick_track_from_results(ctx, tracks)
            if not soon_added:
                await ctx.send("Nothing will be added.")
                return

            msg = f"Added {len(soon_added)} track(s) to the queue."

        if flags.reverse:
            soon_added.reverse()

        if soon_added:
            embeds = self.generate_embeds_from_tracks(soon_added, embed_title=msg)
            self.bot.loop.create_task(self.show_paginated_tracks(ctx, embeds))

        position_to_add = max(flags.position, 0)

        if position_to_add == 0:
            await player.queue.put_wait(soon_added)
        else:
            player.queue._items[position_to_add:position_to_add] = soon_added  # pyright: ignore[reportPrivateUsage]

        if not player.current:
            await player.play(player.queue.get())

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def pause(self, ctx: commands.Context[Nameless]) -> None:
        """Pause the current song."""
        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)

        if player.paused:
            await ctx.send("The player is already paused.")
            return

        await player.pause(True)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def resume(self, ctx: commands.Context[Nameless]) -> None:
        """Resume the current song."""
        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)

        if not player.paused:
            await ctx.send("The player is already playing.")
            return

        await player.pause(False)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def stop(self, ctx: commands.Context[Nameless]) -> None:
        """Stop and pause the current song."""
        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)

        if not player.playing:
            await ctx.send("The player is already stopped.")
            return

        await player.stop()
        await player.pause(True)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def skip(self, ctx: commands.Context[Nameless]) -> None:
        """Skip the current song."""
        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)

        if not player.playing:
            await ctx.send("The player is not playing.")
            return

        await player.skip()
        await ctx.send("Skipped.")

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def queue(self, ctx: commands.Context[Nameless]) -> None:
        """Show the current queue."""
        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)

        if not player.queue and not player.auto_queue:
            await ctx.send("The queue is empty.")
            return

        embeds = [
            *self.generate_embeds_from_tracks(player.queue),
            *self.generate_embeds_from_tracks(
                player.auto_queue, "Autoplay track queue"
            ),
        ]
        await self.show_paginated_tracks(ctx, embeds)

    @commands.hybrid_command(aliases=["np", "nowplaying", "playing"])
    @app_commands.guild_only()
    async def current(self, ctx: commands.Context[Nameless]) -> None:
        """Show the current song."""
        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)
        track: wavelink.Playable | None = player.current  # type: ignore

        if not track:
            await ctx.send("No track is playing.")
            return

        await ctx.send(embed=self.generate_embed_from_track(player, track, ctx.author))

    @commands.hybrid_command(aliases=["random"])
    @app_commands.guild_only()
    async def shuffle(self, ctx: commands.Context[Nameless]) -> None:
        """Shuffle the current queue."""
        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)

        if not player.queue:
            await ctx.send("The queue is empty.")
            return

        player.queue.shuffle()

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def remove(self, ctx: commands.Context[Nameless], index: int) -> None:
        """Remove a song from the queue."""
        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)

        if not player.queue:
            await ctx.send("The queue is empty.")
            return

        if index < 1 or index > len(player.queue):
            await ctx.send("Invalid index.")
            return

        player.queue.remove(player.queue[index - 1])

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def clear(self, ctx: commands.Context[Nameless]) -> None:
        """Clear the queue."""
        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)

        if not player.queue:
            await ctx.send("The queue is empty.")
            return

        player.queue.clear()

    @commands.hybrid_command(aliases=["vol"])
    @app_commands.guild_only()
    @app_commands.describe(volume="Volume to set, between 0 and 200.")
    async def volume(self, ctx: commands.Context[Nameless], volume: int) -> None:
        """Change the volume."""
        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)

        if volume < 0 or volume > 200:
            await ctx.send("Invalid volume.")
            return

        await player.set_volume(volume)

    class SeekFlags(commands.FlagConverter):
        milliseconds: int = commands.flag(
            default=0, description="Milisecond component of position", aliases=["ms"]
        )
        seconds: int = commands.flag(
            default=0,
            description="Second component of position",
            positional=True,
            aliases=["s"],
        )
        minutes: int = commands.flag(
            default=0, description="Minute component of position", aliases=["m"]
        )
        hours: int = commands.flag(
            default=0, description="Hour component of position", aliases=["h"]
        )
        percent: float = commands.flag(
            default=0.0,
            description="Percentage of track, HAS THE HIGHEST OF PRECEDENCE.",
            aliases=["p"],
        )

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def seek(self, ctx: commands.Context[Nameless], *, flags: SeekFlags) -> None:
        """Seek to a position in the current song."""
        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)
        track: wavelink.Playable | None = player.current  # type: ignore

        if not player or not track:
            await ctx.send("No track is playing.")
            return

        if not track.is_seekable:
            await ctx.send("This track is not seekable!")
            return

        # In miliseconds.
        final_position = 0

        if flags.percent:
            final_position = int(track.length * (flags.percent / 100) / 100)
        else:
            total_seconds = flags.hours * 3600 + flags.minutes * 60 + flags.seconds
            final_position = total_seconds * 1000 + flags.milliseconds

        await player.seek(final_position)

        # embed = self.ge(player, track, interaction.user, dbg)
        await ctx.send(
            content="Seeked",
            embed=self.generate_embed_from_track(player, track, ctx.author),
        )

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def repopulate_autoqueue(self, ctx: commands.Context[Nameless]):
        """Repopulate autoplay queue based on current song(s)."""
        await ctx.defer()

        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)

        if player.autoplay != wavelink.AutoPlayMode.enabled:
            await ctx.send("Seems like autoplay is disabled.")
            return

        player.auto_queue.clear()
        await player._do_recommendation()  # pyright: ignore[reportPrivateUsage]

        await ctx.send("Repopulated autoplay queue!")

    @commands.hybrid_command(aliases=["auto"])
    @app_commands.guild_only()
    @app_commands.choices(
        mode=[
            app_commands.Choice(name=k.name, value=k.value)
            for k in wavelink.AutoPlayMode
        ]
    )
    async def autoplay(
        self, ctx: commands.Context[Nameless], mode: wavelink.AutoPlayMode | None = None
    ):
        """Change autoplay mode."""
        player = await self.ensure_guild_voice_client(ctx, auto_connect=True)

        if mode is None:
            await ctx.send(f"Autoplay mode is currently set to {player.autoplay.name}.")
            return

        if player.autoplay == mode:
            await ctx.send("Autoplay mode is already set to this mode.")
            return

        match mode:
            case wavelink.AutoPlayMode.disabled:
                player.auto_queue.clear()
            case wavelink.AutoPlayMode.enabled:
                await player._do_recommendation()  # pyright: ignore[reportPrivateUsage]
            case _:
                pass

        player.autoplay = mode
        await ctx.send(f"Autoplay mode has been set to {mode.name}.")

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def sponsorblock(self, ctx: commands.Context[Nameless]):
        """Sponsorblock setting."""
        # Making a menu to control sponsorblock settings.
        await sponsorblock_make(ctx)

    @commands.hybrid_command()
    @app_commands.guild_only()
    async def filter(self, ctx: commands.Context[Nameless]):
        """Audio filters setting."""
        # Making a menu to control filter settings.
        await filter_make(ctx)


async def setup(bot: Nameless):
    autostart_lavalink = False
    autoupdate_lavalink = False

    for node in nameless_config["wavelinks"]:
        if node.get("auto_start", False) is True:
            autostart_lavalink = True
            autoupdate_lavalink = node.get("auto_update", False)
            break

    if not autostart_lavalink and not nameless_config.get("wavelinks"):
        nameless_config["wavelinks"] = [
            {
                "uri": "http://localhost:2333",
                "password": "youshallnotpass",
                "auto_start": True,
                "auto_update": True,
            }
        ]
        logging.warning("No Lavalink nodes found. Added a default node.")
        autostart_lavalink = True
        autoupdate_lavalink = True

    if autostart_lavalink:
        from nameless.custom.player.lavalink import main as lavalink_main

        await lavalink_main(bot.loop, autoupdate_lavalink)

    await bot.add_cog(MusicCommands(bot))
    logging.info("%s cog added!", __name__)


async def teardown(bot: Nameless):
    for node in nameless_config.get("wavelinks", {}):
        if node.get("auto_start", False) is True:
            from nameless.custom.player.lavalink import stop as lavalink_stop

            logging.warning("Stop default Lavalink node...")
            await lavalink_stop()

    await bot.remove_cog(MusicCommands.__cog_name__)
    logging.warning("%s cog removed!", __name__)
