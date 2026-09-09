# ruff: noqa: F401

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import re
from typing import Any

import httpx

from .base import LyricsBase


class SpotifyLyrics(LyricsBase):
    name = "spotify"

    def get_data(self) -> None:
        resp = self.session.get(f"https://spotify-lyrics-api-yeah.vercel.app/api/lyrics?url={self.spotify_id}")
        if resp.status_code in (200, 404):
            self.cache = resp.json()
        else:
            self.logger.error(f"Failed to fetch lyrics from Spotify API: {resp.status_code} {resp.text}")
            self.cache = None
        super().post_init()

    def get_unsynced(self) -> str | None:
        if not self.cache:
            self.get_data()

        if not self.cache or "lyrics" not in self.cache:
            return None

        return self.cache["lyrics"]
