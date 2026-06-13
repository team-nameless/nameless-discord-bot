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

import mutagen
import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

if TYPE_CHECKING:
    from .._quickjs_types import Context as JsContext
    from ..providers._manifest import ProviderManifest


logger = logging.getLogger("JsMocks")

session = requests.Session()
session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        )
    }
)


class HttpMock:
    def get(self, url: str, headers_json: Any = None) -> str:
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
        headers_dict: dict[str, str] = json.loads(headers_json) if headers_json else {}
        try:
            r = session.post(url, data=body, headers=headers_dict, timeout=30)
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
        session.cookies.clear()


class FileMock:
    def __init__(self, ctx: JsContext) -> None:
        self.ctx = ctx

    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def get_size(self, path: str) -> str:
        try:
            p = Path(path)
            if p.exists():
                return json.dumps({"success": True, "size": p.stat().st_size})
            return json.dumps({"success": False, "error": "file not found"})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def delete(self, path: str) -> str:
        try:
            p = Path(path)
            if p.exists():
                p.unlink()
            return json.dumps({"success": True})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def read_bytes(self, path: str, options_json: Any = None) -> str:
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
        opts: dict[str, Any] = json.loads(options_json) if options_json else {}
        mode = "ab" if opts.get("append") else "wb"
        try:
            with Path(path).open(mode) as f:
                f.write(base64.b64decode(data_b64))
            return json.dumps({"success": True, "path": str(Path(path).absolute())})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def download(self, url: str, output_path: str, options_json: Any = None, progress_id: str | None = None) -> str:
        opts: dict[str, Any] = json.loads(options_json) if options_json else {}
        headers_dict: dict[str, str] = dict(opts.get("headers") or {})

        try:
            r = session.get(url, headers=headers_dict, stream=True, timeout=30)
            r.raise_for_status()

            total = int(r.headers.get("content-length", 0))
            written = 0

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            with Path(output_path).open("wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
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
    def sanitize_filename(self, filename: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', "_", filename.strip())

    def get_audio_quality(self, path: str) -> str:
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
        # FIXME: implement this
        return json.dumps({"error": "not implemented", "lyrics": ""})


class UtilsMock:
    def __init__(self, manifest: ProviderManifest):
        self._manifest = manifest

    def app_user_agent(self) -> str:
        return f"SpotiFLAC-Mobile/{self.app_version()}"

    def random_user_agent(self) -> str:
        ua_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:15.0) Gecko/20100101 Firefox/15.0.1",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/601.3.9 "
            "(KHTML, like Gecko) Version/9.0.2 Safari/601.3.9",
        ]
        return random.choice(ua_list)  # noqa

    def app_version(self) -> str:
        return self._manifest.get("minAppVersion", "1.0.0")

    def base64_decode(self, val: str) -> str:
        return base64.b64decode(val).decode("utf-8")

    def base64_encode(self, val: str) -> str:
        return base64.b64encode(val.encode("utf-8")).decode("utf-8")

    def is_download_cancelled(self) -> bool:
        return False

    def hmac_sha1(self, key_json: str, data_json: str) -> str:
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
        return hashlib.md5(val.encode("utf-8")).hexdigest()

    def sha256(self, val: str) -> str:
        return hashlib.sha256(val.encode("utf-8")).hexdigest()

    def hmac_sha256(self, message: str, key: str) -> str:
        mac = hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256)
        return mac.hexdigest()

    def hmac_sha256_base64(self, message: str, key: str) -> str:
        mac = hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode("utf-8")

    def encrypt_block_cipher(self, data_b64: str, options_json: str) -> str:
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
        time.sleep(ms / 1000.0)
        return True


class StorageMock:
    def __init__(self, data_dir: Path) -> None:
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
        val = self.data.get(key)
        return json.dumps(val)

    def set(self, key: str, value_json: str) -> None:
        try:
            self.data[key] = json.loads(value_json)
            self._save()
        except Exception:
            logger.exception("failed to set storage key: %s", key)

    def remove(self, key: str) -> None:
        if key in self.data:
            del self.data[key]
            self._save()


