from typing import Literal, NotRequired, TypedDict, Unpack

from nameless.command.music_downloader.downloader.providers.base import BaseProvider


class YoutubeMusicWebOptions(TypedDict):
    poTokenMode: NotRequired[Literal["off", "auto", "external", "manual"]]
    poTokenProviderUrl: NotRequired[str]
    manualGvsPoToken: NotRequired[bool]
    logLevel: NotRequired[Literal["error", "warn", "info", "debug"]]


class YoutubeMusicWebProvider(BaseProvider):
    name = "youtube"
    extension_id = "ytmusic-spotiflac"

    def __init__(self, **kwargs: Unpack[YoutubeMusicWebOptions]) -> None:
        super().__init__(**kwargs)
