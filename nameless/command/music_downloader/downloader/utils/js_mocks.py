# pyright: reportPrivateImportUsage=false
# ruff: noqa: S304, S324, S305
from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

import httpx
import mutagen
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

if TYPE_CHECKING:
    from collections.abc import Callable

    from .._quickjs_types import Context as JsContext
    from ..providers._manifest import ProviderManifest


logger = logging.getLogger("JsMocks")
# logger.setLevel(logging.DEBUG)

session = httpx.Client(
    headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        )
    },
    http2=True,
)


class UrlMock:
    def parse_url(self, url_str: str) -> str:
        logger.debug("parse_url has been called with url_str=%s", url_str)
        parsed = urlparse(url_str)
        return json.dumps(
            {
                "href": url_str,
                "origin": f"{parsed.scheme}://{parsed.netloc}",
                "protocol": parsed.scheme + ":" if parsed.scheme else "",
                "host": parsed.netloc,
                "hostname": parsed.hostname or "",
                "port": str(parsed.port) if parsed.port else "",
                "pathname": parsed.path,
                "search": f"?{parsed.query}" if parsed.query else "",
                "hash": f"#{parsed.fragment}" if parsed.fragment else "",
            }
        )

    def parse_search_params(self, query_str: str):
        logger.debug("parse_search_params has been called with query_str=%s", query_str)
        parsed = parse_qs(query_str.lstrip("?"), keep_blank_values=True)
        return json.dumps({k: v[0] if len(v) == 1 else v for k, v in parsed.items()})


class HttpMock:
    def get(self, url: str, headers_json: Any = None) -> str:
        logger.debug("get has been called with url=%s, headers_json=%s", url, headers_json)
        headers_dict: dict[str, str] = json.loads(headers_json) if headers_json else {}
        try:
            r = session.get(url, headers=headers_dict, timeout=30)
            return json.dumps(
                {
                    "statusCode": r.status_code,
                    "status": r.status_code,
                    "ok": 200 <= r.status_code < 300,
                    "body": r.text,
                    "headers": dict(r.headers),
                }
            )
        except Exception as e:
            logger.warning("http.get failed for %s: %s", url, e)
            return json.dumps({"statusCode": 0, "status": 0, "ok": False, "body": "", "headers": {}, "error": str(e)})

    def post(self, url: str, body: Any = None, headers_json: Any = None) -> str:
        logger.debug("post has been called with url=%s, body=%s, headers_json=%s", url, body, headers_json)
        headers_dict: dict[str, str] = json.loads(headers_json) if headers_json else {}
        try:
            kwargs = {}
            if body is not None:
                if isinstance(body, dict):
                    kwargs["data"] = body
                else:
                    kwargs["content"] = body
            r = session.post(url, headers=headers_dict, timeout=30, **kwargs)
            return json.dumps(
                {
                    "statusCode": r.status_code,
                    "status": r.status_code,
                    "ok": 200 <= r.status_code < 300,
                    "body": r.text,
                    "headers": dict(r.headers),
                }
            )
        except Exception as e:
            logger.warning("http.post failed for %s: %s", url, e)
            return json.dumps({"statusCode": 0, "status": 0, "ok": False, "body": "", "headers": {}, "error": str(e)})

    def clear_cookies(self) -> None:
        logger.debug("clear_cookies has been called")
        session.cookies.clear()


