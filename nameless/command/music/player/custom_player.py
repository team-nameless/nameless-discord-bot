# pyright:reportArgumentType=false, reportIncompatibleVariableOverride=false
from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections import deque
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast, final, override

import discord
import httpx
import pomice

from nameless.custom.track_cache import track_info_cache

from ..exceptions import AutoplayPopulateError
from ..ui.embeds import create_now_playing_embed
from ..ui.views import MusicControlView

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


def time_string_to_seconds(time_str: str | Any) -> float:
    if not time_str or not isinstance(time_str, str):
        logging.debug(f"invalid time string: {time_str}")
        return 0.0

    time_str = time_str.strip()
    if not time_str:
        return 0.0

    try:
        parts = time_str.split(":")
        if len(parts) > 3:
            logging.warning(f"time string has too many parts: {time_str}")
            return 0.0

        time_parts: list[int] = []
        for part in reversed(parts):
            try:
                time_parts.append(int(part))
            except ValueError:
                logging.warning(f"invalid time component '{part}' in: {time_str}")
                return 0.0

        total_seconds = 0.0
        multipliers = [1, 60, 3600]

        for i, value in enumerate(time_parts):
            if i < len(multipliers):
                total_seconds += value * multipliers[i]
            else:
                logging.warning(f"too many time components in: {time_str}")
                break

        logging.debug(f"converted '{time_str}' to {total_seconds} seconds")
        return total_seconds

    except Exception as e:
        logging.error(f"error converting time string '{time_str}': {e}")
        return 0.0


def get_and_cast[T](d: Mapping[str, Any], key: str | Iterable[str | int], default: T = None, strict: bool = False) -> T:
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

    if not strict:
        return cast("T", value)

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
    if view_count < 2000:
        return None

    duration = time_string_to_seconds(
        get_and_cast(
            lockup_view_model,
            (
                "contentImage",
                "thumbnailViewModel",
                "overlays",
                0,
                "thumbnailOverlayBadgeViewModel",
                "thumbnailBadges",
                0,
                "thumbnailBadgeViewModel",
                "text",
            ),
            "0:00",
        )
    )
    if duration < 30 or duration > 540:
        return None

    return f"https://www.youtube.com/watch?v={video_id}"


