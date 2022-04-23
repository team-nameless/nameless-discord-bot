from __future__ import unicode_literals

import asyncio
import gc
import itertools
from functools import partial
from math import ceil
from random import choice, shuffle
from time import gmtime, strftime

import nextcord
from nextcord import Interaction, Embed, SlashOption
from nextcord.ext import commands
from yt_dlp import YoutubeDL

from config import Config

ytdlopts = {
    "format": "bestaudio/93/best",
    "outtmpl": "downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "extract_flat": "in_playlist",
    "no_warnings": True,
    "default_search": "ytsearch5",
    "source_address": "0.0.0.0",
}

ffmpegopts = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = YoutubeDL(ytdlopts)
color = (0xDB314B, 0xDB3A4C, 0xDB424D, 0xDB354B)


def timeconv(time):
    return strftime("%H:%M:%S", gmtime(time))


def embed_(footer, thumbnail, **kwargs):
    embed = nextcord.Embed(color=choice(color), **kwargs)

    if isinstance(footer, (int, float)):
        time = timeconv(footer)
        embed.set_footer(text=time)
    else:
        embed.set_footer(text=footer)

    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    return embed


class VoiceConnectionError(commands.CommandError):
    """Custom Exception class for connection errors."""


class InvalidVoiceChannel(VoiceConnectionError):
    """Exception for cases of invalid Voice Channels."""


class Dropdown(nextcord.ui.Select):
    def __init__(self, data=None):
        options = [
            nextcord.SelectOption(
                label="Select all",
                value="All",
                description="Selected items from above will be excluded from playlist",
            )
        ]
        for index, item in enumerate(data):
            options.append(
                nextcord.SelectOption(
                    label=item["title"], description=item["url"], value=str(int)
                )
            )

        super().__init__(
            placeholder="owo", min_values=1, max_values=len(options), options=options
        )

    async def callback(self, interaction: Interaction):
        self._view.stop()


class YTDLSource(nextcord.PCMVolumeTransformer):
    __slots__ = ("source", "requester", "webpage_url", "title", "duration", "thumbnail")

    def __init__(self, source=None, *, data, requester):
        super().__init__(source)

        self.requester = requester
        self.duration = data.get("duration")
        self.webpage_url = data.get("webpage_url")
        self.title = data.get("title")
        self.thumbnail = None  # what

    @classmethod
    async def create_source(
        cls, interaction, search, loop, imported=False, picker=False
    ):

        loop = loop or asyncio.get_event_loop()

        to_run = partial(ytdl.extract_info, url=search, download=False)
        data = await loop.run_in_executor(None, to_run)

        data = ytdl.sanitize_info(data)

        if not picker and data["extractor"] == "youtube:search":
            data = data["entries"][0]

        if "entries" in data:
            if data["extractor"] == "youtube:search":

                view = nextcord.ui.View(timeout=30)
                view.add_item(Dropdown(data["entries"]))

                msg = await interaction.send(
                    "Pick a song, or multiple ones if you want.", view=view
                )

                if await view.wait():
                    await msg.edit(content="Timeout!", view=None, delete_after=10)
                    return

                if view.children[0].values is None:
                    await msg.delete()
                    return

                if "All" in view.children[0].values:
                    values = [0, 1, 2, 3, 4]
                    if len(view.children[0].values) > 1:
                        for item in set(view.children[0].values):
                            while item in values:
                                values.remove(item)
                else:
                    values = view.children[0].values

                await msg.edit(
                    view=None,
                    embed=Embed(
                        title=f"Added {len(values)} songs",
                        description=f"Requested by {interaction.user}",
                    ),
                )

                for i in values:
                    yield cls.to_value(data["entries"][int(i)], interaction.user)

        else:
            yield cls.to_value(data, interaction.user)

            if not imported:
                await interaction.send(
                    embed=embed_(
                        title="Song added",
                        description=f"[{data['title']}]({data.get('webpage_url') or data.get('url')})",
                        footer=data.get("duration") or 0,
                        thumbnail=data["thumbnail"],
                    )
                )

    @staticmethod
    def to_value(data, user):
        return {
            "webpage_url": data.get("webpage_url") or data.get("url"),
            "requester": user,
            "title": data["title"],
            "duration": data.get("duration") or 0,
            "thumbnail": data["thumbnail"],
        }

    @classmethod
    async def regather_stream(cls, data, loop):
        loop = loop or asyncio.get_event_loop()
        requester = data["requester"]

        to_run = partial(ytdl.extract_info, url=data["webpage_url"], download=False)
        data = await loop.run_in_executor(None, to_run)
        data = ytdl.sanitize_info(data)

        return cls(
            nextcord.FFmpegPCMAudio(data["url"], **ffmpegopts),
            data=data,
            requester=requester,
        )


