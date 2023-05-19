import asyncio
import datetime
import logging
import random
from typing import Dict, List, Optional, Tuple, Union

import discord
from discord import ClientException, VoiceClient, app_commands
from discord.app_commands import Choice, Range
from discord.ext import commands
from discord.utils import MISSING, escape_markdown
from reactionmenu import ViewButton, ViewMenu
from yt_dlp import DownloadError

from nameless import Nameless
from nameless.cogs.checks import MusicCogCheck
from nameless.commons import Utility
from nameless.customs.voice_backends import FFOpusAudioProcess, YTDLSource, YTMusicSource
from nameless.customs.voice_backends.errors import FFAudioProcessNoCache
from nameless.database import CRUD
from nameless.ui_kit import TrackSelectDropdown, VoteMenu
from NamelessConfig import NamelessConfig


__all__ = ["MusicNativeCog"]


class MainPlayer:
    __slots__ = (
        "client",
        "_guild",
        "_channel",
        "queue",
        "signal",
        "track",
        "total_duration",
        "repeat",
        "task",
        "loop_play_count",
        "allow_np_msg",
        "play_related_tracks",
        "stopped",
    )

    def __init__(self, interaction: discord.Interaction, cog) -> None:
        self.client = interaction.client
        self._guild = interaction.guild
        self._channel = interaction.channel

        self.queue: asyncio.Queue[YTDLSource] = asyncio.Queue()
        self.signal = asyncio.Event()

        self.track: YTDLSource = MISSING
        self.total_duration = 0

        self.repeat = False
        self.stopped = False
        self.allow_np_msg = True
        self.loop_play_count = 0
        self.play_related_tracks = False

        if not self._guild and not isinstance(self._guild, discord.Guild):
            logging.error("Wait what? There is no guild here!")
            raise AttributeError(f"Try to access guild attribute, got {self._guild.__class__.__name__} instead")

        self.task: asyncio.Task = self.client.loop.create_task(self.create())
        
    @property
    def queue_empty(self) -> bool:
        return self.queue.empty()
    
    @property
    def queue_size(self) -> int:
        return self.queue.qsize()

    @staticmethod
    def build_embed(track: YTDLSource, header: str):
        return (
            discord.Embed(timestamp=datetime.datetime.now(), color=discord.Color.orange())
            .set_author(
                name=header,
                icon_url=getattr(track.requester.avatar, "url", None),
            )
            .set_thumbnail(url=track.thumbnail)
            .add_field(
                name="Title",
                value=escape_markdown(track.title),
                inline=False,
            )
            .add_field(
                name="Author",
                value=escape_markdown(track.author),
            )
            .add_field(
                name="Source",
                value=escape_markdown(track.uri) if track.uri else "N/A",
            )
        )

    def clear_queue(self):
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def create(self):
        await self.client.wait_until_ready()

        while not self.client.is_closed():
            try:
                self.signal.clear()
                if not self.repeat or not self.track:
                    self.track = await self.queue.get()
                    self.stopped = False

                    if self.allow_np_msg:
                        await self._channel.send(embed=self.build_embed(self.track, "Now playing"))  # pyright: ignore

                    self.track = await self.track.generate_stream(self.track)
                    self.total_duration -= self.track.duration
                else:
                    self.loop_play_count += 1
                    try:
                        self.track.to_start()   # type: ignore
                    except FFAudioProcessNoCache:
                        self.track = await YTDLSource.generate_stream(self.track)

                self._guild.voice_client.play(  # type: ignore
                    self.track, after=lambda _: self.client.loop.call_soon_threadsafe(self.signal.set)
                )

            except AttributeError as err:
                logging.error(
                    "We no longer connect to guild %s, but somehow we still in. Time to destroy!", self._guild.id
                )
                logging.error("AttributeError raised, error was: %s", err)
                return self.destroy()

            except Exception as e:
                logging.error(
                    "I'm not sure what went wrong when we tried to process the request in guild %s. Anyway, I'm going to sleep. Here is the error: %s",  # noqa: E501
                    self._guild.id,
                    str(e),
                )
                return await self._channel.send(  # type: ignore
                    f"There was an error processing your song.\n" f"```css\n[{e}]\n```"
                )

            await self.signal.wait()  # wait for signal to set after the song played

            if not self.repeat:
                if self.play_related_tracks and self.queue.empty() and not self.stopped:
                    data = await self.track.get_related_tracks(self.track, self.client)
                    if data:
                        await self.queue.put(data)

                self.loop_play_count = 0
                self.track.final_cleanup()  # type: ignore
                self.track = None

            # if not self._guild.voice_client:  # random check
            #     return self.destroy(self._guild)

        else:
            return self.destroy()

    def destroy(self):
        async def runner():
            self.queue = asyncio.Queue()
            self._guild.voice_client.stop()  # type: ignore

            if not self.signal.is_set():
                self.signal.set()

            self.task.cancel()
            await self._guild.voice_client.disconnect()  # type: ignore

            if self.track:
                self.track.all_cleanup()  # type: ignore
                
        return self.client.loop.create_task(runner())


