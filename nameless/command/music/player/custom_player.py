# pyright:reportArgumentType=false,reportIncompatibleVariableOverride=false
from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast, final, override

import discord
import httpx
import pomice

from ..embeds import create_now_playing_embed
from ..exceptions import AutoplayPopulateError
from ..views import MusicControlView

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from typing import Any

    from discord.abc import Messageable
    from discord.ext.commands.context import Context

    from nameless import Nameless

__all__ = ["CustomPlayer", "CustomQueue"]


def human_readable_to_int(human_readable: str | Any) -> int:
    if not human_readable or not isinstance(human_readable, str):
        return 0

    text = human_readable.strip().lower()
    if "no views" in text or "no view" in text:
        return 0

    match = re.search(r"([\d,]+\.?\d*)\s*([kmb])?", text)
    if not match:
        return 0

    number_str = match.group(1)
    suffix = match.group(2)

    try:
        number = float(number_str.replace(",", ""))
    except ValueError:
        return 0

    multipliers = {
        "k": 1_000,
        "m": 1_000_000,
        "b": 1_000_000_000,
    }
    if suffix and suffix in multipliers:
        number *= multipliers[suffix]

    return int(number)


def get_and_cast[T](d: Mapping[str, Any], key: str | Iterable[str | int], default: T = None) -> T:
    if isinstance(key, str):
        key = [key]

    value = d
    for k in key:
        if (isinstance(value, dict) and k in value) or (
            isinstance(value, list) and isinstance(k, int) and 0 <= k < len(value)  # type: ignore
        ):
            value = value[k]  # type: ignore
        else:
            return default

    if default is None:
        return value  # type: ignore

    _type = type(default)
    try:
        return _type(value)
    except (ValueError, TypeError):
        return default


def _parser_youtube_related_tracks(item: Mapping[str, Any]) -> str | None:
    lockup_view_model = item.get("lockupViewModel")
    if not (lockup_view_model and lockup_view_model.get("contentType") == "LOCKUP_CONTENT_TYPE_VIDEO"):
        return None

    video_id = lockup_view_model.get("contentId")
    if not video_id:
        return None

    view_count = human_readable_to_int(
        get_and_cast(
            lockup_view_model,
            (
                "metadata",
                "lockupMetadataViewModel",
                "metadata",
                "contentMetadataViewModel",
                "metadataRows",
                1,
                "metadataParts",
                0,
                "text",
                "content",
            ),
            "0 views",
        )
    )
    if view_count < 5000:
        return None

    return f"https://www.youtube.com/watch?v={video_id}"


async def get_youtube_related_tracks(
    video_info: pomice.Track,
) -> list[str]:
    current_track_id = video_info.identifier
    if not current_track_id:
        logging.warning("current track ID is missing, cannot fetch related tracks")
        return []

    api_payload = {
        "context": {
            "client": {
                "hl": "en",
                "gl": "US",
                "clientName": "WEB",
                "clientVersion": "2.20220809.02.00",
                "originalUrl": "https://www.youtube.com",
                "platform": "DESKTOP",
            },
        },
        "videoId": current_track_id,
        "racyCheckOk": True,
        "contentCheckOk": True,
    }
    async with httpx.AsyncClient() as session:
        response = await session.post(
            "https://www.youtube.com/youtubei/v1/next?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8",
            json=api_payload,
        )

        if response.status_code != 200:
            logging.error(f"failed to fetch related tracks, status code: {response.status_code}")
            return []

        data: dict[str, Any] = response.json()
        try:
            secondary_results = data["contents"]["twoColumnWatchNextResults"]["secondaryResults"]["secondaryResults"][
                "results"
            ]
        except KeyError as e:
            logging.error(f"error parsing related tracks response: {e}")
            return []

        related_tracks: list[str] = []
        for item in secondary_results:
            parsed = _parser_youtube_related_tracks(item)
            if parsed:
                logging.info(f"related track found: {parsed}")
                related_tracks.append(parsed)

        logging.info(f"fetched {len(related_tracks)} related tracks from youtube")
        return related_tracks


