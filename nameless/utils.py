from urllib.parse import urlparse


def is_an_url(url: str) -> bool:
    """Verifies if the provided string is a URL."""
    return urlparse(url).netloc != ""
