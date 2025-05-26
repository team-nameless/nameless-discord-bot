from datetime import datetime
from pathlib import Path
from tomllib import loads
from typing import TypedDict

__all__ = ["nameless_config"]


class NamelessMetadata(TypedDict):
    version: str
    description: str
    support_server: str
    start_time: datetime
    is_shutting_down: bool


class NamelessCommands(TypedDict):
    prefixes: list[str]


class NamelessBlacklist(TypedDict):
    users: list[int]
    guilds: list[int]


class NamelessConfig(TypedDict):
    nameless: NamelessMetadata
    command: NamelessCommands
    blacklist: NamelessBlacklist


_cfg_path: Path = Path(__file__).parent.parent.absolute() / "nameless.toml"

with open(_cfg_path, encoding="utf-8") as f:
    _content: str = f.read()

# Maybe add a type checker here, using the annotation from the TypedDict
nameless_config: NamelessConfig = NamelessConfig(**loads(_content))  # pyright: ignore[reportAny]
