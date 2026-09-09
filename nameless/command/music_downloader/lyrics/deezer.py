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


class DeezerLyrics(LyricsBase): ...