class FileMock:
    def __init__(self, ctx: JsContext) -> None:
        logger.debug("FileMock.__init__ has been called with ctx=%s", ctx)
        self.ctx = ctx

    def exists(self, path: str) -> bool:
        logger.debug("exists has been called with path=%s", path)
        return Path(path).exists()

    def get_size(self, path: str) -> str:
        logger.debug("get_size has been called with path=%s", path)
        try:
            p = Path(path)
            if p.exists():
                return json.dumps({"success": True, "size": p.stat().st_size})
            return json.dumps({"success": False, "error": "file not found"})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def delete(self, path: str) -> str:
        logger.debug("delete has been called with path=%s", path)
        try:
            p = Path(path)
            if p.exists():
                p.unlink()
            return json.dumps({"success": True})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def read_bytes(self, path: str, options_json: Any = None) -> str:
        logger.debug("read_bytes has been called with path=%s, options_json=%s", path, options_json)
        opts: dict[str, Any] = json.loads(options_json) if options_json else {}
        offset = opts.get("offset", 0)
        length = opts.get("length", -1)
        try:
            with Path(path).open("rb") as f:
                if offset > 0:
                    f.seek(offset)
                data = f.read(length) if length > 0 else f.read()
            eof = len(data) < length if length > 0 else True
            return json.dumps(
                {"success": True, "data": base64.b64encode(data).decode("utf-8"), "bytes_read": len(data), "eof": eof}
            )
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def write_bytes(self, path: str, data_b64: str, options_json: Any = None) -> str:
        logger.debug("write_bytes has been called with path=%s,  options_json=%s", path, options_json)
        opts: dict[str, Any] = json.loads(options_json) if options_json else {}
        mode = "ab" if opts.get("append") else "wb"
        try:
            with Path(path).open(mode) as f:
                f.write(base64.b64decode(data_b64))
            return json.dumps({"success": True, "path": str(Path(path).absolute())})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def download(self, url: str, output_path: str, options_json: Any = None, progress_id: str | None = None) -> str:
        logger.debug(
            "download has been called with url=%s, output_path=%s, options_json=%s, progress_id=%s",
            url,
            output_path,
            options_json,
            progress_id,
        )
        opts: dict[str, Any] = json.loads(options_json) if options_json else {}
        headers_dict: dict[str, str] = dict(opts.get("headers") or {})

        try:
            with session.stream("GET", url, headers=headers_dict, timeout=30) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                written = 0

                Path(output_path).parent.mkdir(parents=True, exist_ok=True)

                with Path(output_path).open("wb") as f:
                    for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            written += len(chunk)
                            if progress_id:
                                with contextlib.suppress(Exception):
                                    self.ctx.eval(f"__trigger_progress({json.dumps(progress_id)}, {written}, {total})")
            return json.dumps({"success": True})
        except Exception as e:
            logger.warning("file.download failed for %s: %s", url, e)
            return json.dumps({"success": False, "error": str(e)})


class GoBackendMock:
    def __init__(self, lyrics_getter: Callable[[str, str, str], str | None] | None = None):
        self.lyrics_getter = lyrics_getter

    def sanitize_filename(self, filename: str) -> str:
        logger.debug("sanitize_filename has been called with filename=%s", filename)
        return re.sub(r'[<>:"/\\|?*]', "_", filename.strip())

    def get_audio_quality(self, path: str) -> str:
        logger.debug("get_audio_quality has been called with path=%s", path)
        try:
            audio = mutagen.File(path)
            if audio is None:
                return json.dumps({"error": "could not parse audio file"})

            info = audio.info
            sample_rate = getattr(info, "sample_rate", 44100)
            bit_depth = getattr(info, "bits_per_sample", 16)
            total_samples = getattr(info, "total_samples", 0)
            if not total_samples:
                length = getattr(info, "length", 0.0)
                total_samples = int(length * sample_rate)

            return json.dumps({"bitDepth": bit_depth, "sampleRate": sample_rate, "totalSamples": total_samples})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def check_isrc_exists(self, output_dir: str, isrc: str) -> str:
        logger.debug("check_isrc_exists has been called with output_dir=%s, isrc=%s", output_dir, isrc)
        target_isrc = isrc.upper().strip()
        with contextlib.suppress(Exception):
            for p in Path(output_dir).glob("*"):
                if p.suffix.lower() in (".flac", ".m4a", ".mp3"):
                    with contextlib.suppress(Exception):
                        audio = mutagen.File(p)
                        if not audio:
                            continue
                        file_isrc = None
                        if p.suffix.lower() == ".flac":
                            val = audio.get("isrc") or audio.get("ISRC")
                            if val:
                                file_isrc = val[0]
                        elif p.suffix.lower() == ".mp3":
                            if "TSRC" in audio:
                                file_isrc = audio["TSRC"].text[0]
                        elif p.suffix.lower() in (".m4a", ".aac"):
                            isrc_key = "----:com.apple.iTunes:ISRC"
                            if isrc_key in audio:
                                file_isrc = audio[isrc_key][0].decode("utf-8")

                        if file_isrc and file_isrc.upper().strip() == target_isrc:
                            return json.dumps({"exists": True, "filePath": str(p)})
        return json.dumps({"exists": False})

    def get_local_time(self) -> str:
        logger.debug("get_local_time has been called")
        now = datetime.now().astimezone()
        offset = now.utcoffset()
        offset_min = -int(offset.total_seconds() / 60) if offset else 0
        return json.dumps(
            {
                "year": now.year,
                "month": now.month,
                "day": now.day,
                "hour": now.hour,
                "minute": now.minute,
                "second": now.second,
                "weekday": now.weekday(),
                "offsetMinutes": offset_min,
                "timezone": str(now.tzinfo) or "Local",
                "timestamp": int(now.timestamp()),
            }
        )

    def get_lyrics_lrc(self, spotify_id: str, title: str, artist: str, album: str, duration_ms: int) -> str:
        logger.debug(
            "get_lyrics_lrc has been called with spotify_id=%s, title=%s, artist=%s, album=%s, duration_ms=%s",
            spotify_id,
            title,
            artist,
            album,
            duration_ms,
        )
        if self.lyrics_getter:
            lyrics = self.lyrics_getter(spotify_id, title, artist)
            if lyrics:
                return json.dumps({"error": None, "lyrics": lyrics})
        return json.dumps({"error": "not implemented", "lyrics": ""})


