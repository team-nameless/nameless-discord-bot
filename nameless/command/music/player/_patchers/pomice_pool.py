from __future__ import annotations

import pomice


async def _patch_get_recommendations(
    self: pomice.Node,
    *,
    track: pomice.Track,
    **kwargs,
) -> list[pomice.Track] | pomice.Playlist | None:
    if track.track_type == pomice.TrackType.SPOTIFY:
        results = await self._spotify_client.get_recommendations(query=track.uri)  # type: ignore
        tracks = [
            pomice.Track(
                track_id=track.id,
                ctx=None,
                track_type=pomice.TrackType.SPOTIFY,
                info={
                    "title": track.name,
                    "author": track.artists,
                    "length": track.length,
                    "identifier": track.id,
                    "uri": track.uri,
                    "isStream": False,
                    "isSeekable": True,
                    "position": 0,
                    "thumbnail": track.image,
                    "isrc": track.isrc,
                },
                requester=self.bot.user,
            )
            for track in results
        ]
        return tracks

    elif track.track_type == pomice.TrackType.YOUTUBE:
        return await self.get_tracks(
            query=f"https://www.youtube.com/watch?v={track.identifier}&list=RD{track.identifier}",
            ctx=None,
        )

    else:
        raise pomice.TrackLoadError(
            "The specfied track must be either a YouTube or Spotify track to recieve recommendations.",
        )


def apply_pool_get_recommendations_patch():
    if getattr(pomice.Node, "_unpatched_get_recommendations", False):
        return

    method_name = "get_recommendations"
    original_method = getattr(pomice.Node, method_name, None)
    if original_method is None:
        raise RuntimeError(f"Could not find method '{method_name}' on 'pomice.Node' to patch.")

    setattr(pomice.Node, method_name, _patch_get_recommendations)
    setattr(pomice.Node, "_unpatched_get_recommendations", original_method)  # noqa
