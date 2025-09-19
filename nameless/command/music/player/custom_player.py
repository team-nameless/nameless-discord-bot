# pyright:reportArgumentType=false

from typing import cast, override

import discord
import pomice
from discord.abc import Messageable

from ..views import MusicControlView


class CustomPlayer(pomice.Player):
    def __init__(self, *args, **kwargs):  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
        super().__init__(*args, **kwargs)  # pyright: ignore[reportUnknownArgumentType]

        self.play_now_allowed: bool = True
        self.queue: pomice.Queue = pomice.Queue()
        self.trigger_channel: Messageable | None = None

        self.is_autoplaying: bool = False

        self._auto_queue: list[pomice.Track] = []
        self._last_control_message: discord.Message | None = None

    @property
    def auto_queue(self) -> list[pomice.Track]:
        return self._auto_queue

    def toggle_play_now(self) -> None:
        self.play_now_allowed = not self.play_now_allowed

    def clear_auto_queue(self) -> None:
        self.auto_queue.clear()

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
        channel: Messageable,
        content: str | None = None,
        *,
        interaction: discord.Interaction | None = None,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
        delete_after: float | None = None,
        silent: bool = False,
        mention_author: bool = False,
    ) -> discord.Message | None:
        if view and isinstance(view, MusicControlView):
            await self._disable_last_control_view()

        if interaction:
            if interaction.response.is_done():
                return None

            await interaction.response.send_message(
                content=content,
                embed=embed,
                delete_after=delete_after,
                silent=silent,
                mention_author=mention_author,
                view=view,
            )
            return cast(discord.Message, await interaction.original_response())

        message = cast(
            discord.Message,
            await channel.send(
                content=content,
                embed=embed,
                delete_after=delete_after,
                silent=silent,
                mention_author=mention_author,
                view=view,
            ),
        )

        if view and isinstance(view, MusicControlView):
            self._last_control_message = message

        return message

    async def send_to_trigger_channel(
        self,
        content: str | None = None,
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
            self.trigger_channel,
            content=content,
            embed=embed,
            delete_after=delete_after,
            silent=silent,
            mention_author=mention_author,
            view=view,
        )
