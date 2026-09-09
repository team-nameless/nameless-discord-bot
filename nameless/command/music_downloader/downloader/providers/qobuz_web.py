from typing import NotRequired, TypedDict, Unpack

from nameless.command.music_downloader.downloader.providers.base import BaseProvider


class QobuzWebOptions(TypedDict):
    apiBaseUrl: NotRequired[str]
    fallbackApiBaseUrl: NotRequired[str]
    appId: NotRequired[str]
    countryCode: NotRequired[str]


class QobuzWebProvider(BaseProvider):
    name = "qobuz"
    extension_id = "qobuz-web"

    def __init__(self, **kwargs: Unpack[QobuzWebOptions]) -> None:
        super().__init__(**kwargs)
