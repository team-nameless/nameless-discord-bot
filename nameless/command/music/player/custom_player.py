import discord
import pomice
from discord.abc import Messageable


class CustomPlayer(pomice.Player):
    """Extend the base Player class with custom functionality.

    Here is only the placeholder for future custom methods and attributes.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.play_now_allowed: bool = True
        self.queue: pomice.Queue = pomice.Queue()
        self.trigger_channel: Messageable | None = None

        self.is_autoplaying: bool = False

        self._auto_queue: list[pomice.Track] = []

    @property
    def auto_queue(self) -> list[pomice.Track]:
        """The autoplay queue."""
        return self._auto_queue

    def toggle_play_now(self) -> None:
        """Toggle the play now feature."""
        self.play_now_allowed = not self.play_now_allowed

    def clear_auto_queue(self) -> None:
        """Clear the autoplay queue."""
        self.auto_queue.clear()

    def toggle_autoplay(self) -> None:
        """Toggle the autoplay feature."""
        self.is_autoplaying = not self.is_autoplaying

    async def refresh_auto_queue(self) -> None:
        """Refresh the autoplay queue."""
        if not self.current:
            self._auto_queue.clear()
            return

        tracks = await self.get_recommendations(track=self.current)
        if not tracks:
            self._auto_queue.clear()
            return

        if isinstance(tracks, list):
            self._auto_queue = tracks
        elif isinstance(tracks, pomice.Playlist):
            self._auto_queue = tracks.tracks.copy()
        else:
            raise TypeError("Expected a list of tracks or a playlist.")

    async def send_to_trigger(
        self,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
        delete_after: float | None = None,
        silent: bool = False,
        mention_author: bool = False,
    ) -> None:
        """Send a message to the trigger channel if available.

        Args:
            content (str | discord.Embed): The content to send.
        """
        if self.trigger_channel is None:
            return

        await self.trigger_channel.send(  # type: ignore
            content=content,
            embed=embed,  # type: ignore
            delete_after=delete_after,  # type: ignore
            silent=silent,
            mention_author=mention_author,
            view=view,  # type: ignore
        )