class CredentialsMock:
    def __init__(self, data_dir: Path) -> None:
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
        try:
            self.data[key] = json.loads(value_json)
            self._save()
        except Exception:
            logger.exception("failed to store credentials key: %s", key)

    def get(self, key: str) -> str:
        val = self.data.get(key)
        return json.dumps(val)

    def has(self, key: str) -> bool:
        return key in self.data

    def remove(self, key: str) -> None:
        if key in self.data:
            del self.data[key]
            self._save()


class AuthMock:
    def __init__(self, data_dir: Path) -> None:
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
        logger.info("auth.openAuthUrl called with url: %s, callback: %s", auth_url, callback_url)

    def get_auth_code(self) -> str:
        return self.data.get("code") or ""

    def set_auth_code(self, tokens_json: str) -> None:
        try:
            tokens = json.loads(tokens_json)
            self.data.update(tokens)
            self._save()
        except Exception:
            logger.exception("failed to set auth code")

    def is_authenticated(self) -> bool:
        return self.data.get("is_authenticated") or bool(self.data.get("access_token"))

    def get_tokens(self) -> str:
        tokens = {
            "access_token": self.data.get("access_token") or "",
            "refresh_token": self.data.get("refresh_token") or "",
            "is_authenticated": self.is_authenticated(),
            "expires_at": self.data.get("expires_at") or 0,
            "is_expired": self.data.get("is_expired") or False,
        }
        return json.dumps(tokens)

    def clear_auth(self) -> None:
        self.data = {}
        self._save()


class MatchingMock:
    def compare_strings(self, a: str, b: str) -> float:
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
        return abs(a - b) <= tolerance

    def normalize_string(self, s: str) -> str:
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