class UtilsMock:
    def __init__(self, manifest: ProviderManifest):
        logger.debug("UtilsMock.__init__ has been called with manifest=%s", manifest)
        self._manifest = manifest

    def app_user_agent(self) -> str:
        logger.debug("app_user_agent has been called")
        return f"SpotiFLAC-Mobile/{self.app_version()}"

    def random_user_agent(self) -> str:
        logger.debug("random_user_agent has been called")
        ua_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:15.0) Gecko/20100101 Firefox/15.0.1",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/601.3.9 "
            "(KHTML, like Gecko) Version/9.0.2 Safari/601.3.9",
        ]
        return random.choice(ua_list)  # noqa

    def app_version(self) -> str:
        logger.debug("app_version has been called")
        return self._manifest.get("minAppVersion", "1.0.0")

    def base64_decode(self, val: str) -> str:
        logger.debug("base64_decode has been called with val=%s", val)
        return base64.b64decode(val).decode("utf-8")

    def base64_encode(self, val: str) -> str:
        logger.debug("base64_encode has been called with val=%s", val)
        return base64.b64encode(val.encode("utf-8")).decode("utf-8")

    def is_download_cancelled(self) -> bool:
        logger.debug("is_download_cancelled has been called")
        return False

    def hmac_sha1(self, key_json: str, data_json: str) -> str:
        logger.debug("hmac_sha1 has been called with key_json=%s, data_json=%s", key_json, data_json)
        try:
            key_val = json.loads(key_json)
            data_val = json.loads(data_json)

            def to_bytes(val: Any) -> bytes:
                if isinstance(val, str):
                    return val.encode("utf-8")
                return bytes([int(v) for v in val])

            key_bytes = to_bytes(key_val)
            msg_bytes = to_bytes(data_val)

            mac = hmac.new(key_bytes, msg_bytes, hashlib.sha1)
            result = mac.digest()
            return json.dumps([int(b) for b in result])
        except Exception as e:
            logger.warning("hmac_sha1 failed: %s", e)
            return "[]"

    def md5(self, val: str) -> str:
        logger.debug("md5 has been called with val=%s", val)
        return hashlib.md5(val.encode("utf-8")).hexdigest()

    def sha256(self, val: str) -> str:
        logger.debug("sha256 has been called with val=%s", val)
        return hashlib.sha256(val.encode("utf-8")).hexdigest()

    def hmac_sha256(self, message: str, key: str) -> str:
        logger.debug("hmac_sha256 has been called with message=%s, key=%s", message, key)
        mac = hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256)
        return mac.hexdigest()

    def hmac_sha256_base64(self, message: str, key: str) -> str:
        logger.debug("hmac_sha256_base64 has been called with message=%s, key=%s", message, key)
        mac = hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode("utf-8")

    def encrypt_block_cipher(self, data_b64: str, options_json: str) -> str:
        logger.debug("encrypt_block_cipher has been called with data_b64=%s, options_json=%s", data_b64, options_json)
        try:
            opts: dict[str, Any] = json.loads(options_json)
            algorithm = opts.get("algorithm", "").lower()
            mode_name = opts.get("mode", "").lower()
            key_str = opts.get("key", "")
            key_enc = opts.get("keyEncoding", "hex").lower()
            iv_str = opts.get("iv", "")
            iv_enc = opts.get("ivEncoding", "hex").lower()

            if key_enc == "hex":
                key_bytes = bytes.fromhex(key_str)
            elif key_enc == "base64":
                key_bytes = base64.b64decode(key_str)
            else:
                key_bytes = key_str.encode("utf-8")

            if iv_enc == "hex":
                iv_bytes = bytes.fromhex(iv_str)
            elif iv_enc == "base64":
                iv_bytes = base64.b64decode(iv_str)
            else:
                iv_bytes = iv_str.encode("utf-8")

            plain_data = base64.b64decode(data_b64)

            if algorithm == "blowfish":
                algo = algorithms.Blowfish(key_bytes)
            elif algorithm == "aes":
                algo = algorithms.AES(key_bytes)
            else:
                raise ValueError(f"unsupported algorithm: {algorithm}")

            if mode_name == "cbc":
                mode = modes.CBC(iv_bytes)
            elif mode_name == "ecb":
                mode = modes.ECB()
            else:
                raise ValueError(f"unsupported mode: {mode_name}")

            cipher = Cipher(algo, mode, backend=default_backend())
            encryptor = cipher.encryptor()
            encrypted_data = encryptor.update(plain_data) + encryptor.finalize()

            return json.dumps({"success": True, "data": base64.b64encode(encrypted_data).decode("utf-8")})
        except Exception as e:
            logger.warning("encryptBlockCipher failed: %s", e)
            return json.dumps({"success": False, "error": str(e)})

    def decrypt_block_cipher(self, data_b64: str, options_json: str) -> str:
        logger.debug("decrypt_block_cipher has been called with data_b64=%s, options_json=%s", data_b64, options_json)
        try:
            opts: dict[str, Any] = json.loads(options_json)
            algorithm = opts.get("algorithm", "").lower()
            mode_name = opts.get("mode", "").lower()
            key_str = opts.get("key", "")
            key_enc = opts.get("keyEncoding", "hex").lower()
            iv_str = opts.get("iv", "")
            iv_enc = opts.get("ivEncoding", "hex").lower()

            if key_enc == "hex":
                key_bytes = bytes.fromhex(key_str)
            elif key_enc == "base64":
                key_bytes = base64.b64decode(key_str)
            else:
                key_bytes = key_str.encode("utf-8")

            if iv_enc == "hex":
                iv_bytes = bytes.fromhex(iv_str)
            elif iv_enc == "base64":
                iv_bytes = base64.b64decode(iv_str)
            else:
                iv_bytes = iv_str.encode("utf-8")

            encrypted_data = base64.b64decode(data_b64)

            if algorithm == "blowfish":
                algo = algorithms.Blowfish(key_bytes)
            elif algorithm == "aes":
                algo = algorithms.AES(key_bytes)
            else:
                raise ValueError(f"unsupported algorithm: {algorithm}")

            if mode_name == "cbc":
                mode = modes.CBC(iv_bytes)
            elif mode_name == "ecb":
                mode = modes.ECB()
            else:
                raise ValueError(f"unsupported mode: {mode_name}")

            cipher = Cipher(algo, mode, backend=default_backend())
            decryptor = cipher.decryptor()
            decrypted_data = decryptor.update(encrypted_data) + decryptor.finalize()

            return json.dumps({"success": True, "data": base64.b64encode(decrypted_data).decode("utf-8")})
        except Exception as e:
            logger.warning("decryptBlockCipher failed: %s", e)
            return json.dumps({"success": False, "error": str(e)})

    def sleep(self, ms: int) -> bool:
        logger.debug("sleep has been called with ms=%s", ms)
        time.sleep(ms / 1000.0)
        return True


