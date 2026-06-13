from typing import NotRequired, TypedDict, Unpack

from nameless.command.music_downloader.downloader.providers.base import BaseProvider


class AppleMusicOptions(TypedDict):
    storefront: NotRequired[str]
    mediaUserToken: NotRequired[str]
    lyricsTranslation: NotRequired[str]
    lyricsPronunciation: NotRequired[str]
    proxyApiKey: NotRequired[str]
    downloadPollIntervalMs: NotRequired[int]
    downloadMaxWaitMinutes: NotRequired[int]


class AppleMusicWebProvider(BaseProvider):
    name = "apple"
    extension_id = "apple-music"

    def __init__(self, **kwargs: Unpack[AppleMusicOptions]) -> None:
        super().__init__(**kwargs)
