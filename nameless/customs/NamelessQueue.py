import asyncio
from enum import Enum

from wavelink import Playable, Playlist, Queue

__all__ = ["QueueAction", "NamelessQueue"]


class QueueAction(Enum):
    ADD = 0
    INSERT = 1


class NamelessQueue(Queue):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _insert(self, item: Playable) -> None:
        self._check_compatability(item)
        self._queue.insert(0, item)

    def insert(self, item: Playable | Playlist, /, *, atomic: bool = True) -> int:
        added: int = 0

        if isinstance(item, Playlist):
            if atomic:
                self._check_atomic(item)

            for track in item:
                try:
                    self._insert(track)
                    added += 1
                except TypeError:
                    pass

        else:
            self._insert(item)
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
                        self._insert(track)
                        added += 1
                    except TypeError:
                        pass

                    await asyncio.sleep(0)

            else:
                self._insert(item)
                added += 1
                await asyncio.sleep(0)

        self._wakeup_next()
        return added