@final
class CustomQueue(pomice.Queue):
    def __init__(self) -> None:
        super().__init__()
        self._current_item: pomice.Track | None = None

    @override
    def get(self) -> pomice.Track:
        if self._should_loop_current_track():
            return self._current_item  # type: ignore[return-value]

        if self.is_empty:
            raise pomice.QueueEmpty("No items in the queue.")

        item = self._get_next_item_in_queue_loop() if self._loop_mode == pomice.LoopMode.QUEUE else self._get()
        self._current_item = item
        return item

    def swap(self, index1: int, index2: int) -> None:
        if not (0 <= index1 < len(self._queue)) or not (0 <= index2 < len(self._queue)):
            raise IndexError("Queue index out of range.")

        self._queue[index1], self._queue[index2] = self._queue[index2], self._queue[index1]

    def _should_loop_current_track(self) -> bool:
        return self._loop_mode == pomice.LoopMode.TRACK and self._current_item is not None

    def _get_next_item_in_queue_loop(self) -> pomice.Track:
        if self._is_current_item_invalid():
            return self._queue[0]

        current_index = self._index(self._current_item)
        is_at_end_of_queue = current_index >= len(self._queue) - 1
        return self._queue[0] if is_at_end_of_queue else self._queue[current_index + 1]

    def _is_current_item_invalid(self) -> bool:
        return not self._current_item or self._current_item not in self._queue


class CustomPlayer(pomice.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.np_message_allowed: bool = True
        self.queue: CustomQueue = CustomQueue()
        self.trigger_channel: Messageable | None = None

        self._autoplay_enabled: bool = True
        self._auto_disconnect_enabled: bool = True
        self._auto_disconnect_timeout: int = 300  # seconds

        self._logger: logging.Logger = logging.getLogger(f"CustomPlayer({self.guild.id})")
        self._auto_queue: list[pomice.Track] = []
        self._history: deque[pomice.Track] = deque(maxlen=50)
        self._last_control_message: discord.Message | None = None
        self._inactive_disconnect_task: asyncio.Task[None] | None = None

        # tracker
        self._vote_skip_in_progress: bool = False

        # filter
        self._speed: float = 1.0

        # track error handling
        self._track_errors: dict[str, int] = {}  # track_id -> error_count
        self.__reset_track_error_later_tasks = set()
        self._max_track_errors: int = 3
        self._error_reset_time: int = 300

        self._autoplay_extraction_track: pomice.Track | None = None

    @property
    def vote_skip_in_progress(self) -> bool:
        return self._vote_skip_in_progress

    @asynccontextmanager
    async def vote_skip_context(self):
        self._vote_skip_in_progress = True
        try:
            yield
        finally:
            self._vote_skip_in_progress = False

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
    def history(self) -> deque[pomice.Track]:
        return self._history

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
        self._track_errors.clear()
        self.cancel_disconnect_timer()
        super().cleanup()

    @override
    async def disconnect(self, *, force: bool = False) -> None:
        await self.disable_last_control_view()
        await super().disconnect(force=force)

    @override
    async def get_recommendations(
        self, *, track: pomice.Track, ctx: Context[Nameless] | None = None
    ) -> list[pomice.Track] | pomice.Playlist | None:
        try:
            raise Exception("Force fallback to custom recommendation logic")
            return await super().get_recommendations(track=track, ctx=ctx)
        except Exception:
            if track.track_type is pomice.TrackType.YOUTUBE:
                related_urls = await get_youtube_related_tracks(track)
                if related_urls:
                    tracks: list[pomice.Track] = []
                    # skip the first one as it's usually the current track
                    for _url in related_urls[1:11]:
                        track_item = await self.get_tracks(_url)
                        if track_item and isinstance(track_item, list):
                            tracks.append(track_item[0])
                    return tracks
            return None

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
            self._history.appendleft(self.current)

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
