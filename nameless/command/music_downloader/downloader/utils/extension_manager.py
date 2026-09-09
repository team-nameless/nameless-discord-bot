from __future__ import annotations

import io
import json
import logging
import zipfile
from pathlib import Path

import httpx

logger = logging.getLogger("ExtensionManager")

REGISTRY_URL = "https://raw.githubusercontent.com/zarzet/SpotiFLAC-Extension/main/registry.json"


def get_cache_assets_dir() -> Path:
    # update this when changing project structure
    root = Path(__file__).resolve().parents[5]
    assets_dir = root / ".cache" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    return assets_dir


def check_and_update_extension(extension_name: str) -> Path:
    assets_root = get_cache_assets_dir()
    assets_dir = assets_root / extension_name
    assets_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = assets_dir / "manifest.json"
    script_path = assets_dir / "index.js"

    current_version = None
    if manifest_path.exists():
        try:
            with manifest_path.open(encoding="utf-8") as f:
                manifest_data = json.load(f)
                current_version = manifest_data.get("version")
        except Exception as e:
            logger.warning("failed to read local manifest for %s: %s", extension_name, e)

    try:
        with httpx.Client(http2=True) as client:
            r = client.get(REGISTRY_URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=15)
            r.raise_for_status()
            registry_data = r.json()
    except Exception as e:
        logger.warning("failed to fetch extension registry: %s", e)
        if script_path.exists():
            return script_path
        raise RuntimeError(f"failed to fetch registry and no local extension found: {e}") from e

    ext_info = None
    for ext in registry_data.get("extensions", []):
        if ext.get("id") == extension_name:
            ext_info = ext
            break

    if not ext_info:
        if script_path.exists():
            return script_path
        raise ValueError(f"extension '{extension_name}' not found in registry")

    remote_version = ext_info.get("version")
    download_url = ext_info.get("download_url")

    if not current_version or current_version != remote_version or not script_path.exists():
        logger.info("updating extension %s: %s -> %s", extension_name, current_version, remote_version)
        try:
            with httpx.Client(http2=True) as client:
                r = client.get(
                    download_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=30
                )
                r.raise_for_status()
                zip_data = r.content

            with zipfile.ZipFile(io.BytesIO(zip_data)) as zip_ref:
                zip_ref.extractall(assets_dir)

            logger.info("successfully updated extension %s to version %s", extension_name, remote_version)
        except Exception as e:
            logger.error("failed to download or extract extension: %s", e)
            if script_path.exists():
                return script_path
            raise RuntimeError(f"failed to update extension: {e}") from e

    return script_path