def register_mocks_in_context(ctx: JsContext, data_dir: Path, manifest: ProviderManifest) -> None:
    http_mock = HttpMock()
    file_mock = FileMock(ctx)
    backend_mock = GoBackendMock()
    utils_mock = UtilsMock(manifest)
    storage_mock = StorageMock(data_dir)
    credentials_mock = CredentialsMock(data_dir)
    auth_mock = AuthMock(data_dir)
    matching_mock = MatchingMock()
    log_mock = LogMock()

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

    ctx.eval("""
    var global = this;
    var window = this;

    var http = {
        get: function(url, headers) {
            var res = __http_get(url, headers ? JSON.stringify(headers) : null);
            return JSON.parse(res);
        },
        post: function(url, body, headers) {
            var res = __http_post(url, body, headers ? JSON.stringify(headers) : null);
            return JSON.parse(res);
        },
        clearCookies: __http_clearCookies
    };

    var file = {
        exists: __file_exists,
        getSize: function(path) {
            var res = __file_getSize(path);
            return JSON.parse(res);
        },
        delete: function(path) {
            var res = __file_delete(path);
            return JSON.parse(res);
        },
        readBytes: function(path, options) {
            var res = __file_readBytes(path, options ? JSON.stringify(options) : null);
            return JSON.parse(res);
        },
        writeBytes: function(path, data, options) {
            var res = __file_writeBytes(path, data, options ? JSON.stringify(options) : null);
            return JSON.parse(res);
        },
        download: function(url, outputPath, options) {
            options = options || {};
            var hasProgress = typeof options.onProgress === 'function';
            if (!hasProgress && typeof global.__active_download_progress === 'function') {
                options.onProgress = global.__active_download_progress;
                hasProgress = true;
            }
            var progressId = null;
            if (hasProgress) {
                progressId = "dl_" + Math.random().toString(36).substring(2);
                __progress_callbacks[progressId] = options.onProgress;
            }

            var cleanOpts = {};
            if (options.headers) cleanOpts.headers = options.headers;

            var res = __file_download(url, outputPath, JSON.stringify(cleanOpts), progressId);
            if (progressId) {
                delete __progress_callbacks[progressId];
            }
            return JSON.parse(res);
        }
    };

    var gobackend = {
        sanitizeFilename: __gobackend_sanitizeFilename,
        getAudioQuality: function(path) {
            var res = __gobackend_getAudioQuality(path);
            return JSON.parse(res);
        },
        checkISRCExists: function(outputDir, isrc) {
            var res = __gobackend_checkISRCExists(outputDir, isrc);
            return JSON.parse(res);
        },
        getLocalTime: function() {
            var res = __gobackend_getLocalTime();
            return JSON.parse(res);
        },
        getLyricsLRC: function(spotifyId, title, artist, album, durationMs) {
            var res = __gobackend_getLyricsLRC(
                spotifyId || "",
                title || "",
                artist || "",
                album || "",
                Number(durationMs || 0)
            );
            return JSON.parse(res);
        }
    };

    var utils = {
        appUserAgent: __utils_appUserAgent,
        randomUserAgent: __utils_randomUserAgent,
        appVersion: __utils_appVersion,
        base64Decode: __utils_base64Decode,
        base64Encode: __utils_base64Encode,
        isDownloadCancelled: __utils_isDownloadCancelled,
        hmacSHA1: function(key, data) {
            var res = __utils_hmacSHA1(JSON.stringify(key), JSON.stringify(data));
            return JSON.parse(res);
        },
        parseJSON: function(s) {
            return JSON.parse(s);
        },
        stringifyJSON: function(obj) {
            return JSON.stringify(obj);
        },
        md5: __utils_md5,
        sha256: __utils_sha256,
        hmacSHA256: __utils_hmacSHA256,
        hmacSHA256Base64: __utils_hmacSHA256Base64,
        encryptBlockCipher: function(data, options) {
            var res = __utils_encryptBlockCipher(data, JSON.stringify(options));
            return JSON.parse(res);
        },
        decryptBlockCipher: function(data, options) {
            var res = __utils_decryptBlockCipher(data, JSON.stringify(options));
            return JSON.parse(res);
        },
        sleep: __utils_sleep
    };

    var storage = {
        get: function(key) {
            var res = __storage_get(key);
            return JSON.parse(res);
        },
        set: function(key, value) {
            __storage_set(key, JSON.stringify(value));
        },
        remove: __storage_remove
    };

    var credentials = {
        store: function(key, value) {
            __credentials_store(key, JSON.stringify(value));
        },
        get: function(key) {
            var res = __credentials_get(key);
            return JSON.parse(res);
        },
        has: __credentials_has,
        remove: __credentials_remove
    };

    var auth = {
        openAuthUrl: __auth_openAuthUrl,
        getAuthCode: __auth_getAuthCode,
        setAuthCode: function(tokens) {
            __auth_setAuthCode(JSON.stringify(tokens));
        },
        isAuthenticated: __auth_isAuthenticated,
        getTokens: function() {
            var res = __auth_getTokens();
            return JSON.parse(res);
        },
        clearAuth: __auth_clearAuth
    };

    var matching = {
        compareStrings: __matching_compareStrings,
        compareDuration: __matching_compareDuration,
        normalizeString: __matching_normalizeString
    };

    var log = {
        info: function() { __log_info(Array.prototype.join.call(arguments, ' ')); },
        debug: function() { __log_debug(Array.prototype.join.call(arguments, ' ')); },
        error: function() { __log_error(Array.prototype.join.call(arguments, ' ')); },
        warn: function() { __log_warn(Array.prototype.join.call(arguments, ' ')); }
    };
    var console = log;

    var __progress_callbacks = {};
    function __trigger_progress(progressId, written, total) {
        var cb = __progress_callbacks[progressId];
        if (cb) {
            try {
                cb(written, total);
            } catch(e) {}
        }
    }

    // does quickjs support fetch natively?
    function fetch(url, options) {
        options = options || {};
        var method = (options.method || 'GET').toUpperCase();
        var headers = options.headers || {};
        var body = options.body || null;

        var response;
        if (method === 'GET' || method === 'HEAD') {
            response = http.get(url, headers);
        } else if (method === 'POST') {
            response = http.post(url, body, headers);
        } else {
            throw new Error('Unsupported HTTP method: ' + method);
        }

        var responseObj = {
            ok: response.ok || false,
            status: response.status || response.statusCode || 0,
            statusText: response.status >= 200 && response.status < 300 ? 'OK' : 'ERROR',
            headers: response.headers || {},
            body: response.body || '',
            text: function() {
                return this.body;
            },
            json: function() {
                try {
                    return JSON.parse(this.body);
                } catch(e) {
                    throw new Error('Invalid JSON response');
                }
            },
            arrayBuffer: function() {
                return this.body;
            },
            blob: function() {
                return this.body;
            }
        };

        return responseObj;
    }
    """)