class MusicNativeCog(commands.GroupCog, name="music"):
    def __init__(self, bot: Nameless):
        self.bot = bot
        self.players: Dict[int, MainPlayer] = {}

    def get_player(self, interaction: discord.Interaction):
        """Retrieve the guild player, or generate one."""
        try:
            player = self.players[interaction.guild.id]
        except KeyError:
            player = MainPlayer(interaction, self)
            self.players[interaction.guild.id] = player

        return player

    async def cleanup(self, guild_id: int):
        player: Optional[MainPlayer] = self.players.pop(guild_id, None)
        if not player:
            return logging.warning("No player was found for guild %s. And also, this should not happen.", guild_id)
        player.destroy()

    @staticmethod
    def generate_embeds_from_queue(q: asyncio.Queue) -> List[discord.Embed]:
        # Some workaround to get list from asyncio.Queue
        copycat: List = q._queue.copy()  # type: ignore
        idx = 0
        txt = ""
        embeds: List[discord.Embed] = []

        try:
            while track := copycat.pop():
                upcoming = (
                    f"{idx + 1} - "
                    f"[{escape_markdown(track.title)} by {escape_markdown(track.author)}]"
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
        except IndexError:
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

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Handle voice state updates, auto-disconnect the bot, or maybe add a logging system in here :eyes:"""
        player = self.players.get(member.guild.id)
        if not player:
            return

        chn = before.channel if before.channel else after.channel
        guild = before.channel.guild if before.channel else after.channel.guild

        voice_members = [member for member in chn.members if member.id != self.bot.user.id]
        bot_is_in_vc = any(member for member in chn.members if member.id == self.bot.user.id)

        if bot_is_in_vc:
            if len(voice_members) == 0:
                await self.cleanup(guild.id)

        if member.id == self.bot.user.id:
            before_was_in_voice = before.channel is not None
            after_not_in_noice = after.channel is None

            if before_was_in_voice and after_not_in_noice:
                logging.debug(
                    "Guild player %s still connected even if it is removed from voice, disconnecting",
                    guild.id,
                )
                await self.cleanup(guild.id)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_in_voice)
    async def connect(self, interaction: discord.Interaction):
        """Connect to your current voice channel"""
        await interaction.response.defer(thinking=True)

        await self.bot.wait_until_ready()
        try:
            await interaction.user.voice.channel.connect(self_deaf=True)  # type: ignore
            await interaction.followup.send("Connected to your current voice channel")
            self.get_player(interaction)
        except ClientException:
            await interaction.followup.send("Already connected")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.bot_in_voice)
    async def disconnect(self, interaction: discord.Interaction):
        """Disconnect from my current voice channel"""
        await interaction.response.defer(thinking=True)

        try:
            await self.cleanup(interaction.guild.id)
            await interaction.followup.send("Disconnected from my own voice channel")
        except AttributeError:
            await interaction.followup.send("Already disconnected")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def loop(self, interaction: discord.Interaction):
        """Toggle loop playback of current track"""
        await interaction.response.defer(thinking=True)

        player = self.get_player(interaction)
        player.repeat = not player.repeat
        await interaction.followup.send(f"Loop set to {'on' if player.repeat else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def toggle(self, interaction: discord.Interaction):
        """Toggle for current playback."""
        vc: VoiceClient = interaction.guild.voice_client  # type: ignore

        if vc.is_paused():
            vc.resume()
            action = "Resumed"
        else:
            vc.pause()
            action = "Paused"

        await interaction.followup.send(action)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def pause(self, interaction: discord.Interaction):
        """Pause current playback"""
        await interaction.response.defer(thinking=True)

        vc: VoiceClient = interaction.guild.voice_client  # type: ignore

        if vc.is_paused():
            await interaction.followup.send("Already paused")
            return

        vc.pause()
        await interaction.followup.send("Paused")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_is_silent)
    async def resume(self, interaction: discord.Interaction):
        """Resume current playback, if paused"""
        await interaction.response.defer(thinking=True)

        vc: VoiceClient = interaction.guild.voice_client  # type: ignore

        if not vc.is_paused():
            await interaction.followup.send("Already resuming")
            return

        vc.resume()
        await interaction.followup.send("Resumed")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def stop(self, interaction: discord.Interaction):
        """Stop current playback."""
        await interaction.response.defer(thinking=True)

        vc: VoiceClient = interaction.guild.voice_client  # type: ignore
        player = self.get_player(interaction)

        vc.stop()
        player.stopped = True
        player.clear_queue()
        await interaction.followup.send("Stopped")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def skip(self, interaction: discord.Interaction):
        """Skip a song."""
        await interaction.response.defer(thinking=True)

        vc: VoiceClient = interaction.guild.voice_client  # type: ignore
        player: MainPlayer = self.get_player(interaction)
        track: YTDLSource = player.track

        if await VoteMenu("skip", track.title, interaction, vc).start():
            vc.stop()

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(offset="Position to seek to in milliseconds, defaults to run from start")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def seek(self, interaction: discord.Interaction, offset: int = 0):
        """Seek to a position in a track"""
        await interaction.response.defer(thinking=True)

        player: MainPlayer = self.get_player(interaction)
        source: Optional[FFOpusAudioProcess] = player.track.source

        if not source:
            return await interaction.followup.send("Not playing anything")

        try:
            await source.seek(offset)
            await interaction.followup.send(content="✅")
        except Exception as err:
            await interaction.followup.send(content=f"{err.__class__.__name__}: {str(err)}")
            logging.error("%s: %s", err.__class__.__name__, str(err))

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def toggle_play_now(self, interaction: discord.Interaction):
        """Toggle 'Now playing' message delivery"""
        await interaction.response.defer(thinking=True)
        player: MainPlayer = self.get_player(interaction)

        player.allow_np_msg = not player.allow_np_msg
        await interaction.followup.send(f"'Now playing' delivery is now {'on' if player.allow_np_msg else 'off'}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_must_play_track_not_stream)
    async def now_playing(self, interaction: discord.Interaction):
        """Check now playing song"""
        await interaction.response.defer(thinking=True)

        vc: VoiceClient = interaction.guild.voice_client  # type: ignore
        player: MainPlayer = self.get_player(interaction)
        track: YTDLSource = player.track

        dbg = CRUD.get_or_create_guild_record(discord_guild=interaction.guild)
        if not dbg:
            logging.error("Oh no. The database is gone! What do we do now?!!")
            raise AttributeError(f"Can't find guild id '{interaction.guild.id}'. Or maybe the database is gone?")

        next_tr: Optional[YTDLSource] = None
        if not player.queue.empty():
            next_tr = player.queue._queue[0]  # type: ignore

        await interaction.followup.send(
            embed=player.build_embed(track=track, header="Now playing")
            .add_field(
                name="Looping",
                value="This is a stream"
                if track.is_stream
                else f"Looped {getattr(vc, 'loop_play_count')} time(s)"
                if player.repeat is True
                else False,
            )
            .add_field(name="Paused", value=vc.is_paused())
            .add_field(
                name="Playtime" if track.is_stream else "Position",
                value=str(
                    discord.utils.utcnow().replace(tzinfo=None) - dbg.radio_start_time
                    if track.is_stream
                    else f"{datetime.timedelta(seconds=track.source.position)}/"
                    f"{datetime.timedelta(seconds=track.duration)}"
                ),
            )
            .add_field(
                name="Next track",
                value=f"[{escape_markdown(next_tr.title)} "
                f"by {escape_markdown(next_tr.author)}]"
                f"({next_tr.uri[:100]})"
                if next_tr
                else None,
            )
        )

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def autoplay(self, interaction: discord.Interaction):
        """Automatically play the next song in the queue"""
        await interaction.response.defer(thinking=True)

        player: MainPlayer = self.get_player(interaction)
        player.play_related_tracks = not player.play_related_tracks

        await interaction.followup.send(f"Autoplay is now {'on' if player.play_related_tracks else 'off'}")

    queue = app_commands.Group(name="queue", description="Commands related to queue management.")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def view(self, interaction: discord.Interaction):
        """View current queue"""
        await interaction.response.defer(thinking=True)

        player: MainPlayer = self.get_player(interaction)

        embeds = self.generate_embeds_from_queue(player.queue)
        self.bot.loop.create_task(self.show_paginated_tracks(interaction, embeds))

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(idx="The index to remove (1-based)")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def delete(self, interaction: discord.Interaction, idx: Range[int, 1]):
        """Remove track from queue"""
        await interaction.response.defer(thinking=True)

        idx -= 1
        player: MainPlayer = self.get_player(interaction)
        queue: List = player.queue._queue  # type: ignore

        if idx > player.queue.qsize() or idx < 0:
            return await interaction.followup.send("The track number you just entered is not available. Check again")

        deleted_track: YTDLSource = queue.pop(idx)
        await interaction.followup.send(
            f"Deleted track at position #{idx}: **{deleted_track.title}** from **{deleted_track.author}**"
        )

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(
        search="Search query", provider="Pick a provider to search from", amount="How much results to show"
    )
    @app_commands.choices(provider=[Choice(name=k, value=k) for k in ("ytmusic", "youtube", "soundcloud")])
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    async def add(self, interaction: discord.Interaction, search: str, provider: str = "youtube", amount: int = 10):
        """Add selected track(s) to queue"""
        await interaction.response.defer(thinking=True)

        player: MainPlayer = self.get_player(interaction)

        if provider == "ytmusic":
            search = f"{search}#songs"

        try:
            tracks: Optional[Tuple[Union[YTDLSource, YTMusicSource]]] = tuple(
                [tr async for tr in YTDLSource.get_tracks(interaction, search, amount, provider)]
            )
        except DownloadError:
            if "youtube" in search:  # only check for youtube link, not search str or any other provider
                tracks = (await YTMusicSource.indivious_get_track(interaction, search),)  # type: ignore
            else:
                tracks = None

        if not tracks:
            await interaction.followup.send(f"No tracks found for '{search}' on '{provider}'.")
            return

        extend_duration = 0
        if len(tracks) > 1:
            if ":search" in tracks[0].extractor:
                dropdown: Union[discord.ui.Item[discord.ui.View], TrackSelectDropdown] = TrackSelectDropdown(
                    tracks  # pyright: ignore
                )
                view = discord.ui.View(timeout=20).add_item(dropdown)
                msg: discord.WebhookMessage = await interaction.followup.send(content="Tracks found", view=view)  # type: ignore  # noqa: E501
                await msg.delete(delay=30)

                if await view.wait():
                    return await msg.edit(content="Timed out!", view=None)

                vals = dropdown.values
                queue_len = len(vals)
                if not vals or "Nope" in vals:
                    return await msg.edit(content="OK bye", view=None)

                for val in vals:
                    idx = int(val)
                    await player.queue.put(tracks[idx])
                    extend_duration += tracks[idx].duration
            else:
                queue_len = len(tracks)
                for tr in tracks:
                    await player.queue.put(tr)
                    extend_duration += tr.duration

            await interaction.followup.send(content=f"Added {queue_len} tracks into the queue")
        else:
            if not player.queue_empty:
                msg = await interaction.followup.send(embed=player.build_embed(tracks[0], "Added to queue"))  # type: ignore  # noqa: E501
            else:
                msg = await interaction.followup.send(content="✅")  # type: ignore

            await msg.delete(delay=10)
            await player.queue.put(tracks[0])
            extend_duration = tracks[0].duration

        player.total_duration += extend_duration

    @app_commands.command()
    @app_commands.guilds(*getattr(NamelessConfig, "GUILD_IDs", []))
    @app_commands.guild_only()
    @app_commands.describe(url="Radio url")
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.bot_is_silent)
    async def radio(self, interaction: discord.Interaction, url: str):
        """Play a radio"""
        await interaction.response.defer(thinking=True)

        if not Utility.is_an_url(url):
            await interaction.followup.send("You need to provide a direct URL")
            return

        await self.add(interaction, url, True)  # type: ignore

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(before="Old position", after="New position")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def move(self, interaction: discord.Interaction, before: Range[int, 1], after: Range[int, 1]):
        """Move track to new position"""
        await interaction.response.defer(thinking=True)

        player: MainPlayer = self.get_player(interaction)
        int_queue = player.queue._queue  # type: ignore
        queue_length = player.queue.qsize()

        if not (before != after and 1 <= before <= queue_length and 1 <= after <= queue_length):
            await interaction.followup.send("Invalid queue position(s)")
            return

        temp = int_queue[before - 1]
        del int_queue[before - 1]
        int_queue.insert(after - 1, temp)

        await interaction.followup.send(f"Moved track #{before} to #{after}")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.describe(pos="Current position", diff="Relative difference")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def move_relative(self, interaction: discord.Interaction, pos: Range[int, 1], diff: Range[int, 0]):
        """Move track to new position using relative difference"""
        await self.move(interaction, pos, pos + diff)  # pyright: ignore

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    @app_commands.describe(
        pos1="First track position (1-indexed)",
        pos2="Second track position (1-indexed)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def swap(self, interaction: discord.Interaction, pos1: Range[int, 1], pos2: Range[int, 1]):
        """Swap two tracks."""
        await interaction.response.defer(thinking=True)

        player: MainPlayer = self.get_player(interaction)

        q = player.queue._queue  # type: ignore
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
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shuffle(self, interaction: discord.Interaction):
        """Shuffle the queue"""
        await interaction.response.defer(thinking=True)

        vc: VoiceClient = interaction.guild.voice_client  # type: ignore

        random.shuffle(vc.queue._queue)  # type: ignore
        await interaction.followup.send("Shuffled the queue")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    async def clear(self, interaction: discord.Interaction):
        """Clear the queue"""
        await interaction.response.defer(thinking=True)

        vc = interaction.guild.voice_client  # type: ignore
        player: MainPlayer = self.get_player(interaction)

        if await VoteMenu("clear", "queue", interaction, vc).start():  # pyright: ignore
            player.clear_queue()
            await interaction.followup.send("Cleared the queue")

    @queue.command()
    @app_commands.guild_only()
    @app_commands.check(MusicCogCheck.user_and_bot_in_voice)
    @app_commands.check(MusicCogCheck.queue_has_element)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def force_clear(self, interaction: discord.Interaction):
        """Clear the queue"""
        await interaction.response.defer(thinking=True)
        player: MainPlayer = self.get_player(interaction)

        try:
            player.clear_queue()
            await interaction.followup.send("Cleared the queue")
        except Exception as e:
            logging.error(
                "User %s try to forcely clear the queue in %s, but we encounter some trouble.",
                interaction.user.id,
                player._guild.id,
            )
            logging.error("MusicCog.force_clear raise an error: [%s] %s", e.__class__.__name__, str(e))


async def setup(bot: Nameless):
    if bot.get_cog("MusicLavalinkCog"):
        raise commands.ExtensionFailed(
            __name__, RuntimeError("can't load MusicLavalinkCog and MusicNativeCog at the same time.")
        )

    await bot.add_cog(MusicNativeCog(bot))
    logging.info("Cog of %s added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog("MusicNativeCog")
    logging.warning("Cog of %s removed!", __name__)
