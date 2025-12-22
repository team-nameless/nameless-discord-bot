# pyright:reportArgumentType=false,reportIncompatibleVariableOverride=false

import asyncio
import logging
from typing import cast, final, override

import discord
import pomice
from discord.abc import Messageable

from ..embeds import create_now_playing_embed
from ..exceptions import AutoplayPopulateError
from ..views import MusicControlView


@final
class CustomQueue(pomice.Queue):
    def __init__(self) -> None:
        super().__init__()
        self._current_item: pomice.Track | None = None

    @override
    def get(self):
        if self._loop_mode == pomice.LoopMode.TRACK and self._current_item:
            return self._current_item

        if self.is_empty:
            raise pomice.QueueEmpty("No items in the queue.")

        if self._loop_mode == pomice.LoopMode.QUEUE:
            # set current item to first track in queue if not set already
            # otherwise exception will be raised
            if not self._current_item or self._current_item not in self._queue:
                if self._queue:
                    item = self._queue[0]
                else:
                    raise pomice.QueueEmpty("No items in the queue.")

            # set current item to first track in queue if not set already
            if not self._current_item:
                self._current_item = self._queue[0]
                item = self._current_item

            # we reached the end of the queue, go back to first track
            if self._index(self._current_item) == len(self._queue) - 1:
                item = self._queue[0]

            # we are in the middle of the queue, go the next item
            else:
                index = self._index(self._current_item) + 1
                item = self._queue[index]
        else:
            item = self._get()

        self._current_item = item
        return item