@track_info_cache
async def get_youtube_related_tracks(current_track_id: str) -> list[str]:
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
            secondary_results = get_and_cast(
                data,
                (
                    "contents",
                    "twoColumnWatchNextResults",
                    "secondaryResults",
                    "secondaryResults",
                    "results",
                ),
                [],
                strict=True,
            )
            # secondary_results
            # data["contents"]["twoColumnWatchNextResults"]["secondaryResults"]["secondaryResults"]["results"]
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
        self.trigger_channel: Messageable | None = None
        self.queue: CustomQueue = CustomQueue()

        self._autoplay_enabled: bool = True
        self._refresh_autoplay_on_track_end: bool = True
        self._auto_disconnect_enabled: bool = True
        self._auto_disconnect_timeout: int = 300  # seconds

        self._logger: logging.Logger = logging.getLogger(f"CustomPlayer({self.guild.id})")
        self._auto_queue: deque[pomice.Track | str] = deque()
        self._history: deque[pomice.Track] = deque(maxlen=100)
        self._last_control_message: discord.Message | None = None
        self._inactive_disconnect_task: asyncio.Task[None] | None = None

        # tracker
        self._vote_skip_in_progress: bool = False
        self._is_current_track_autoplay: bool = False

        # filter
        ## timescale
        self.speed = 1.0
        self.pitch = 1.0
        self._rate = 1.0
        ## eq
        self.eq_bands: dict[int, float] = {}

        self._autoplay_extraction_track: pomice.Track | None = None
        self._max_play_errors: int = 4

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
    def auto_queue(self) -> deque[pomice.Track | str]:
        return self._auto_queue

    @property
    def history(self) -> deque[pomice.Track]:
        return self._history

    @property
    def total_duration(self) -> int:
        return sum(track.length for track in self.queue)

    @property
    def rate(self) -> float:
        return self._rate

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

    @override
    def cleanup(self) -> None:
        self.queue.clear()
        self._auto_queue.clear()
        self._history.clear()
        self.cancel_disconnect_timer()
        super().cleanup()

    @override
    async def disconnect(self, *, force: bool = False) -> None:
        await self.disable_last_control_view()
        await super().disconnect(force=force)

    async def _get_youtube_recommendations(self, track: pomice.Track) -> list[str] | None:
        related_urls = await get_youtube_related_tracks(track.identifier)
        if not related_urls:
            return

        return related_urls[1:]

    async def _get_youtube_music_recommendations(self, track: pomice.Track) -> list[pomice.Track] | None:
        pl_id = f"RDAMVM{track.identifier}"
        pl_url = f"ytsearch:https://www.youtube.com/watch?v={track.identifier}&list={pl_id}"
        try:
            track_list = await self.get_tracks(query=pl_url, ctx=None)
            if isinstance(track_list, pomice.Playlist):
                return track_list.tracks[1:]
            return track_list[1:] if track_list else None
        except Exception as e:
            logging.error(f"error fetching YouTube Music recommendations: {e}")
            return None

    async def custom_get_recommendations(
        self, *, track: pomice.Track, ctx: Context[Nameless] | None = None
    ) -> list[str] | list[pomice.Track] | pomice.Playlist | None:
        result = None
        with contextlib.suppress(pomice.TrackLoadError):
            result = await super().get_recommendations(track=track, ctx=ctx)

        if result:
            return result

        if track.track_type is not pomice.TrackType.YOUTUBE:
            return

        result = await self._get_youtube_music_recommendations(track)
        if result:
            return result
        logging.warning("Failed to get YouTube Music recommendations, falling back to standard YouTube.")

        return await self._get_youtube_recommendations(track)

    def toggle_autoplay(self) -> bool:
        self._autoplay_enabled = not self._autoplay_enabled
        return self._autoplay_enabled

    async def refresh_auto_queue(self) -> None:
        current = self.current or self._autoplay_extraction_track
        if not current:
            self._auto_queue.clear()
            return

        related_result = await self.custom_get_recommendations(track=current)
        if not related_result:
            self._auto_queue.clear()
            return

        if isinstance(related_result, list):
            self._auto_queue.extend(related_result)
        else:
            self._auto_queue.extend(related_result.tracks)

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

    async def _update_timescale_filter(self) -> None:
        timescale = pomice.Timescale(
            speed=self.speed,
            pitch=self.pitch,
            rate=self._rate,
        )
        if self.filters.has_filter("timescale"):
            await self.edit_filter("timescale", timescale)
        else:
            await self.add_filter("timescale", timescale)

    async def set_speed(self, speed: float) -> None:
        self.speed = speed
        await self._update_timescale_filter()

    async def set_pitch(self, pitch: float) -> None:
        self.pitch = pitch
        await self._update_timescale_filter()

    async def set_rate(self, rate: float) -> None:
        self._rate = rate
        await self._update_timescale_filter()

    async def set_eq_band(self, band: int, gain: float) -> None:
        if not 0 <= band <= 14:
            raise ValueError("Band must be 0-14")
        if not -0.25 <= gain <= 1.0:
            raise ValueError("Gain must be -0.25 to 1.0")

        self.eq_bands[band] = gain
        await self._update_equalizer()

    async def reset_eq(self) -> None:
        self.eq_bands.clear()
        if self.filters.has_filter(filter_tag="equalizer"):
            await self.remove_filter(filter_tag="equalizer")

    async def _update_equalizer(self) -> None:
        levels = [(band, gain) for band, gain in self.eq_bands.items()]
        eq_filter = pomice.Equalizer(tag="equalizer", levels=levels)

        if self.filters.has_filter(filter_tag="equalizer"):
            await self.edit_filter(filter_tag="equalizer", edited_filter=eq_filter)
        else:
            await self.add_filter(eq_filter)

    @track_info_cache
    async def get_track(
        self,
        query: str,
        *,
        ctx: Context[Nameless] | None = None,
        search_type: pomice.SearchType = pomice.SearchType.ytsearch,
        filters: pomice.Filters | None = None,
    ):
        tracks = await super().get_tracks(query, ctx=ctx, search_type=search_type, filters=filters)
        if not tracks:
            return None
        if isinstance(tracks, pomice.Playlist):
            return tracks.tracks[0]
        return tracks[0]

    async def _play_with_retries(self, track: pomice.Track, *args, **kwargs) -> bool:
        for attempt in range(self._max_play_errors):
            try:
                if attempt + 1 == self._max_play_errors:
                    self._logger.error(f"Final attempt to play track {track.title}")
                    _track = await self.get_track(query=track.uri, ctx=None)  # reload track info
                    if not _track:
                        self._logger.error(f"Failed to reload track info for {track.title}, skipping.")
                        return False
                    track = _track

                await self.play(track, *args, **kwargs)
                return True
            except Exception as e:
                logging.error(
                    "Error playing track %s (attempt %d/%d): %s",
                    track.title,
                    attempt + 1,
                    self._max_play_errors,
                    e,
                    exc_info=True,
                )
                await asyncio.sleep(1)

        logging.error("Max play attempts reached for track %s, skipping.", track.title)
        return False

    async def _get_next_auto_track(self) -> pomice.Track | None:
        if self._refresh_autoplay_on_track_end and self.queue.is_empty and not self._is_current_track_autoplay:
            await self.refresh_auto_queue()

        while self._auto_queue:
            next_track = self._auto_queue.popleft()
            if isinstance(next_track, str):
                next_track_obj = await self.get_track(next_track)
                if not next_track_obj:
                    self._logger.warning(f"Failed to get track recommendation for '{next_track}', skipping.")
                    continue
                next_track = next_track_obj

            return next_track
        return None

    async def do_next(self):
        if self.current:
            self._history.appendleft(self.current)

        while not self.queue.is_empty:
            try:
                next_track = self.queue.get()
            except pomice.QueueEmpty:
                break

            success = await self._play_with_retries(next_track)
            if success:
                self._is_current_track_autoplay = False
                return

        if not self.is_autoplay_enabled:
            # nothing left to play
            self.start_disconnect_timer()
            return

        next_auto_track = await self._get_next_auto_track()
        if not next_auto_track:
            self.start_disconnect_timer()
            raise AutoplayPopulateError()

        await self._play_with_retries(next_auto_track)
        self._is_current_track_autoplay = True

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