class MusicPlayer:
    __slots__ = (
        "interaction",
        "_loop",
        "client",
        "_guild",
        "_channel",
        "_cog",
        "queue",
        "next",
        "current",
        "np",
        "volume",
        "totaldura",
        "task",
        "source",
    )

    def __init__(self, interaction: Interaction, cog=None):
        self.client = interaction.client
        self._guild = interaction.guild
        self._channel = interaction.channel
        self._cog = cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.np = None
        self.volume = 0.5
        self.current = None
        self.source = None
        self.totaldura = 0
        self._loop = False

        self.task = interaction.client.loop.create_task(self.player_loop())

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    async def player_loop(self):
        await self.client.wait_until_ready()

        while not self.client.is_closed():
            try:
                self.next.clear()

                if not self._loop or self.source is None:
                    self.source = await self.queue.get()

                    self.np = embed_(
                        title=f"Nowplaying",
                        footer=f"Requested by {self.source['requester']}",
                        description=f"[{self.source['title']}]({self.source['webpage_url']})",
                        thumbnail=self.source["thumbnail"],
                    )
                    await self._channel.send(embed=self.np)

                self.current = await YTDLSource.regather_stream(
                    self.source, loop=self.client.loop
                )
                self.current.volume = self.volume

                self._guild.voice_client.play(
                    self.current,
                    after=lambda _: self.client.loop.call_soon_threadsafe(
                        self.next.set
                    ),
                )

                self.totaldura -= self.source["duration"]

            except AttributeError as e:
                print(self._guild.id, str(e))
                return self.destroy(self._guild)

            except Exception as e:
                return await self._channel.send(
                    f"There was an error processing your song.\n" f"```css\n[{e}]\n```"
                )

            finally:
                await self.next.wait()

                # Make sure the FFmpeg process is cleaned up.
                self.current.cleanup()
                self.current = None
                print(f"after music, release: {gc.collect()} objects")

    def destroy(self, guild):
        """Disconnect and cleanup the player."""
        return self.client.loop.create_task(self._cog.cleanup(guild))


