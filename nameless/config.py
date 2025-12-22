from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tomllib import loads
from typing import get_args, get_origin

__all__ = ["nameless_config"]


@dataclass(eq=False, repr=False, slots=True)
class NamelessMetadata:
    version: str
    description: str
    support_server: str
    start_time: datetime = field(default_factory=datetime.now)


@dataclass(eq=False, repr=False, slots=True)
class NamelessRuntime:
    is_shutting_down: bool = False


@dataclass(eq=False, repr=False, slots=True)
class NamelessCommands:
    prefixes: set[str]
    ignores: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.prefixes = set(self.prefixes)


@dataclass(eq=False, repr=False, slots=True)
class NamelessBlacklist:
    users: list[int] = field(default_factory=list)
    guilds: list[int] = field(default_factory=list)


@dataclass(eq=False, repr=False, slots=True)
class LavalinkNode:
    host: str
    port: int
    password: str
    identifier: str = field(default="")
    secure: bool = False
    region: str | None = None
    auto_start: bool = field(default=False)
    auto_update: bool = field(default=False)

    def __post_init__(self):
        if not self.identifier:
            self.identifier = f"{self.host}:{self.port}"


@dataclass(eq=False, repr=False, slots=True)
class NamelessDevConfig:
    enabled: bool
    debug: bool
    server_sync_ids: list[int] = field(default_factory=list[int])


@dataclass(eq=False, repr=False, slots=True)
class NamelessConfig:
    nameless: NamelessMetadata
    command: NamelessCommands
    dev: NamelessDevConfig
    runtime: NamelessRuntime = field(default_factory=NamelessRuntime)
    blacklist: NamelessBlacklist = field(default_factory=NamelessBlacklist)
    lavalinks: list[LavalinkNode] = field(default_factory=list[LavalinkNode])

    def __post_init__(self):
        for key_name, value_type in self.__annotations__.items():
            value = getattr(self, key_name)

            if not isinstance(value, dict | list):
                continue

            origin = get_origin(value_type)
            if origin is list:
                args = get_args(value_type)
                if args and isinstance(value, list):
                    item_class = args[0]
                    if hasattr(item_class, "__dataclass_fields__"):
                        converted = [item_class(**item) if isinstance(item, dict) else item for item in value]
                        setattr(self, key_name, converted)

            elif isinstance(value, dict):
                if hasattr(value_type, "__dataclass_fields__"):
                    setattr(self, key_name, value_type(**value))


_cfg_path: Path = Path(__file__).parent.parent.absolute() / "nameless.toml"
with _cfg_path.open(encoding="utf-8") as f:
    _content: str = f.read()

nameless_config: NamelessConfig = NamelessConfig(**loads(_content))
