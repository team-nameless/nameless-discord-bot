from typing import NotRequired, TypedDict, Unpack

from nameless.command.music_downloader.downloader.providers.base import BaseProvider


class DeezerOptions(TypedDict):
    apiBaseUrl: NotRequired[str]


class DeezerWebProvider(BaseProvider):
    name = "deezer"
    extension_id = "deezer"

    def __init__(self, **kwargs: Unpack[DeezerOptions]) -> None:
        super().__init__(**kwargs)
