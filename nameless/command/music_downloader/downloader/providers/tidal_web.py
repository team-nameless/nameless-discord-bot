from typing import NotRequired, TypedDict, Unpack

from nameless.command.music_downloader.downloader.providers.base import BaseProvider


class TidalWebOptions(TypedDict):
    publicToken: NotRequired[str]
    countryCode: NotRequired[str]
    locale: NotRequired[str]
    deviceType: NotRequired[str]
    downloadApiUrl: NotRequired[str]


class TidalWebProvider(BaseProvider):
    name = "tidal"
    extension_id = "tidal-web"

    def __init__(self, **kwargs: Unpack[TidalWebOptions]) -> None:
        super().__init__(**kwargs)
