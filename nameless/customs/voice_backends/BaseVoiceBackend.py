import asyncio
from collections.abc import Iterator

import wavelink
from wavelink import AutoPlayMode, Playable, Playlist, Queue


class PriorityQueue(Queue):
    def __init__(self, history=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._priority_queue = Queue(history=history)

    def insert(self, item: Playable | Playlist, /, *, atomic: bool = True) -> int:
        added: int = 0

        if isinstance(item, Playlist):
            if atomic:
                self._check_atomic(item)

            for track in item:
                try:
                    self._priority_queue._put(track)
                    added += 1
                except TypeError:
                    pass

        else:
            self._priority_queue._put(item)
            added += 1

        return added

    async def insert_wait(self, item: list[Playable] | Playable | Playlist, /, *, atomic: bool = True) -> int:
        added: int = 0

        async with self._lock:
            if isinstance(item, list | Playlist):
                if atomic:
                    super()._check_atomic(item)

                for track in item:
                    try:
                        self._priority_queue._put(track)
                        added += 1
                    except TypeError:
                        pass

                    await asyncio.sleep(0)

            else:
                self._priority_queue._put(item)
                added += 1
                await asyncio.sleep(0)

        self._wakeup_next()
        return added

    def get(self) -> Playable:
        if self._priority_queue:
            return self._priority_queue._get()
        return self._get()

    def __iter__(self) -> Iterator[Playable]:
        if self._priority_queue:
            yield from self._priority_queue
        yield from self._queue.__iter__()


class Player(wavelink.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.autoplay = wavelink.AutoPlayMode.partial
        self.queue: PriorityQueue = PriorityQueue()

        self._cog = None  # maybe useful for later
        self._should_send_play_now = True
        self._play_now_allowed = True
        self._trigger_channel_id = self.channel.id
        self._auto_play_queue = True

    @property
    def auto_play_queue(self) -> bool:
        return self._auto_play_queue

    @auto_play_queue.setter
    def auto_play_queue(self, value: bool):
        self._auto_play_queue = value

    @property
    def should_send_play_now(self) -> bool:
        return self._should_send_play_now

    @should_send_play_now.setter
    def should_send_play_now(self, value: bool):
        self._should_send_play_now = value

    @property
    def play_now_allowed(self) -> bool:
        """
        Check if 'Now playing' message should be sent.
        """
        return self._play_now_allowed

    @play_now_allowed.setter
    def play_now_allowed(self, value: bool):
        self._play_now_allowed = value

    @property
    def trigger_channel_id(self) -> int:
        """
        Store channel Id that triggered this player.
        """
        return self._trigger_channel_id

    @trigger_channel_id.setter
    def trigger_channel_id(self, value: int):
        self._trigger_channel_id = value

    async def repopulate_auto_queue(self):
        """
        Repopulate autoplay queue. This snippet is copy from wavelink `_auto_play_event`.
        """
        if self.autoplay is AutoPlayMode.enabled:
            async with self._auto_lock:
                self.auto_queue.clear()
                await self._do_recommendation()

    async def toggle_autoplay(self) -> bool:
        """
        Toggle autoplay like the one on Youtube, also repopulates autoplay queue base on new value.

        Returns
        -------
        :class:`bool`
            True if autoplay is enabled, False if disabled.
        """
        if self.autoplay is AutoPlayMode.enabled:
            self.autoplay = AutoPlayMode.partial
            return False

        self.autoplay = AutoPlayMode.enabled
        return True
