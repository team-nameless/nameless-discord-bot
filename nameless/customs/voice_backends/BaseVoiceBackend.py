import asyncio
import json
from typing import Optional

import aiohttp
import wavelink
from wavelink import NodePool, TrackEventPayload
from wavelink.enums import TrackSource
from wavelink.exceptions import QueueEmpty


class Player(wavelink.Player):
    @staticmethod
    async def requests(http_session: aiohttp.ClientSession, url, *args, **kwargs) -> Optional[dict]:
        async with http_session.post(url, *args, **kwargs) as resp:
            if resp.status == 200:
                try:
                    return await resp.json()
                except json.JSONDecodeError:
                    return None

            raise asyncio.InvalidStateError(f"Failed to get {url}: Get {resp.status}")

    async def _populate_youtube(
        self, session: aiohttp.ClientSession, track: wavelink.Playable
    ) -> Optional[list[wavelink.Playable]]:
        data = await self.requests(
            session,
            "https://www.youtube.com/youtubei/v1/next?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8",
            json={
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
                "videoId": track.identifier,
                "racyCheckOk": True,
                "contentCheckOk": True,
            },
            headers={
                "Origin": "https://www.youtube.com",
                "Referer": "https://www.youtube.com/",
            },
        )

        if not data:
            return

        related = data["contents"]["twoColumnWatchNextResults"]["secondaryResults"]["secondaryResults"]["results"]

        for item in related:
            res = item.get("compactRadioRenderer", False)

            if not res:
                continue

            playlist = await NodePool.get_playlist(res["shareUrl"], cls=wavelink.YouTubePlaylist, node=None)  # type: ignore  # noqa: E501
            return playlist.tracks  # type: ignore

        playlist = []
        for item in related:
            res = item.get("compactVideoRenderer", False)

            if not res:
                continue

            playlist.append(await NodePool.get_tracks(f"https://www.youtube.com/watch?v={res['videoId']}", wavelink.YouTubeTrack)[0])  # type: ignore  # noqa: E501
        return playlist

    async def _populate_local(self, session: aiohttp.ClientSession, track: wavelink.Playable):
        pass

    async def _populate_soundcloud(self, session: aiohttp.ClientSession, track: wavelink.Playable):
        pass

    async def _populate_ytmusic(self, session: aiohttp.ClientSession, track: wavelink.Playable):
        pass

    async def _populate(self, payload: TrackEventPayload):
        func_ = {
            TrackSource.Local: self._populate_local,
            TrackSource.YouTube: self._populate_youtube,
            TrackSource.SoundCloud: self._populate_soundcloud,
            TrackSource.YouTubeMusic: self._populate_youtube,
        }
        node = NodePool().get_node()
        return await func_[payload.track.source](node._session, payload.track)

    async def _auto_play_event(self, payload: TrackEventPayload) -> None:
        if not self.autoplay:
            return

        if payload.reason == "REPLACED":
            return

        if self.queue.loop:
            try:
                track = self.queue.get()
            except QueueEmpty:
                return

            await self.play(track)  # pyright: ignore
            return

        if self.queue:
            populate = len(self.auto_queue) < self._auto_threshold
            await self.play(self.queue.get(), populate=populate)  # pyright: ignore

            return

        if not self.auto_queue:
            _q = await self._populate(payload)
            if _q:
                for t in _q:
                    self.auto_queue.put(t)

        await self.queue.put_wait(await self.auto_queue.get_wait())
        populate = self.auto_queue.is_empty

        await self.play(await self.queue.get_wait(), populate=populate)  # pyright: ignore
