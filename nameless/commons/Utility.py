from urllib.parse import urlparse

__all__ = ["Utility"]


class Utility:
    @staticmethod
    def is_an_url(url: str) -> bool:
        return urlparse(url).netloc != ""
