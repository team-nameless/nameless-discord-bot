from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import cachetools

__all__ = ["track_info_cache"]

_CACHE_MAX_SIZE = 250
_CACHE_TTL = 3600

_track_cache: cachetools.TTLCache[str, Any] = cachetools.TTLCache(
    maxsize=_CACHE_MAX_SIZE,
    ttl=_CACHE_TTL,
)


def track_info_cache[F: Callable[..., Awaitable[Any]]](func: F) -> F:
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        cache_key = _build_cache_key(func.__name__, args, kwargs)

        if cache_key in _track_cache:
            logging.debug(f"Cache hit for {func.__name__} with key: {cache_key}")
            return _track_cache[cache_key]

        result = await func(*args, **kwargs)

        _track_cache[cache_key] = result
        logging.debug(f"Cached result for {func.__name__} with key: {cache_key}")

        return result

    return wrapper  # type: ignore


def _build_cache_key(func_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    filtered_args = tuple(
        arg for arg in args if not isinstance(arg, object) or isinstance(arg, (str, int, float, bool))
    )

    args_str = "|".join(str(arg) for arg in filtered_args)
    kwargs_str = "|".join(f"{k}={v}" for k, v in sorted(kwargs.items()))

    return f"{func_name}:{args_str}:{kwargs_str}"