class MusicCog(commands.Cog):
    __slots__ = ("client", "players", "db")

    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot
        self.players = {}

    async def cleanup(self, guild):
        try:
            await guild.voice_client.disconnect()
        except AttributeError:
            pass

        try:
            player = self.players[guild.id]
            player.task.cancel()
        except asyncio.CancelledError:
            pass

        try:
            del self.players[guild.id]
            print(f"cleanup guild, release: {gc.collect()} objects")
        except KeyError:
            pass

    def get_player(self, interaction: Interaction):
        try:
            player = self.players[interaction.guild.id]
        except KeyError:
            player = MusicPlayer(interaction, self)
            self.players[interaction.guild.id] = player

        return player

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        try:
            player = self.players[member.guild.id]
        except KeyError:
            return

        try:
            if len(player._guild.voice_client.channel.members) == 1:  # If bot is alone
                if player._guild.voice_client.channel.members[0].id == self.bot.user.id:
                    await self.cleanup(player._guild)
                    await player._channel.send('Hic. Don"t leave me alone :cry:')
        except AttributeError:  # bot got kicked out
            await self.cleanup(player._guild)

    @nextcord.slash_command(description="Music command", guild_ids=Config.GUILD_IDs)
    async def music(self, interaction: nextcord.Interaction):
        pass

    @music.subcommand(description="Connect to voice channel")
    async def connect(
        self,
        interaction: Interaction,
        channel: nextcord.abc.GuildChannel = SlashOption(
            name="channel",
            description="Join where?",
            channel_types=[nextcord.ChannelType.voice],
        ),
    ):
        if not channel:
            try:
                channel = interaction.user.voice.channel
            except AttributeError:
                await interaction.send(
                    "No channel to join. Please either specify a valid channel or join one."
                )
                raise InvalidVoiceChannel

        vc = interaction.guild.voice_client

        if vc:
            if vc.channel.id == channel.id:
                return
            try:
                await vc.move_to(channel)
            except asyncio.TimeoutError:
                raise VoiceConnectionError(f"Moving to channel: <{channel}> timed out.")
        else:
            try:
                await channel.connect()
            except asyncio.TimeoutError:
                raise VoiceConnectionError(
                    f"Connecting to channel: <{channel}> timed out."
                )

        self.get_player(interaction)
        await interaction.send(f"Connected to: **{channel}**", delete_after=20)

    @music.subcommand(description="Play music from remote URL")
    async def play(
        self,
        interaction: Interaction,
        url=SlashOption(description="URL go brrrrr", required=True),
        picker: bool = SlashOption(
            description="Show a dropdown menu", required=False, default=False
        ),
    ):
        await interaction.response.defer()

        vc = interaction.guild.voice_client
        try:
            if not vc:
                await self.connect.invoke_slash(interaction, channel=None)
        except InvalidVoiceChannel:
            return

        player = self.get_player(interaction)

        async for source in YTDLSource.create_source(
            interaction, url, loop=self.bot.loop, picker=picker
        ):
            player.totaldura += source["duration"]
            await player.queue.put(source)

    @music.subcommand(description="Toggle playback of current song")
    async def toggle_playback(self, interaction: Interaction):
        vc: nextcord.VoiceClient = interaction.guild.voice_client

        if not vc or not vc.is_connected():
            return await interaction.send(
                "I am currently not in any voice chat!", delete_after=20
            )

        if vc.source is None:
            return await interaction.send(
                "I am not currently playing anything!", delete_after=20
            )

        if vc.is_paused():
            vc.resume()
            action = "Resumed"
        else:
            vc.pause()
            action = "Paused"

        await interaction.send(f"**`{interaction.user}`**: {action} the song!")

    @music.subcommand(description="Skip playing song")
    async def skip(self, interaction: Interaction):
        vc: nextcord.VoiceClient = interaction.guild.voice_client

        if vc.is_paused():
            pass
        elif not vc.is_playing():
            return

        player = self.get_player(interaction)
        if player.loop:
            player.source = None

        vc.stop()
        await interaction.send(f"**`{interaction.user}`**: Skipped the song!")

    @music.subcommand(description="Loop current song")
    async def loop(self, interaction: Interaction):
        player = self.get_player(interaction)

        if not player.loop:
            player.loop = True
            await interaction.send("Looping current song!")
        else:
            player.loop = False
            await interaction.send("Current song is now no longer in loop!")

    @music.subcommand(description="View information of current queue")
    async def queue_info(
        self,
        interaction: Interaction,
        page: int = SlashOption(description="Page to view", required=False, default=1),
    ):
        player = self.get_player(interaction)
        if player.queue.empty():
            return await interaction.send("There are currently no more queued songs.")

        index = (page - 1) * 5
        max_index = len(player.queue._queue)
        upcoming = list(itertools.islice(player.queue._queue, index, index + 5))
        if not upcoming:
            await interaction.send("Out of index!")
            return

        desc = "\n"
        for i, q in enumerate(upcoming, start=index):
            if len(q["title"]) > 50:
                title = q["title"][:50] + "..." + q["title"][-5:]
            else:
                title = q["title"]

            desc += f"\n[{str(i + 1) + '. ' + title}]({q['webpage_url']})\n"

        embed = nextcord.Embed(title=f"{max_index} songs in queue")
        embed.add_field(name=f"Total time: {timeconv(player.totaldura)}", value=desc)
        embed.set_footer(text=f"Page {page}/{ceil(max_index / 5)}")
        await interaction.send(embed=embed)

    @music.subcommand(description="Swap two song in queue")
    async def swap(
        self,
        interaction,
        pos1: int = SlashOption(description="Position of first track"),
        pos2: int = SlashOption(description="Position of second track"),
    ):
        # i = i - 1
        # j = j - 1
        # As long as I remember, the following use C code right?
        pos1 -= 1
        pos2 -= 1

        player = self.get_player(interaction)
        if pos1 < len(player.queue._queue) and pos2 < len(player.queue._queue):
            player.queue._queue[pos1], player.queue._queue[pos2] = (
                player.queue._queue[pos2],
                player.queue._queue[pos1],
            )
            await interaction.send("✅")
        else:
            await interaction.send("Out of index!")

    @music.subcommand(name="shuffle", description="Shuffle the queue")
    async def shuffle_(self, interaction: Interaction):
        await interaction.response.defer()
        vc: nextcord.VoiceClient = interaction.guild.voice_client

        player = self.get_player(interaction)

        if player.queue.empty():
            return await interaction.send("There are no more queued songs to shuffle.")

        shuffle(player.queue._queue)
        await interaction.send("✅")  # white_check_mark

    @music.subcommand(description="Remove a song from queue")
    async def remove(
        self,
        interaction: Interaction,
        index: int = SlashOption(description="Index to remove"),
    ):
        player = self.get_player(interaction)
        title = player.queue._queue[index - 1]["title"]

        if player.queue.empty():
            return await interaction.send("There is no other song in queue!")

        del player.queue._queue[index - 1]

        await interaction.send(
            f"**`{interaction.user}`**: Removed `{title}` from queue"
        )

    @music.subcommand(description="View now playing song")
    async def now_playing(self, interaction: Interaction):
        player = self.get_player(interaction)
        if not player.current:
            return await interaction.send("I am not currently playing anything!")

        await interaction.send(embed=player.np)

    @music.subcommand(description="Adjust the volume")
    async def volume(
        self,
        interaction: Interaction,
        _: float = SlashOption(name="vol", description="A value"),
    ):
        await interaction.send(
            content="Due to the expensive hardware cost of adjusting the volume,"
            "you have to do it manually."
        )

    @music.subcommand(description="Stop playing session")
    async def stop(self, interaction: Interaction):
        await self.cleanup(interaction.guild)
        await interaction.send("byeee")

    @music.subcommand(description="Clear the queue")
    async def clear(self, interaction: Interaction):
        player = self.get_player(interaction)
        if not player.current:
            return await interaction.send("I am not playing anything!")

        player.queue._queue.clear()
        await interaction.send("✅")

    @clear.application_command_before_invoke
    @stop.application_command_before_invoke
    @now_playing.application_command_before_invoke
    @shuffle_.application_command_before_invoke
    @swap.application_command_before_invoke
    @queue_info.application_command_before_invoke
    @loop.application_command_before_invoke
    @skip.application_command_before_invoke
    @toggle_playback.application_command_before_invoke
    async def require_bot_connected(self, interaction: Interaction):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            return await interaction.send(
                "I am not connected to voice!", delete_after=10
            )