class CustomPlayer(pomice.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.np_message_allowed: bool = True
        self.queue: pomice.Queue = CustomQueue()
        self.trigger_channel: Messageable | None = None

        self._autoplay_enabled: bool = True
        self._auto_disconnect_enabled: bool = True
        self._auto_disconnect_timeout: int = 300  # seconds

        self._logger: logging.Logger = logging.getLogger(f"CustomPlayer({self.guild.id})")
        self._auto_queue: list[pomice.Track] = []
        self._history: list[pomice.Track] = []
        self._votes: set[int] = set()
        self._speed: float = 1.0
        self._last_control_message: discord.Message | None = None
        self._inactive_disconnect_task: asyncio.Task[None] | None = None

        self.__reset_track_error_later_tasks = set()

        # track error handling
        self._track_errors: dict[str, int] = {}  # track_id -> error_count
        self._max_track_errors: int = 3
        self._error_reset_time: int = 300

        self._autoplay_extraction_track: pomice.Track | None = None

        # start timer immediately
        self.start_disconnect_timer()

    @property
    def is_autoplay_enabled(self) -> bool:
        return self._autoplay_enabled

    @property
    def is_auto_disconnect_enabled(self) -> bool:
        return self._auto_disconnect_enabled

    @property
    def auto_queue(self) -> list[pomice.Track]:
        return self._auto_queue

    @property
    def history(self) -> list[pomice.Track]:
        return self._history

    @property
    def votes(self) -> set[int]:
        return self._votes

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def total_duration(self) -> int:
        return sum(track.length for track in self.queue)

    @override
    async def stop(self) -> None:
        if self._autoplay_enabled and not self._auto_queue:
            self._autoplay_extraction_track = self.current
        return await super().stop()

    def toggle_play_now(self) -> None:
        self.np_message_allowed = not self.np_message_allowed

    def clear_auto_queue(self) -> None:
        self.auto_queue.clear()

    def start_disconnect_timer(self) -> None:
        if not self._auto_disconnect_enabled:
            return

        self.cancel_disconnect_timer()
        self._inactive_disconnect_task = asyncio.create_task(self._disconnect_after_timeout())

    async def _disconnect_after_timeout(self) -> None:
        if not self._auto_disconnect_enabled:
            return

        try:
            await asyncio.sleep(self._auto_disconnect_timeout)
            if not self.is_playing and not self.is_paused:
                await self.send_to_trigger_channel("Disconnecting due to inactivity.")
                await self.disconnect()
        except asyncio.CancelledError:
            pass
        finally:
            self._inactive_disconnect_task = None

    def cancel_disconnect_timer(self) -> None:
        if self._inactive_disconnect_task and not self._inactive_disconnect_task.done():
            self._inactive_disconnect_task.cancel()
            self._inactive_disconnect_task = None

    def set_auto_disconnect(self, value: bool, timeout: int | None = None) -> None:
        self._auto_disconnect_enabled = value
        if timeout is not None and timeout > 0:
            self._auto_disconnect_timeout = timeout

        if not value:
            self.cancel_disconnect_timer()
        else:
            self.start_disconnect_timer()

    def _get_track_id(self, track: pomice.Track) -> str:
        return f"{track.uri}:{track.title}"

    def _increment_track_error(self, track: pomice.Track) -> int:
        track_id = self._get_track_id(track)
        self._track_errors[track_id] = self._track_errors.get(track_id, 0) + 1

        # schedule error count reset
        task = asyncio.create_task(self._reset_track_error_later(track_id))
        task.add_done_callback(lambda t: self.__reset_track_error_later_tasks.discard(t))
        self.__reset_track_error_later_tasks.add(task)
        return self._track_errors[track_id]

    async def _reset_track_error_later(self, track_id: str) -> None:
        await asyncio.sleep(self._error_reset_time)
        if track_id in self._track_errors:
            del self._track_errors[track_id]

    def _should_skip_track(self, track: pomice.Track) -> bool:
        track_id = self._get_track_id(track)
        return self._track_errors.get(track_id, 0) >= self._max_track_errors

    async def _handle_problematic_track(self, track: pomice.Track) -> None:
        track_id = self._get_track_id(track)
        error_count = self._track_errors.get(track_id, 0)

        # remove error tracking
        if track_id in self._track_errors:
            del self._track_errors[track_id]

        # disable loop to prevent infinite loop
        if self.queue.loop_mode == pomice.LoopMode.TRACK:
            self.queue.disable_loop()
            await self.send_to_trigger_channel(
                f"**Track loop disabled** - `{track.title}` failed {error_count} times. Skipping to next track."
            )
        else:
            await self.send_to_trigger_channel(f"**Track skipped** - `{track.title}` failed {error_count} times.")

    @override
    def cleanup(self) -> None:
        self.queue.clear()
        self._auto_queue.clear()
        self._history.clear()
        self._votes.clear()
        self._track_errors.clear()
        self.cancel_disconnect_timer()
        super().cleanup()

    @override
    async def disconnect(self, *, force: bool = False) -> None:
        await self.disable_last_control_view()
        await super().disconnect(force=force)

    def toggle_autoplay(self) -> bool:
        self._autoplay_enabled = not self._autoplay_enabled
        return self._autoplay_enabled

    async def refresh_auto_queue(self) -> None:
        current = self.current or self._autoplay_extraction_track
        if not current:
            self._auto_queue.clear()
            return

        tracks = await self.get_recommendations(track=current)
        if not tracks:
            self._auto_queue.clear()
            return

        if isinstance(tracks, list):
            self._auto_queue = tracks
        else:
            self._auto_queue = tracks.tracks.copy()

        self._logger.info(f"Refreshed auto queue with {len(self._auto_queue)} tracks.")

    async def update_now_playing_embed(
        self,
        message: discord.Message | None = None,
        user: discord.User | discord.Member | discord.ClientUser | None = None,
    ):
        target_message = message or self._last_control_message
        if target_message is None or not self.current:
            return

        try:
            embed = create_now_playing_embed(
                self,
                self.current,
                user or self.guild.me,
            )
            view = MusicControlView(self)
            await target_message.edit(embed=embed, view=view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            if message is None:
                self._last_control_message = None

    async def disable_last_control_view(self) -> None:
        if self._last_control_message is None:
            return

        try:
            disabled_view = MusicControlView(self)
            for item in disabled_view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

            await self._last_control_message.edit(view=None)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        finally:
            self._last_control_message = None

    async def handle_track_error(self, track: pomice.Track) -> bool:
        error_count = self._increment_track_error(track)

        if error_count >= self._max_track_errors:
            await self._handle_problematic_track(track)
            return True

        return False

    async def set_speed(self, speed: float) -> None:
        self._speed = speed
        # Try to edit if exists, else add
        try:
            await self.edit_filter(pomice.Timescale(tag="speed", speed=speed))
        except pomice.FilterTagInvalid:
            await self.add_filter(pomice.Timescale(tag="speed", speed=speed))

    async def do_next(self):
        if self.current:
            self._history.insert(0, self.current)
            if len(self._history) > 50:
                self._history.pop()

        self._votes.clear()

        if self.queue:
            next_track = self.queue.get()
            await self.play(next_track)
            return

        if self.is_autoplay_enabled:
            if not self.auto_queue:
                await self.refresh_auto_queue()
                if not self.auto_queue:
                    raise AutoplayPopulateError()

            next_track = self.auto_queue.pop(0)
            await self.play(next_track)
            return

        self.start_disconnect_timer()

    async def send_to_channel(
        self,
        messageable: Messageable,
        content: str | None = None,
        make_controller: bool = False,
        *,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
        delete_after: float | None = None,
        silent: bool = False,
        mention_author: bool = False,
    ) -> discord.Message | None:
        view = self._prepare_view(view, make_controller)

        if self._is_music_control_view(view):
            await self.disable_last_control_view()

        message = await self._send_message(
            messageable=messageable,
            content=content,
            embed=embed,
            view=view,
            delete_after=delete_after,
            silent=silent,
            mention_author=mention_author,
        )

        if self._is_music_control_view(view):
            self._last_control_message = message

        return message

    async def send_to_trigger_channel(
        self,
        content: str | None = None,
        make_controller: bool = False,
        *,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
        delete_after: float | None = None,
        silent: bool = False,
        mention_author: bool = False,
    ) -> discord.Message | None:
        if not self.trigger_channel:
            return None

        return await self.send_to_channel(
            messageable=self.trigger_channel,
            content=content,
            make_controller=make_controller,
            embed=embed,
            view=view,
            delete_after=delete_after,
            silent=silent,
            mention_author=mention_author,
        )

    def _prepare_view(self, view: discord.ui.View | None, make_controller: bool) -> discord.ui.View | None:
        if make_controller:
            return MusicControlView(self)
        return view

    def _is_music_control_view(self, view: discord.ui.View | None) -> bool:
        return view is not None and isinstance(view, MusicControlView)

    async def _send_message(
        self,
        messageable: Messageable,
        content: str | None,
        embed: discord.Embed | None,
        view: discord.ui.View | None,
        delete_after: float | None,
        silent: bool,
        mention_author: bool,
    ) -> discord.Message:
        return cast(
            "discord.Message",
            await messageable.send(
                content=content,
                embed=embed,
                view=view,
                delete_after=delete_after,
                silent=silent,
                mention_author=mention_author,
            ),
        )
