from datetime import datetime
from pathlib import Path
from tomllib import loads
from typing import NotRequired, TypedDict

__all__ = ["nameless_config"]


class NamelessInfo(TypedDict):
    version: str
    description: str
    support_server: str
    start_time: datetime
    is_shutting_down: bool


class NamelessBlacklist(TypedDict):
    users: list[int]
    guilds: list[int]


class WavelinkNode(TypedDict):
    uri: str
    password: str
    region: NotRequired[str]
    auto_start: NotRequired[bool]
    auto_update: NotRequired[bool]


class NamelessConfig(TypedDict):
    nameless: NamelessInfo
    blacklist: NamelessBlacklist
    wavelinks: list[WavelinkNode]


_cfg_path: Path = Path(__file__).parent.parent.absolute() / "nameless.toml"

with open(_cfg_path, encoding="utf-8") as f:
    _content: str = f.read()

raw_config = loads(_content)
nameless_config: NamelessConfig = NamelessConfig(**raw_config)  # pyright: ignore[reportAny]
