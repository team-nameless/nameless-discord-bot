# pyright:reportArgumentType=false

import asyncio
from typing import cast, override

import discord
import pomice
from discord.abc import Messageable

from ..views import MusicControlView


class CustomPlayer(pomice.Player):
    def __init__(self, *args, timeout=300, **kwargs):  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
        super().__init__(*args, **kwargs)  # pyright: ignore[reportUnknownArgumentType]

        self.play_now_allowed: bool = True
        self.queue: pomice.Queue = pomice.Queue()
        self.trigger_channel: Messageable | None = None

        self.is_autoplaying: bool = False

        self._auto_queue: list[pomice.Track] = []
        self._last_control_message: discord.Message | None = None
        self._inactive_disconnect_task: asyncio.Task[None] | None = None

    @property
    def auto_queue(self) -> list[pomice.Track]:
        return self._auto_queue

    def toggle_play_now(self) -> None:
        self.play_now_allowed = not self.play_now_allowed

    def clear_auto_queue(self) -> None:
        self.auto_queue.clear()

    def start_disconnect_timer(self) -> None:
        self.cancel_disconnect_timer()
        self._inactive_disconnect_task = asyncio.create_task(self._disconnect_after_timeout())

    async def _disconnect_after_timeout(self) -> None:
        try:
            await asyncio.sleep(300)
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

    @override
    def cleanup(self) -> None:
        self.queue.clear()
        self._auto_queue.clear()
        self.cancel_disconnect_timer()
        super().cleanup()

    @override
    async def disconnect(self, *, force: bool = False) -> None:
        await self._disable_last_control_view()
        await super().disconnect(force=force)

    def toggle_autoplay(self) -> None:
        self.is_autoplaying = not self.is_autoplaying

    async def refresh_auto_queue(self) -> None:
        if not self.current:
            self._auto_queue.clear()
            return

        tracks = await self.get_recommendations(track=self.current)  # pyright: ignore[reportUnknownMemberType]
        if not tracks:
            self._auto_queue.clear()
            return
        if isinstance(tracks, list):
            self._auto_queue = tracks
        else:
            self._auto_queue = tracks.tracks.copy()

    async def _disable_last_control_view(self) -> None:
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
            await self._disable_last_control_view()

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
            discord.Message,
            await messageable.send(
                content=content,
                embed=embed,
                view=view,
                delete_after=delete_after,
                silent=silent,
                mention_author=mention_author,
            ),
        )