class StorageMock:
    def __init__(self, data_dir: Path) -> None:
        logger.debug("StorageMock.__init__ has been called with data_dir=%s", data_dir)
        self.file_path = data_dir / "storage.json"
        self.data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.file_path.exists():
            try:
                with self.file_path.open("r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}

    def _save(self) -> None:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w", encoding="utf-8") as f:
                json.dump(self.data, f)
        except Exception:
            logger.exception("failed to save storage data")

    def get(self, key: str) -> str:
        logger.debug("StorageMock.get has been called with key=%s", key)
        val = self.data.get(key)
        return json.dumps(val)

    def set(self, key: str, value_json: str) -> None:
        logger.debug("set has been called with key=%s, value_json=%s", key, value_json)
        try:
            self.data[key] = json.loads(value_json)
            self._save()
        except Exception:
            logger.exception("failed to set storage key: %s", key)

    def remove(self, key: str) -> None:
        logger.debug("StorageMock.remove has been called with key=%s", key)
        if key in self.data:
            del self.data[key]
            self._save()


class CredentialsMock:
    def __init__(self, data_dir: Path) -> None:
        logger.debug("CredentialsMock.__init__ has been called with data_dir=%s", data_dir)
        self.file_path = data_dir / "credentials.json"
        self.data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.file_path.exists():
            try:
                with self.file_path.open("r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}

    def _save(self) -> None:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w", encoding="utf-8") as f:
                json.dump(self.data, f)
        except Exception:
            logger.exception("failed to save credentials data")

    def store(self, key: str, value_json: str) -> None:
        logger.debug("store has been called with key=%s, value_json=%s", key, value_json)
        try:
            self.data[key] = json.loads(value_json)
            self._save()
        except Exception:
            logger.exception("failed to store credentials key: %s", key)

    def get(self, key: str) -> str:
        logger.debug("CredentialsMock.get has been called with key=%s", key)
        val = self.data.get(key)
        return json.dumps(val)

    def has(self, key: str) -> bool:
        logger.debug("has has been called with key=%s", key)
        return key in self.data

    def remove(self, key: str) -> None:
        logger.debug("CredentialsMock.remove has been called with key=%s", key)
        if key in self.data:
            del self.data[key]
            self._save()


class AuthMock:
    def __init__(self, data_dir: Path) -> None:
        logger.debug("AuthMock.__init__ has been called with data_dir=%s", data_dir)
        self.file_path = data_dir / "auth.json"
        self.data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.file_path.exists():
            try:
                with self.file_path.open("r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}

    def _save(self) -> None:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w", encoding="utf-8") as f:
                json.dump(self.data, f)
        except Exception:
            logger.exception("failed to save auth data")

    def open_auth_url(self, auth_url: str, callback_url: str) -> None:
        logger.debug("auth.openAuthUrl called with url: %s, callback: %s", auth_url, callback_url)

    def get_auth_code(self) -> str:
        logger.debug("get_auth_code has been called")
        return self.data.get("code") or ""

    def set_auth_code(self, tokens_json: str) -> None:
        logger.debug("set_auth_code has been called with tokens_json=%s", tokens_json)
        try:
            tokens = json.loads(tokens_json)
            self.data.update(tokens)
            self._save()
        except Exception:
            logger.exception("failed to set auth code")

    def is_authenticated(self) -> bool:
        logger.debug("is_authenticated has been called")
        return self.data.get("is_authenticated") or bool(self.data.get("access_token"))

    def get_tokens(self) -> str:
        logger.debug("get_tokens has been called")
        tokens = {
            "access_token": self.data.get("access_token") or "",
            "refresh_token": self.data.get("refresh_token") or "",
            "is_authenticated": self.is_authenticated(),
            "expires_at": self.data.get("expires_at") or 0,
            "is_expired": self.data.get("is_expired") or False,
        }
        return json.dumps(tokens)

    def clear_auth(self) -> None:
        logger.debug("clear_auth has been called")
        self.data = {}
        self._save()


class MatchingMock:
    def compare_strings(self, a: str, b: str) -> float:
        logger.debug("compare_strings has been called with a=%s, b=%s", a, b)
        a_norm = self.normalize_string(a)
        b_norm = self.normalize_string(b)
        if a_norm == b_norm:
            return 1.0
        if a_norm in b_norm or b_norm in a_norm:
            return 0.85
        words_a = set(a_norm.split())
        words_b = set(b_norm.split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a.intersection(words_b)
        return len(intersection) / max(len(words_a), len(words_b))

    def compare_duration(self, a: float, b: float, tolerance: float) -> bool:
        logger.debug("compare_duration has been called with a=%s, b=%s, tolerance=%s", a, b, tolerance)
        return abs(a - b) <= tolerance

    def normalize_string(self, s: str) -> str:
        logger.debug("normalize_string has been called with s=%s", s)
        s = s.lower().strip()
        s = re.sub(r"\([^)]*\)", "", s)
        s = re.sub(r"\[[^\]]*\]", "", s)
        s = re.sub(r"[^\w\s]", "", s)
        return " ".join(s.split())


class LogMock:
    def info(self, msg: Any) -> None:
        logger.info(str(msg))

    def debug(self, msg: Any) -> None:
        logger.debug(str(msg))

    def error(self, msg: Any) -> None:
        logger.error(str(msg))

    def warn(self, msg: Any) -> None:
        logger.warning(str(msg))


def register_mocks_in_context(
    ctx: JsContext,
    data_dir: Path,
    manifest: ProviderManifest,
    lyrics_getter: Callable[[str, str, str], str | None] | None = None,
) -> None:
    url_mock = UrlMock()
    http_mock = HttpMock()
    file_mock = FileMock(ctx)
    backend_mock = GoBackendMock(lyrics_getter)
    utils_mock = UtilsMock(manifest)
    storage_mock = StorageMock(data_dir)
    credentials_mock = CredentialsMock(data_dir)
    auth_mock = AuthMock(data_dir)
    matching_mock = MatchingMock()
    log_mock = LogMock()

    ctx.add_callable("__url_parse", url_mock.parse_url)
    ctx.add_callable("__url_parseSearchParams", url_mock.parse_search_params)

    ctx.add_callable("__http_get", http_mock.get)
    ctx.add_callable("__http_post", http_mock.post)
    ctx.add_callable("__http_clearCookies", http_mock.clear_cookies)

    ctx.add_callable("__file_exists", file_mock.exists)
    ctx.add_callable("__file_getSize", file_mock.get_size)
    ctx.add_callable("__file_delete", file_mock.delete)
    ctx.add_callable("__file_readBytes", file_mock.read_bytes)
    ctx.add_callable("__file_writeBytes", file_mock.write_bytes)
    ctx.add_callable("__file_download", file_mock.download)

    ctx.add_callable("__gobackend_sanitizeFilename", backend_mock.sanitize_filename)
    ctx.add_callable("__gobackend_getAudioQuality", backend_mock.get_audio_quality)
    ctx.add_callable("__gobackend_checkISRCExists", backend_mock.check_isrc_exists)
    ctx.add_callable("__gobackend_getLocalTime", backend_mock.get_local_time)
    ctx.add_callable("__gobackend_getLyricsLRC", backend_mock.get_lyrics_lrc)

    ctx.add_callable("__utils_appUserAgent", utils_mock.app_user_agent)
    ctx.add_callable("__utils_randomUserAgent", utils_mock.random_user_agent)
    ctx.add_callable("__utils_appVersion", utils_mock.app_version)
    ctx.add_callable("__utils_base64Decode", utils_mock.base64_decode)
    ctx.add_callable("__utils_base64Encode", utils_mock.base64_encode)
    ctx.add_callable("__utils_isDownloadCancelled", utils_mock.is_download_cancelled)
    ctx.add_callable("__utils_hmacSHA1", utils_mock.hmac_sha1)
    ctx.add_callable("__utils_md5", utils_mock.md5)
    ctx.add_callable("__utils_sha256", utils_mock.sha256)
    ctx.add_callable("__utils_hmacSHA256", utils_mock.hmac_sha256)
    ctx.add_callable("__utils_hmacSHA256Base64", utils_mock.hmac_sha256_base64)
    ctx.add_callable("__utils_encryptBlockCipher", utils_mock.encrypt_block_cipher)
    ctx.add_callable("__utils_decryptBlockCipher", utils_mock.decrypt_block_cipher)
    ctx.add_callable("__utils_sleep", utils_mock.sleep)

    ctx.add_callable("__storage_get", storage_mock.get)
    ctx.add_callable("__storage_set", storage_mock.set)
    ctx.add_callable("__storage_remove", storage_mock.remove)

    ctx.add_callable("__credentials_store", credentials_mock.store)
    ctx.add_callable("__credentials_get", credentials_mock.get)
    ctx.add_callable("__credentials_has", credentials_mock.has)
    ctx.add_callable("__credentials_remove", credentials_mock.remove)

    ctx.add_callable("__auth_openAuthUrl", auth_mock.open_auth_url)
    ctx.add_callable("__auth_getAuthCode", auth_mock.get_auth_code)
    ctx.add_callable("__auth_setAuthCode", auth_mock.set_auth_code)
    ctx.add_callable("__auth_isAuthenticated", auth_mock.is_authenticated)
    ctx.add_callable("__auth_getTokens", auth_mock.get_tokens)
    ctx.add_callable("__auth_clearAuth", auth_mock.clear_auth)

    ctx.add_callable("__matching_compareStrings", matching_mock.compare_strings)
    ctx.add_callable("__matching_compareDuration", matching_mock.compare_duration)
    ctx.add_callable("__matching_normalizeString", matching_mock.normalize_string)

    ctx.add_callable("__log_info", log_mock.info)
    ctx.add_callable("__log_debug", log_mock.debug)
    ctx.add_callable("__log_error", log_mock.error)
    ctx.add_callable("__log_warn", log_mock.warn)

    with (Path(__file__).parent / "mocks.js").open(mode="r", encoding="utf-8") as f:
        mocks_js = f.read()
        ctx.eval(mocks_js)


def setup_test():
    from typing import cast  # noqa

    import quickjs  # noqa

    ctx = cast("JsContext", quickjs.Context())

    url_mock = UrlMock()
    http_mock = HttpMock()
    file_mock = FileMock(ctx)
    backend_mock = GoBackendMock()

    ctx.add_callable("__url_parse", url_mock.parse_url)
    ctx.add_callable("__url_parseSearchParams", url_mock.parse_search_params)

    ctx.add_callable("__http_get", http_mock.get)
    ctx.add_callable("__http_post", http_mock.post)
    ctx.add_callable("__http_clearCookies", http_mock.clear_cookies)

    ctx.add_callable("__file_exists", file_mock.exists)
    ctx.add_callable("__file_getSize", file_mock.get_size)
    ctx.add_callable("__file_delete", file_mock.delete)
    ctx.add_callable("__file_readBytes", file_mock.read_bytes)
    ctx.add_callable("__file_writeBytes", file_mock.write_bytes)
    ctx.add_callable("__file_download", file_mock.download)

    ctx.add_callable("__gobackend_sanitizeFilename", backend_mock.sanitize_filename)
    ctx.add_callable("__gobackend_getAudioQuality", backend_mock.get_audio_quality)
    ctx.add_callable("__gobackend_checkISRCExists", backend_mock.check_isrc_exists)
    ctx.add_callable("__gobackend_getLocalTime", backend_mock.get_local_time)
    ctx.add_callable("__gobackend_getLyricsLRC", backend_mock.get_lyrics_lrc)

    with Path(r"nameless\command\music_downloader\downloader\utils\mocks.js").open(mode="r", encoding="utf-8") as f:
        mocks_js = f.read()
        ctx.eval(mocks_js)

    return ctx
