from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, cast

import quickjs

from nameless.command.music_downloader.downloader.utils.extension_manager import check_and_update_extension
from nameless.command.music_downloader.downloader.utils.js_mocks import register_mocks_in_context
from nameless.command.music_downloader.lyrics import get_lyrics

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from .._quickjs_types import Context as JsContext
    from ._manifest import ProviderManifest


class BaseProvider:
    name: str = "base"
    extension_id: str = "base"

    def __init__(self, **kwargs: Any) -> None:
        self._script_path: Path | None = None
        self._ctx: JsContext | None = None
        self._manifest_data: ProviderManifest | None = None
        self._progress_cb: Callable[[int, int], None] | None = None
        self._logger = logging.getLogger(f"downloader:{self.name}")

        self._load_extension(options=kwargs)

        settings = self.manifest.get("settings", {})
        real_kwargs = {}
        for setting in settings:
            key = setting.get("key")
            _type = setting.get("type", "string")
            default = setting.get("default")
            if key and key in kwargs:
                value = kwargs[key]
                if _type == "number":
                    value = int(value)
                real_kwargs[key] = value
            else:
                real_kwargs[key] = default

    def set_progress_callback(self, cb: Callable[[int, int], None]) -> None:
        self._progress_cb = cb

    @property
    def manifest(self) -> ProviderManifest:
        if self._manifest_data is not None:
            return self._manifest_data

        if not self._script_path:
            raise RuntimeError("provider script path not set")

        manifest_path = self._script_path.parent / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError(f"manifest file not found for provider {self.name}")

        with manifest_path.open(encoding="utf-8") as f:
            self._manifest_data = json.load(f)
        if not isinstance(self._manifest_data, dict):
            raise RuntimeError(f"invalid manifest format for provider {self.name}")
        return self._manifest_data

    @manifest.setter
    def manifest(self, value: ProviderManifest) -> None:
        self._manifest_data = value

    def _load_extension(self, options: dict[str, Any]) -> None:
        try:
            self._script_path = check_and_update_extension(self.extension_id)

            self._ctx = cast("JsContext", quickjs.Context())
            self._ctx.eval("var registeredExtension = null;")
            self._ctx.eval("function registerExtension(ext) { registeredExtension = ext; }")

            register_mocks_in_context(self._ctx, self._script_path.parent, self.manifest, get_lyrics)

            with self._script_path.open(encoding="utf-8") as f:
                js_code = f.read()
            self._ctx.eval(js_code)

            if not self._ctx.eval("registeredExtension !== null"):
                raise RuntimeError(f"extension {self.extension_id} did not register correctly")

            default_settings = {}
            for setting in self.manifest.get("settings", []):
                if "key" in setting and "default" in setting:
                    default_settings[setting["key"]] = setting["default"]
            default_settings.update(options)

            init_js = f"registeredExtension.initialize({json.dumps(default_settings)});"
            self._ctx.eval(init_js)
            self._logger.info("loaded and initialized JS provider %s successfully", self.name)
        except Exception as e:
            self._logger.error("failed to load JS provider %s: %s", self.name, e)
            raise

    def resolve_url(self, url: str) -> dict[str, Any]:
        if not self._ctx:
            raise RuntimeError("provider not initialized")
        js_cmd = f"""
        (function() {{
            var fn = registeredExtension.handleUrl || registeredExtension.handleURL;
            if (typeof fn === 'function') {{
                return JSON.stringify(fn({json.dumps(url)}));
            }}
            return JSON.stringify({{success: false, error: "handleUrl not implemented"}});
        }})()
        """
        res_str = self._ctx.eval(js_cmd)
        return json.loads(res_str)

    def search_tracks(self, query: str, limit: int = 20) -> list[Any]:
        if not self._ctx:
            raise RuntimeError("provider not initialized")

        search_opts = {"limit": limit, "filter": "track"}
        search_js = f"""
        (function() {{
            if (typeof registeredExtension.customSearch === 'function') {{
                return JSON.stringify(registeredExtension.customSearch({json.dumps(query)}, {json.dumps(search_opts)}));
            }} else if (typeof registeredExtension.searchTracks === 'function') {{
                return JSON.stringify(registeredExtension.searchTracks({json.dumps(query)}, {limit}));
            }}
            return JSON.stringify([]);
        }})()
        """
        res_str = self._ctx.eval(search_js)
        return json.loads(res_str)

    def check_availability(
        self,
        isrc: str,
        title: str,
        artists: str,
        options: dict[str, Any] | None = None,
    ) -> str | None:
        if not self._ctx:
            raise RuntimeError("provider not initialized")
        has_check = self._ctx.eval("typeof registeredExtension.checkAvailability === 'function'")
        if not has_check:
            return None

        args_str = f"{json.dumps(isrc or '')}, {json.dumps(title)}, {json.dumps(artists)}"
        if options is not None:
            args_str += f", {json.dumps(options)}"

        res_str = self._ctx.eval(f"JSON.stringify(registeredExtension.checkAvailability({args_str}))")
        res = json.loads(res_str)
        self._logger.info("checkAvailability result for %s - %s (ISRC: %s): %s", artists, title, isrc, res)
        if res and res.get("available"):
            return res.get("track_id")

        return None

    def enrich_track(self, track: Mapping[str, Any]) -> Mapping[str, Any]:
        if not self._ctx:
            raise RuntimeError("provider not initialized")

        has_enrich = self._ctx.eval("typeof registeredExtension.enrichTrack === 'function'")
        if not has_enrich:
            return track

        res_str = self._ctx.eval(f"JSON.stringify(registeredExtension.enrichTrack({json.dumps(track)}))")
        return json.loads(res_str)

    def download_track(self, track_id: str, quality: str, output_path: str) -> dict[str, Any]:
        if not self._ctx:
            raise RuntimeError("provider not initialized")

        def trigger_py_progress(written: Any, total: Any = None) -> None:
            if self._progress_cb:
                try:
                    if total is None:
                        w = int(float(written)) if written is not None else 0
                        t = 100
                    else:
                        w_bytes = int(float(written)) if written is not None else 0
                        t_bytes = int(float(total)) if total is not None else 0
                        pct = (w_bytes / t_bytes) * 100 if t_bytes > 0 else 0.0
                        w = int(pct * 0.35) if self.name == "deezer" else int(pct)
                        t = 100
                    self._progress_cb(w, t)
                except Exception as e:
                    self._logger.debug("error in trigger_py_progress: %s", e)

        self._ctx.add_callable("__trigger_py_progress", trigger_py_progress)

        # strip prefixes
        clean_track_id = str(track_id)
        for prefix in [f"{self.name}:", f"{self.extension_id}:"]:
            if clean_track_id.startswith(prefix):
                clean_track_id = clean_track_id.removeprefix(prefix)

        download_js = f"""
        (function() {{
            var progressCallback = function(written, total) {{
                __trigger_py_progress(written, total);
            }};
            global.__active_download_progress = progressCallback;
            try {{
                var res = registeredExtension.download(
                    {json.dumps(clean_track_id)},
                    {json.dumps(quality)},
                    {json.dumps(output_path)},
                    progressCallback
                );
                return JSON.stringify(res);
            }} finally {{
                delete global.__active_download_progress;
            }}
        }})()
        """

        res_str = self._ctx.eval(download_js)
        res = json.loads(res_str)
        return res
