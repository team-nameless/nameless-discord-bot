__all__ = ["create_cache_key"]


def create_cache_key(*values: str) -> str:
    """Create cache key."""
    return f"({','.join(values)})"
