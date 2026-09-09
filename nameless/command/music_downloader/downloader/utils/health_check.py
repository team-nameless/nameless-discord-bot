# pyright: reportUnknownVariableType=false

from __future__ import annotations

import contextlib
import json
import logging
import time
import urllib.parse
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from ..providers._manifest import ProviderManifest, ServiceHealthManifest

HEALTH_CACHE: dict[str, tuple[bool, float]] = {}


# based on https://github.com/spotiflacapp/SpotiFLAC-Mobile/blob/7624e24ea6880f45c9218859af3bd3000464330f/go_backend/extension_health.go#L69
def check_service_health(manifest: ProviderManifest, logger: logging.Logger | None = None) -> bool:
    extension_id = manifest.get("name")
    if not extension_id:
        return True

    service_health = manifest.get("serviceHealth", [])
    if not service_health:
        return True

    now = time.time()
    if extension_id in HEALTH_CACHE:
        is_healthy, expires_at = HEALTH_CACHE[extension_id]
        if now < expires_at:
            return is_healthy

    is_healthy = run_health_checks(manifest, service_health, logger=logger)

    ttl = 60.0
    for check in service_health:
        check_ttl = check.get("cacheTtlSeconds", 60)
        if 0 < check_ttl < ttl:
            ttl = float(check_ttl)

    HEALTH_CACHE[extension_id] = (is_healthy, now + ttl)
    return is_healthy


def run_health_checks(
    manifest: ProviderManifest,
    checks: list[ServiceHealthManifest],
    *,
    logger: logging.Logger | None = None,
) -> bool:
    logger = logger or logging.getLogger("HealthCheck")

    # overall status of the extension. Starts as "online" if there are checks.
    # if a required check is offline, status becomes "offline" (which means False).
    # otherwise we consider it True.
    extension_status = "online"

    for check in checks:
        url_str = check.get("url")
        if not url_str:
            continue

        required = check.get("required", True)
        method = check.get("method", "GET").upper()
        if method not in ("GET", "HEAD"):
            # golang code does this check
            check_status = "offline"
            if required:
                extension_status = "offline"
            elif extension_status == "online":
                extension_status = "degraded"
            continue

        timeout_ms = check.get("timeoutMs", 4000)
        timeout_sec = timeout_ms / 1000.0

        try:
            parsed = urllib.parse.urlparse(url_str)
            if parsed.scheme != "https":
                raise ValueError("health check must use https")
            if not parsed.hostname:
                raise ValueError("health check URL hostname is required")
        except Exception:
            check_status = "offline"
            if required:
                extension_status = "offline"
            elif extension_status == "online":
                extension_status = "degraded"
            continue

        # run HTTP request
        try:
            headers = {
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            with httpx.Client(http2=True) as client:
                if method == "GET":
                    r = client.get(url_str, timeout=timeout_sec, headers=headers)
                else:
                    r = client.head(url_str, timeout=timeout_sec, headers=headers)

            if r.status_code < 200 or r.status_code >= 300:
                check_status = "offline"
            elif method == "HEAD":
                check_status = "online"
            else:
                # read body up to 64KB
                body = r.content[: 64 * 1024]
                service_key = check.get("serviceKey")
                check_status = classify_health_body(body, service_key)

        except Exception as e:
            logger.warning("health check failed for %s: %s", url_str, e)
            check_status = "offline"

        # update overall status
        if check_status == "offline":
            if required:
                extension_status = "offline"
            elif extension_status == "online":
                extension_status = "degraded"
        elif check_status == "degraded":
            if extension_status == "online":
                extension_status = "degraded"
        elif check_status == "unknown" and extension_status == "online":
            extension_status = "unknown"

    return extension_status != "offline"


def classify_health_body(body: bytes, service_key: str | None) -> str:
    body_str = body.decode("utf-8", errors="ignore").strip()
    if not body_str:
        return "online"

    try:
        payload = json.loads(body_str)
    except Exception:
        return "online"

    if service_key and service_key.strip():
        status, found = classify_health_service(payload, service_key.strip())
        if found:
            return status

    raw_status = payload.get("status")
    if raw_status is None:
        return "online"

    normalized = str(raw_status).lower().strip()
    if normalized in ("", "ok", "up", "online", "healthy", "operational", "pass", "passing"):
        return "online"
    elif normalized in ("degraded", "partial", "warning", "warn"):
        return "degraded"
    elif normalized in ("down", "offline", "error", "failed", "fail", "unhealthy"):
        return "offline"
    else:
        return "online"


def classify_health_service(payload: dict[str, Any], service_key: str) -> tuple[str, bool]:  # noqa: PLR0911
    services = payload.get("services")
    if not isinstance(services, dict):
        return "", False

    service = services.get(service_key)
    if service is None:
        return "unknown", True
    if not isinstance(service, dict):
        return "unknown", True

    raw_status = service.get("status")
    ok_value = service.get("ok")
    detail = service.get("detail", "")

    status_code = None
    if isinstance(raw_status, (int, float)):
        status_code = int(raw_status)
    elif isinstance(raw_status, str):
        with contextlib.suppress(ValueError):
            status_code = int(raw_status)

    if status_code is not None:
        if 200 <= status_code < 300:
            return "online", True
        if status_code in (401, 403):
            return "degraded", True
        if status_code == 500 and ok_value is True:
            return "online", True
        return "offline", True

    if isinstance(detail, str):
        detail_lower = detail.lower().strip()
        if detail_lower in ("auth_required", "authorization_required", "login_required", "unauthorized"):
            return "degraded", True

    if ok_value is not None:
        if ok_value is True:
            return "online", True
        return "offline", True

    if raw_status is None:
        return "unknown", True

    status_str = str(raw_status).lower().strip()
    if status_str in ("ok", "up", "online", "healthy", "operational"):
        return "online", True
    elif status_str in ("degraded", "partial", "warning", "warn"):
        return "degraded", True
    elif status_str in ("down", "offline", "error", "failed", "fail", "unhealthy"):
        return "offline", True
    else:
        return "unknown", True
