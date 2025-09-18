from datetime import datetime
from pathlib import Path
from tomllib import loads
from typing import NotRequired, TypedDict

__all__ = ["nameless_config"]


class NamelessMetadata(TypedDict):
    version: str
    description: str
    support_server: str
    start_time: datetime


class NamelessRuntime(TypedDict):
    is_shutting_down: bool


class NamelessCommands(TypedDict):
    prefixes: list[str]
    ignores: NotRequired[list[str]]


class NamelessBlacklist(TypedDict):
    users: list[int]
    guilds: list[int]


class LavalinkNode(TypedDict):
    host: str
    port: int
    password: str
    identifier: str
    region: NotRequired[str]
    auto_start: NotRequired[bool]
    auto_update: NotRequired[bool]


class NamelessConfig(TypedDict):
    nameless: NamelessMetadata
    command: NamelessCommands
    runtime: NamelessRuntime
    blacklist: NamelessBlacklist
    lavalinks: list[LavalinkNode]


_cfg_path: Path = Path(__file__).parent.parent.absolute() / "nameless.toml"

with open(_cfg_path, encoding="utf-8") as f:
    _content: str = f.read()

# Maybe add a type checker here, using the annotation from the TypedDict
nameless_config: NamelessConfig = NamelessConfig(**loads(_content), runtime={"is_shutting_down": False})
